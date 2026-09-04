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
from dataclasses import dataclass

from bs4 import BeautifulSoup

from . import catalogue
from .catalogue import Club
from .reseau import Client

journal = logging.getLogger("logostt")

@dataclass(frozen=True)
class Federation:
    """Une instance nationale de click-TT. Le moteur est le même partout."""

    pays: str            # code ISO du pays, tel qu'il figure au catalogue
    base: str            # racine de l'application nuLiga
    code: str            # code fédération attendu par la recherche
    longueur_cp: int     # 5 chiffres en Allemagne, 4 en Suisse

    @property
    def recherche(self) -> str:
        return f"{self.base}/clubSearch"

    def fiche(self, club: str) -> str:
        # La langue est forcée en allemand : les intitulés de la page (« Spiellokal »,
        # « VNr. ») servent de repères à l'extraction.
        return f"{self.base}/clubInfoDisplay?club={club}&preferredLanguage=German"

    @property
    def racine(self) -> str:
        return self.base.split("/cgi-bin/")[0]


ALLEMAGNE = Federation(
    pays="DE",
    base="https://dttb.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa",
    code="DTTB",
    longueur_cp=5,
)
SUISSE = Federation(
    pays="CH",
    base="https://www.click-tt.ch/cgi-bin/WebObjects/nuLigaTTCH.woa/wa",
    code="STT",
    longueur_cp=4,
)
FEDERATIONS = {"DE": ALLEMAGNE, "CH": SUISSE}

# Compatibilité avec l'existant.
BASE = ALLEMAGNE.base
RECHERCHE = ALLEMAGNE.recherche
FICHE = ALLEMAGNE.base + "/clubInfoDisplay?club={club}&preferredLanguage=German"

# Termes de recherche : leur union couvre les noms de clubs allemands. Presque tous
# contiennent « e » ou « a » ; les autres lettres rattrapent les sigles et les exceptions.
TERMES = ["e", "a", "i", "o", "u", "s", "n", "r", "t", "c", "v", "g", "b", "z", "ü", "ö", "ä"]

# Liens présents sur toutes les fiches : ce ne sont pas les sites des clubs.
DOMAINES_IGNORES = re.compile(
    r"(^|\.)(click-tt\.de|click-tt\.ch|tischtennis\.de|mytischtennis\.de|"
    r"swisstabletennis\.ch|datenautomaten\.nu|google\.[a-z.]+|liga\.nu|nu-liga\.de)$",
    re.I,
)


