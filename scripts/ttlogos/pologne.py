"""Clubs polonais : le registre des licences de la PZTS, complété par la Mazovie.

La fédération publie la liste de ses clubs licenciés — numéro, nom et voïvodie — dans
le tableau des licences de clubs de son système de compétition. Ce tableau ne donne
pas les adresses de site : la fédération ne les collecte pas.

Une seule des seize associations régionales, celle de Mazovie, publie ses clubs avec
leur site. Les autres n'ont pas d'annuaire exploitable. Les clubs des quinze autres
voïvodies figurent donc au catalogue avec leur nom et leur région, mais sans logo.

De la page mazovienne ne sont retenus que le nom du club et l'adresse de son site :
elle affiche aussi le président, son téléphone et le numéro fiscal de l'association,
qui ne sont jamais enregistrés.
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

LICENCES = "https://rozgrywki.pzts.pl/rozgrywki-indywidualne/club_licenses?season=18"
MAZOVIE = "http://www.mzts.pl/kluby-czlonkowskie/"

# Les seize voïvodies, telles que le tableau les abrège.
VOIVODIES: dict[str, tuple[str, str]] = {
    "DŚL": ("PL-DOLNOSLASKIE", "Basse-Silésie"),
    "KPM": ("PL-KUJAWSKO-POMORSKIE", "Cujavie-Poméranie"),
    "LBU": ("PL-LUBUSKIE", "Lubusz"),
    "LLS": ("PL-LUBELSKIE", "Lublin"),
    "MAZ": ("PL-MAZOWIECKIE", "Mazovie"),
    "MŁP": ("PL-MALOPOLSKIE", "Petite-Pologne"),
    "OPO": ("PL-OPOLSKIE", "Opole"),
    "PDL": ("PL-PODLASKIE", "Podlachie"),
    "PKR": ("PL-PODKARPACKIE", "Basses-Carpates"),
    "POM": ("PL-POMORSKIE", "Poméranie"),
    "WLP": ("PL-WIELKOPOLSKIE", "Grande-Pologne"),
    "WMZ": ("PL-WARMINSKO-MAZURSKIE", "Varmie-Mazurie"),
    "ZPM": ("PL-ZACHODNIOPOMORSKIE", "Poméranie occidentale"),
    "ŁDZ": ("PL-LODZKIE", "Łódź"),
    "ŚLS": ("PL-SLASKIE", "Silésie"),
    "ŚWI": ("PL-SWIETOKRZYSKIE", "Sainte-Croix"),
}

# Liens présents sur la page mazovienne sans être le site d'un club.
NON_CLUB = re.compile(r"mzts\.pl|pzts\.pl|facebook|instagram|youtube|twitter|x\.com|"
                      r"linkedin|google|w3\.org|wordpress|themezee", re.I)


# Presque tous les clubs polonais commencent par un sigle de forme juridique : ces
# lettres ne distinguent rien et ne doivent pas servir à rapprocher deux fiches.
SIGLES = {"uks", "ks", "mks", "lks", "glks", "wks", "tg", "ktsi", "kts", "ts", "mos",
          "mosir", "osir", "ludowy", "klub", "sportowy", "miejski", "gminny", "uczniowski",
          "ludowe", "zespol", "stowarzyszenie", "towarzystwo", "sekcja", "tenisa",
          "stolowego", "gimnazjum", "szkolny", "szkola"}


def _sans_accent(texte: str) -> str:
    decompose = unicodedata.normalize("NFKD", texte)
    # « ł » ne se décompose pas : il faut le traduire à part.
    return "".join(c for c in decompose if not unicodedata.combining(c)).replace(
        "ł", "l").replace("Ł", "L")


def _comparable(nom: str) -> str:
    """Forme d'un nom de club qui permet de le reconnaître d'une source à l'autre.

    Les deux sources n'écrivent pas les noms de la même façon : accents, majuscules,
    ponctuation et espaces surnuméraires varient (« UKS LUPUS Kabaty Wars zawa »).
    """
    return re.sub(r"[^a-z0-9]+", "", _sans_accent(nom).lower())


def _mots(nom: str) -> set[str]:
    """Mots distinctifs d'un nom de club, sigles de forme juridique retirés.

    Une comparaison mot à mot rattrape ce que la forme compacte laisse passer : les
    deux annuaires coupent parfois un nom au mauvais endroit (« Wars zawa »), en
    inversent l'ordre ou ajoutent la forme juridique d'un côté seulement.
    """
    mots = re.findall(r"[a-z0-9]+", _sans_accent(nom).lower())
    return {m for m in mots if len(m) >= 4 and m not in SIGLES}


def _rapprocher(nom: str, index: dict[str, str], par_mot: dict[str, set[str]]) -> str:
    """Adresse du site d'un club, cherchée d'abord à l'identique puis mot à mot."""
    exact = index.get(_comparable(nom))
    if exact:
        return exact
    mots = _mots(nom)
    if not mots:
        return ""
    # Un candidat doit partager au moins deux mots distinctifs, faute de quoi deux
    # clubs d'une même ville seraient confondus.
    comptes: dict[str, int] = {}
    for mot in mots:
        for candidat in par_mot.get(mot, ()):
            comptes[candidat] = comptes.get(candidat, 0) + 1
    meilleurs = sorted(comptes.items(), key=lambda paire: -paire[1])
    if meilleurs and meilleurs[0][1] >= 2 and (
            len(meilleurs) == 1 or meilleurs[0][1] > meilleurs[1][1]):
        return index.get(meilleurs[0][0], "")
    return ""


