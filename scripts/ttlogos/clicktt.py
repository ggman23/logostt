"""Source publique allemande : click-TT (nuLiga), le système du DTTB.

Deux points d'entrée suffisent, sans identifiants :

* ``clubSearch`` (POST, champ ``searchFor``) renvoie d'un coup, sans pagination, tous
  les clubs dont le nom contient le terme cherché — quelques lettres couvrent les
  ~9 000 clubs allemands ;
* ``clubInfoDisplay?club=<id>`` est la fiche publique d'un club : Landesverband, numéro
  d'affiliation, salle, adresse, lien vers le site du club, et surtout **le logo officiel
  hébergé par click-TT**, ce qui évite d'avoir à le deviner sur le site du club.

Comme pour la France, l'adresse de contact d'une personne (nom, téléphone) figure sur la
fiche : elle n'est ni extraite ni enregistrée.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from . import catalogue
from .catalogue import Club
from .reseau import Client

journal = logging.getLogger("logostt")

BASE = "https://dttb.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa"
RECHERCHE = f"{BASE}/clubSearch"
FICHE = f"{BASE}/clubInfoDisplay?club={{club}}"

# Termes de recherche : leur union couvre les noms de clubs allemands. Presque tous
# contiennent « e » ou « a » ; les autres lettres rattrapent les sigles et les exceptions.
TERMES = ["e", "a", "i", "o", "u", "s", "n", "r", "t", "c", "v", "g", "b", "z", "ü", "ö", "ä"]

# Liens présents sur toutes les fiches : ce ne sont pas les sites des clubs.
DOMAINES_IGNORES = re.compile(
    r"(^|\.)(click-tt\.de|tischtennis\.de|mytischtennis\.de|datenautomaten\.nu|"
    r"google\.[a-z.]+|liga\.nu|nu-liga\.de)$",
    re.I,
)


def liste_des_clubs(client: Client, termes: list[str] | None = None) -> list[dict[str, str]]:
    """Tous les clubs trouvés par la recherche publique, dédoublonnés par identifiant."""
    clubs: dict[str, dict[str, str]] = {}
    for terme in termes or TERMES:
        try:
            reponse = client.session.post(
                RECHERCHE,
                data={"federation": "DTTB", "federations": "DTTB", "searchFor": terme},
                timeout=60,
            )
        except Exception as erreur:  # noqa: BLE001 - une recherche ratée ne doit pas tout arrêter
            journal.warning("recherche « %s » en échec : %s", terme, erreur)
            continue
        avant = len(clubs)
        for entree in _lire_resultats(reponse.text):
            clubs.setdefault(entree["id"], entree)
        journal.info("recherche « %s » : %s clubs (+%s nouveaux)",
                     terme, len(clubs), len(clubs) - avant)
    return sorted(clubs.values(), key=lambda c: c["nom"])


def _lire_resultats(html: str) -> list[dict[str, str]]:
    soupe = BeautifulSoup(html, "html.parser")
    resultats = []
    for lien in soupe.select("a[href*='clubInfoDisplay']"):
        identifiant = re.search(r"club=(\d+)", lien["href"])
        nom = re.sub(r"\s+", " ", lien.get_text(" ", strip=True))
        if not identifiant or not nom:
            continue
        cellule = lien.find_parent("td")
        texte = re.sub(r"\s+", " ", cellule.get_text(" ", strip=True)) if cellule else nom
        numero = re.search(r"\((\d+)\)", texte)
        resultats.append({
            "id": identifiant.group(1),
            "nom": nom,
            "numero": numero.group(1) if numero else identifiant.group(1),
        })
    return resultats


def _site_du_club(soupe: BeautifulSoup) -> str:
    for lien in soupe.find_all("a", href=True):
        adresse = lien["href"].strip()
        if not adresse.lower().startswith("http"):
            continue
        if DOMAINES_IGNORES.search(catalogue.domaine_de(adresse)):
            continue
        return catalogue.normaliser_url(adresse)
    return ""


def _adresse(texte: str) -> tuple[str, str]:
    """Extrait (code postal, ville) d'un bloc d'adresse allemand."""
    trouve = re.search(r"\b(\d{5})\s+([A-Za-zÄÖÜäöüß][\w.\-' ]{1,40}?)\s*(?:,|$|\n)", texte)
    if not trouve:
        return "", ""
    return trouve.group(1), trouve.group(2).strip(" ,").strip()


def club_depuis_fiche(identifiant: str, html: str, nom_connu: str = "") -> Club | None:
    """Construit un club à partir du HTML de sa fiche click-TT."""
    soupe = BeautifulSoup(html, "html.parser")
    titre = soupe.find("h1")
    if titre is None:
        return None
    morceaux = [m.strip() for m in titre.get_text("\n", strip=True).split("\n") if m.strip()]
    if not morceaux:
        return None
    verband = morceaux[0]
    nom = morceaux[-1] if len(morceaux) > 1 else nom_connu
    if not nom or nom == verband:
        nom = nom_connu
    if not nom:
        return None

    texte = re.sub(r"[ \t]+", " ", soupe.get_text("\n", strip=True))
    numero = re.search(r"VNr\.?:\s*(\d+)", texte)
    code_postal, ville = _adresse(texte)

    salle = ""
    for entete in soupe.find_all("h2"):
        if entete.get_text(strip=True).lower().startswith("spiellokal"):
            bloc = entete.find_next("p")
            if bloc:
                lignes = [l.strip() for l in bloc.get_text("\n", strip=True).split("\n")
                          if l.strip() and not l.strip().lower().startswith(("tel", "routenplaner", "http"))]
                salle = " — ".join(lignes[:2])
                if not code_postal:
                    code_postal, ville = _adresse("\n".join(lignes))
            break

    club = Club(
        pays="DE",
        numero=f"DE{identifiant}",
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=salle,
        site_web=_site_du_club(soupe),
        ligue_nom=verband,
        ligue_code=code_ligue(verband),
        dep=dep_allemand(code_postal),
        dep_nom=f"PLZ {code_postal[:2]}" if code_postal else "",
        source_donnees=f"click-TT (DTTB), VNr. {numero.group(1) if numero else '?'}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def logo_heberge(soupe: BeautifulSoup) -> str:
    """URL du logo officiel hébergé par click-TT, s'il y en a un sur la fiche.

    L'adresse contient un jeton propre à la requête : elle doit être suivie tout de
    suite, avec la même session que celle qui a chargé la fiche.
    """
    for image in soupe.find_all("img", src=True):
        if "wodata=" in image["src"]:
            return "https://dttb.click-tt.de" + image["src"]
    return ""


def dep_allemand(code_postal: str) -> str:
    """Regroupement géographique : les deux premiers chiffres du code postal."""
    return f"D{code_postal[:2]}" if len(code_postal) >= 2 and code_postal[:2].isdigit() else ""


def code_ligue(verband: str) -> str:
    """Code court et stable pour un Landesverband.

    « Tischtennis Baden-Württemberg e.V. » -> « DE-BADEN-WUERTTEM ». Les mots communs à
    tous les verbands sont retirés pour que les codes restent distincts entre eux.
    """
    nettoye = re.sub(
        r"\b(e\.?\s?V\.?|Tischtennis-?(verband|bund)?|Verband|Landesverband|Deutscher)\b",
        " ", verband, flags=re.I,
    )
    racine = catalogue.slug(nettoye.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae"))
    return ("DE-" + (racine[:17] or catalogue.slug(verband)[:17])).upper().strip("-")
