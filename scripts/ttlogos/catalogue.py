"""Lecture / écriture du catalogue des clubs (data/clubs.csv)."""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from datetime import date
from pathlib import Path

from . import referentiel

RACINE = referentiel.RACINE
FICHIER_CLUBS = RACINE / "data" / "clubs.csv"
FICHIER_CORRECTIONS = RACINE / "data" / "corrections.csv"

# Statuts possibles pour le logo d'un club.
LOGO_RECUPERE = "logo"          # fichier image récupéré et stocké dans site/logos/
LOGO_FAVICON = "favicon"        # seule une favicone a pu être extraite (qualité faible)
LOGO_ABSENT = "aucun"           # pas de logo trouvé
SITE_ABSENT = "sans-site"       # le club n'a pas de site web connu


@dataclass
class Club:
    numero: str = ""             # numéro d'affiliation FFTT (identifiant stable)
    nom: str = ""
    dep: str = ""
    dep_nom: str = ""
    ligue_code: str = ""
    ligue_nom: str = ""
    ville: str = ""
    code_postal: str = ""
    salle: str = ""
    site_web: str = ""
    logo_fichier: str = ""       # chemin relatif au dossier site/ (ex. logos/75/…webp)
    logo_source: str = ""        # URL d'origine du logo
    logo_statut: str = SITE_ABSENT
    couleurs: str = ""           # couleurs dominantes du logo, séparées par des espaces
    fond: str = ""               # « sombre » si le logo doit être posé sur fond sombre
    latitude: str = ""
    longitude: str = ""
    source_donnees: str = ""     # d'où viennent les informations du club
    maj: str = ""                # date de dernière mise à jour (AAAA-MM-JJ)

    def completer_geographie(self) -> None:
        """Complète département / ligue à partir du code postal ou du numéro FFTT."""
        if not self.dep:
            self.dep = referentiel.dep_depuis_code_postal(self.code_postal)
        if not self.dep and len(self.numero) >= 2 and self.numero[:2].isdigit():
            self.dep = self.numero[:2]
        self.dep = referentiel.normaliser_dep(self.dep)
        info = referentiel.departement(self.dep)
        if info:
            self.dep_nom = info.nom
            self.ligue_code = info.ligue_code
            self.ligue_nom = info.ligue_nom

    @property
    def domaine(self) -> str:
        return domaine_de(self.site_web)

    def cle_fichier(self) -> str:
        """Nom de fichier stable pour le logo du club."""
        base = slug(self.nom) or slug(self.ville) or "club"
        return f"{self.numero or base}-{base}"[:80]


COLONNES = [f.name for f in fields(Club)]


def slug(valeur: str) -> str:
    """Transforme un libellé en identifiant utilisable dans une URL ou un nom de fichier."""
    valeur = unicodedata.normalize("NFKD", valeur or "")
    valeur = valeur.encode("ascii", "ignore").decode("ascii").lower()
    valeur = re.sub(r"[^a-z0-9]+", "-", valeur).strip("-")
    return re.sub(r"-{2,}", "-", valeur)


def domaine_de(url: str) -> str:
    if not url:
        return ""
    url = re.sub(r"^https?://", "", url.strip(), flags=re.I)
    return url.split("/")[0].lower().removeprefix("www.")


def normaliser_url(url: str) -> str:
    """Nettoie une URL saisie à la main dans la base FFTT (souvent sans schéma)."""
    url = (url or "").strip().strip('"').strip()
    if not url or url.lower() in {"-", "n/a", "néant", "neant", "aucun"}:
        return ""
    url = url.replace(" ", "")
    if url.startswith("//"):
        url = "https:" + url
    if not re.match(r"^https?://", url, flags=re.I):
        if "@" in url or url.startswith("mailto:"):
            return ""
        url = "http://" + url
    if "." not in domaine_de(url):
        return ""
    return url


def charger(chemin: Path = FICHIER_CLUBS) -> list[Club]:
    if not chemin.exists():
        return []
    clubs: list[Club] = []
    with chemin.open(encoding="utf-8", newline="") as flux:
        for ligne in csv.DictReader(flux):
            clubs.append(Club(**{c: (ligne.get(c) or "").strip() for c in COLONNES}))
    return clubs


def enregistrer(clubs: list[Club], chemin: Path = FICHIER_CLUBS) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    clubs = trier(clubs)
    with chemin.open("w", encoding="utf-8", newline="") as flux:
        redacteur = csv.DictWriter(flux, fieldnames=COLONNES)
        redacteur.writeheader()
        for club in clubs:
            redacteur.writerow(asdict(club))


def trier(clubs: list[Club]) -> list[Club]:
    return sorted(clubs, key=lambda c: (c.dep, slug(c.ville), slug(c.nom)))


def fusionner(existants: list[Club], nouveaux: list[Club], deps_collectes: set[str]) -> list[Club]:
    """Fusionne une collecte avec le catalogue existant.

    Les informations fraîchement collectées font foi pour l'identité du club ; le travail
    déjà fait sur les logos est conservé tant que le site web du club n'a pas changé.
    Les clubs d'un département collecté qui n'apparaissent plus sont supprimés (désaffiliation).
    """
    index = {c.numero: c for c in existants if c.numero}
    resultat = [c for c in existants if c.dep not in deps_collectes or not c.numero]
    for club in nouveaux:
        ancien = index.get(club.numero)
        if ancien:
            club.logo_fichier = ancien.logo_fichier
            club.logo_source = ancien.logo_source
            club.logo_statut = ancien.logo_statut
            club.couleurs = ancien.couleurs
            club.fond = ancien.fond
            if ancien.site_web and not club.site_web:
                club.site_web = ancien.site_web
            if domaine_de(ancien.site_web) != domaine_de(club.site_web):
                # Le site a changé : le logo connu n'est plus fiable, on le redemandera.
                club.logo_fichier = club.logo_source = club.couleurs = club.fond = ""
                club.logo_statut = SITE_ABSENT
        resultat.append(club)
    return trier(resultat)


@dataclass
class Correction:
    """Correction manuelle appliquée après chaque collecte (data/corrections.csv)."""

    numero: str = ""
    site_web: str = ""
    logo_url: str = ""
    exclure: str = ""
    commentaire: str = ""


def charger_corrections(chemin: Path = FICHIER_CORRECTIONS) -> dict[str, Correction]:
    if not chemin.exists():
        return {}
    corrections: dict[str, Correction] = {}
    with chemin.open(encoding="utf-8", newline="") as flux:
        for ligne in csv.DictReader(flux):
            numero = (ligne.get("numero") or "").strip()
            if not numero:
                continue
            corrections[numero] = Correction(
                numero=numero,
                site_web=(ligne.get("site_web") or "").strip(),
                logo_url=(ligne.get("logo_url") or "").strip(),
                exclure=(ligne.get("exclure") or "").strip(),
                commentaire=(ligne.get("commentaire") or "").strip(),
            )
    return corrections


def appliquer_corrections(clubs: list[Club], corrections: dict[str, Correction]) -> list[Club]:
    if not corrections:
        return clubs
    resultat = []
    for club in clubs:
        correction = corrections.get(club.numero)
        if correction:
            if correction.exclure.lower() in {"1", "oui", "true", "x"}:
                continue
            if correction.site_web:
                nouveau = normaliser_url(correction.site_web)
                if domaine_de(nouveau) != club.domaine:
                    club.logo_fichier = club.logo_source = club.couleurs = club.fond = ""
                    club.logo_statut = SITE_ABSENT
                club.site_web = nouveau
        resultat.append(club)
    return resultat


def aujourdhui() -> str:
    return date.today().isoformat()