def club_depuis_ligne(ligne) -> Club | None:
    """Construit un club à partir d'une ligne du tableau des licences."""
    cellules = ligne.find_all("td")
    if len(cellules) < 7:
        return None
    lien = cellules[2].find("a", href=True)
    if lien is None:
        return None
    identifiant = re.search(r"c_id=(\d+)", lien["href"])
    nom = lien.get_text(" ", strip=True)
    if not identifiant or not nom:
        return None
    sigle = cellules[6].get_text(strip=True)
    ligue_code, ligue_nom = VOIVODIES.get(sigle, ("PL-AUTRE", sigle or "Pologne"))

    club = Club(
        pays="PL",
        numero=f"PL{identifiant.group(1)}",
        nom=nom,
        ligue_code=ligue_code,
        ligue_nom=ligue_nom,
        source_donnees=f"PZTS (licences de clubs), club {identifiant.group(1)}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.SITE_ABSENT
    return club


def sites_de_mazovie(client: Client) -> dict[str, str]:
    """Adresses de site des clubs mazoviens, indexées par nom comparable."""
    reponse = client.get(MAZOVIE, taille_max=8_000_000)
    if reponse is None:
        journal.warning("annuaire mazovien inaccessible")
        return {}
    soupe = BeautifulSoup(reponse.text, "html.parser")
    sites: dict[str, str] = {}
    for ligne in soupe.find_all("tr"):
        cellules = ligne.find_all("td")
        if not cellules:
            continue
        # « 1. TG SOKÓŁ Brwinów » : le rang précède le nom.
        nom = re.sub(r"^\s*\d+\.\s*", "", cellules[0].get_text(" ", strip=True))
        adresses = [a["href"] for a in ligne.find_all("a", href=True)
                    if a["href"].startswith("http") and not NON_CLUB.search(a["href"])]
        if nom and adresses:
            sites[_comparable(nom)] = adresses[0]
            sites.setdefault("mots:" + _comparable(nom), nom)
    journal.info("Mazovie : %d clubs avec un site", len(sites))
    return sites


def liste_des_clubs(client: Client, limite: int = 0) -> list[Club]:
    """Lit le tableau des licences, puis complète la Mazovie avec ses sites."""
    reponse = client.get(LICENCES, taille_max=20_000_000)
    if reponse is None:
        journal.error("registre des licences polonais inaccessible")
        return []
    soupe = BeautifulSoup(reponse.text, "html.parser")
    clubs: dict[str, Club] = {}
    for ligne in soupe.find_all("tr"):
        club = club_depuis_ligne(ligne)
        if club is not None:
            clubs[club.numero] = club
    journal.info("registre polonais : %d clubs", len(clubs))

    sites = sites_de_mazovie(client)
    index = {cle: valeur for cle, valeur in sites.items() if not cle.startswith("mots:")}
    par_mot: dict[str, set[str]] = {}
    for cle, valeur in sites.items():
        if cle.startswith("mots:"):
            for mot in _mots(valeur):
                par_mot.setdefault(mot, set()).add(cle[len("mots:"):])
    apparies = 0
    for club in clubs.values():
        adresse = _rapprocher(club.nom, index, par_mot)
        if adresse:
            club.site_web = adresse
            club.logo_statut = catalogue.LOGO_ABSENT
            apparies += 1
    journal.info("registre polonais : %d clubs avec un site", apparies)

    liste = sorted(clubs.values(), key=lambda c: c.nom.lower())
    return liste[:limite] if limite else liste