def liste_des_clubs(
    client: Client, termes: list[str] | None = None, federation: Federation = ALLEMAGNE
) -> list[dict[str, str]]:
    """Tous les clubs trouvés par la recherche publique, dédoublonnés par identifiant."""
    clubs: dict[str, dict[str, str]] = {}
    for terme in termes or TERMES:
        try:
            reponse = client.session.post(
                federation.recherche,
                data={"federation": federation.code, "federations": federation.code,
                      "searchFor": terme},
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


def _adresse(texte: str, longueur_cp: int = 5) -> tuple[str, str]:
    """Extrait (code postal, ville) d'un bloc d'adresse.

    En Suisse le code postal n'a que quatre chiffres : une année de fondation lui
    ressemble. On écarte donc les nombres introduits par un intitulé de date.
    """
    for trouve in re.finditer(
        rf"\b(\d{{{longueur_cp}}})\s+([A-Za-zÄÖÜäöüß][\w.\-' ]{{1,40}}?)\s*(?:,|$|\n)", texte
    ):
        avant = texte[max(0, trouve.start() - 30):trouve.start()].lower()
        if re.search(r"gr[üu]ndungsjahr|gegr|seit|jahr|ann[ée]e", avant):
            continue
        ville = trouve.group(2).strip(" ,").strip()
        if ville.lower() in {"kontaktadresse", "spiellokal", "verein", "informationen"}:
            continue
        return trouve.group(1), ville
    return "", ""


def _bloc(soupe: BeautifulSoup, intitule: str) -> str:
    """Texte qui suit un intitulé de section (« Kontaktadresse », « Spiellokal »)."""
    for entete in soupe.find_all(("h2", "h3")):
        if entete.get_text(strip=True).lower().startswith(intitule.lower()):
            suite = entete.find_next("p")
            if suite is not None:
                return re.sub(r"[ \t]+", " ", suite.get_text("\n", strip=True))
    return ""


# En Suisse, click-TT n'affiche qu'une fédération pour tout le pays : l'appartenance
# régionale se lit dans le numéro d'affiliation, dont la dizaine de milliers désigne
# l'association (10 000 = Genève, 20 000 = Neuchâtel-Jura, 30 000 = Tessin…). Les
# numéros inférieurs, et les multiples exacts de 10 000, sont les associations
# elles-mêmes et quelques comptes de service : ce ne sont pas des clubs.
ASSOCIATIONS_SUISSES = {
    1: ("CH-GENEVE", "Association Genevoise de Tennis de Table"),
    2: ("CH-NEUCHATEL-JURA", "Association Neuchâteloise et Jurassienne de Tennis de Table"),
    3: ("CH-TICINO", "Associazione Ticinese Tennis Tavolo"),
    4: ("CH-VAUD-VALAIS-FRIBOURG", "Association Vaudoise, Valaisanne et Fribourgeoise"),
    5: ("CH-MITTELLAND", "Mittelländischer Tischtennisverband"),
    6: ("CH-NORDWEST", "Nordwestschweizerischer Tischtennisverband"),
    7: ("CH-OST", "Ostschweizer Tischtennisverband"),
    8: ("CH-INNERSCHWEIZ", "Tischtennisverband Innerschweiz"),
}


def association_suisse(numero: int) -> tuple[str, str] | None:
    """Association régionale d'un club suisse, ou None si l'entrée n'est pas un club."""
    if numero < 10_000 or numero % 10_000 == 0:
        return None
    return ASSOCIATIONS_SUISSES.get(numero // 10_000, ("CH-STT", "Swiss Table Tennis"))


def club_depuis_fiche(
    identifiant: str, html: str, nom_connu: str = "", federation: Federation = ALLEMAGNE
) -> Club | None:
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
    # L'adresse est cherchée dans les blocs qui en contiennent une, jamais dans toute
    # la page : ailleurs, d'autres nombres pourraient passer pour un code postal.
    code_postal, ville = "", ""
    for intitule in ("Kontaktadresse", "Spiellokal"):
        bloc = _bloc(soupe, intitule)
        if bloc:
            code_postal, ville = _adresse(bloc, federation.longueur_cp)
            if code_postal:
                break

    salle = ""
    for entete in soupe.find_all("h2"):
        if entete.get_text(strip=True).lower().startswith("spiellokal"):
            bloc = entete.find_next("p")
            if bloc:
                lignes = [l.strip() for l in bloc.get_text("\n", strip=True).split("\n")
                          if l.strip() and not l.strip().lower().startswith(("tel", "routenplaner", "http"))]
                salle = " — ".join(lignes[:2])
                if not code_postal:
                    code_postal, ville = _adresse("\n".join(lignes), federation.longueur_cp)
            break

    vnr = int(numero.group(1)) if numero else 0
    ligue_code_club = code_ligue(verband)
    if federation.pays == "CH":
        association = association_suisse(vnr)
        if association is None:
            return None
        ligue_code_club, verband = association

    club = Club(
        pays=federation.pays,
        numero=f"{federation.pays}{identifiant}",
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=salle,
        site_web=_site_du_club(soupe),
        ligue_nom=verband,
        ligue_code=ligue_code_club,
        dep=zone_postale(code_postal, federation),
        dep_nom=f"{'PLZ' if federation.pays == 'DE' else 'NPA'} {code_postal[:2]}" if code_postal else "",
        source_donnees=f"click-TT ({federation.code}), VNr. {numero.group(1) if numero else '?'}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def logo_heberge(soupe: BeautifulSoup, federation: Federation = ALLEMAGNE) -> str:
    """URL du logo officiel hébergé par click-TT, s'il y en a un sur la fiche.

    L'adresse contient un jeton propre à la requête : elle doit être suivie tout de
    suite, avec la même session que celle qui a chargé la fiche.
    """
    for image in soupe.find_all("img", src=True):
        if "wodata=" in image["src"]:
            return federation.racine + image["src"]
    return ""


def zone_postale(code_postal: str, federation: Federation = ALLEMAGNE) -> str:
    """Regroupement géographique : les deux premiers chiffres du code postal."""
    if len(code_postal) < 2 or not code_postal[:2].isdigit():
        return ""
    return f"{'D' if federation.pays == 'DE' else 'CH'}{code_postal[:2]}"


def dep_allemand(code_postal: str) -> str:
    """Ancien nom, conservé pour l'existant."""
    return zone_postale(code_postal, ALLEMAGNE)


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
