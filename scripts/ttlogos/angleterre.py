"""Clubs anglais : lecture du flux ouvert publié par Table Tennis England.

La fédération publie l'intégralité de son annuaire au format OpenActive (RPDE 0.2.3)
sur tabletennis365.com, sans clé ni inscription. Chaque fiche donne le nom du club,
l'adresse de son site quand il en a un, et la salle où il joue. Il n'y a pas de logo
dans le flux : ils sont ensuite extraits des sites des clubs, comme en France.

Documentation du flux : https://github.com/TableTennis365/opendata
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

FLUX = "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs"


class SourceEnMaintenance(RuntimeError):
    """La fédération a coupé son flux : ce n'est pas une erreur de notre côté.

    Le serveur répond alors 503 avec un corps JSON explicite. Rien ne sert de
    réessayer dans la minute : la collecte s'arrête et sera relancée plus tard.
    """

# Les zones postales britanniques (les lettres qui ouvrent un code postal) servent de
# second niveau de navigation, comme les départements en France ; chacune est rattachée
# à l'une des neuf régions anglaises, qui tiennent lieu de ligues.
LONDRES = "Londres"
NORD_EST = "Nord-Est"
NORD_OUEST = "Nord-Ouest"
YORKSHIRE = "Yorkshire et Humber"
MIDLANDS_EST = "Midlands de l'Est"
MIDLANDS_OUEST = "Midlands de l'Ouest"
EST = "Est de l'Angleterre"
SUD_EST = "Sud-Est"
SUD_OUEST = "Sud-Ouest"

ZONES: dict[str, tuple[str, str]] = {
    "AL": ("St Albans", EST), "B": ("Birmingham", MIDLANDS_OUEST),
    "BA": ("Bath", SUD_OUEST), "BB": ("Blackburn", NORD_OUEST),
    "BD": ("Bradford", YORKSHIRE), "BH": ("Bournemouth", SUD_OUEST),
    "BL": ("Bolton", NORD_OUEST), "BN": ("Brighton", SUD_EST),
    "BR": ("Bromley", LONDRES), "BS": ("Bristol", SUD_OUEST),
    "CA": ("Carlisle", NORD_OUEST), "CB": ("Cambridge", EST),
    "CH": ("Chester", NORD_OUEST), "CM": ("Chelmsford", EST),
    "CO": ("Colchester", EST), "CR": ("Croydon", LONDRES),
    "CT": ("Canterbury", SUD_EST), "CV": ("Coventry", MIDLANDS_OUEST),
    "CW": ("Crewe", NORD_OUEST), "DA": ("Dartford", SUD_EST),
    "DE": ("Derby", MIDLANDS_EST), "DH": ("Durham", NORD_EST),
    "DL": ("Darlington", NORD_EST), "DN": ("Doncaster", YORKSHIRE),
    "DT": ("Dorchester", SUD_OUEST), "DY": ("Dudley", MIDLANDS_OUEST),
    "E": ("Londres Est", LONDRES), "EC": ("Londres Cité", LONDRES),
    "EN": ("Enfield", LONDRES), "EX": ("Exeter", SUD_OUEST),
    "FY": ("Blackpool", NORD_OUEST), "GL": ("Gloucester", SUD_OUEST),
    "GU": ("Guildford", SUD_EST), "HA": ("Harrow", LONDRES),
    "HD": ("Huddersfield", YORKSHIRE), "HG": ("Harrogate", YORKSHIRE),
    "HP": ("Hemel Hempstead", EST), "HR": ("Hereford", MIDLANDS_OUEST),
    "HU": ("Hull", YORKSHIRE), "HX": ("Halifax", YORKSHIRE),
    "IG": ("Ilford", LONDRES), "IP": ("Ipswich", EST),
    "KT": ("Kingston upon Thames", LONDRES), "L": ("Liverpool", NORD_OUEST),
    "LA": ("Lancaster", NORD_OUEST), "LE": ("Leicester", MIDLANDS_EST),
    "LN": ("Lincoln", MIDLANDS_EST), "LS": ("Leeds", YORKSHIRE),
    "LU": ("Luton", EST), "M": ("Manchester", NORD_OUEST),
    "ME": ("Medway", SUD_EST), "MK": ("Milton Keynes", SUD_EST),
    "N": ("Londres Nord", LONDRES), "NE": ("Newcastle upon Tyne", NORD_EST),
    "NG": ("Nottingham", MIDLANDS_EST), "NN": ("Northampton", MIDLANDS_EST),
    "NR": ("Norwich", EST), "NW": ("Londres Nord-Ouest", LONDRES),
    "OL": ("Oldham", NORD_OUEST), "OX": ("Oxford", SUD_EST),
    "PE": ("Peterborough", EST), "PL": ("Plymouth", SUD_OUEST),
    "PO": ("Portsmouth", SUD_EST), "PR": ("Preston", NORD_OUEST),
    "RG": ("Reading", SUD_EST), "RH": ("Redhill", SUD_EST),
    "RM": ("Romford", LONDRES), "S": ("Sheffield", YORKSHIRE),
    "SE": ("Londres Sud-Est", LONDRES), "SG": ("Stevenage", EST),
    "SK": ("Stockport", NORD_OUEST), "SL": ("Slough", SUD_EST),
    "SM": ("Sutton", LONDRES), "SN": ("Swindon", SUD_OUEST),
    "SO": ("Southampton", SUD_EST), "SP": ("Salisbury", SUD_OUEST),
    "SR": ("Sunderland", NORD_EST), "SS": ("Southend-on-Sea", EST),
    "ST": ("Stoke-on-Trent", MIDLANDS_OUEST), "SW": ("Londres Sud-Ouest", LONDRES),
    "SY": ("Shrewsbury", MIDLANDS_OUEST), "TA": ("Taunton", SUD_OUEST),
    "TF": ("Telford", MIDLANDS_OUEST), "TN": ("Tonbridge", SUD_EST),
    "TQ": ("Torquay", SUD_OUEST), "TR": ("Truro", SUD_OUEST),
    "TS": ("Teesside", NORD_EST), "TW": ("Twickenham", LONDRES),
    "UB": ("Southall", LONDRES), "W": ("Londres Ouest", LONDRES),
    "WA": ("Warrington", NORD_OUEST), "WC": ("Londres Centre", LONDRES),
    "WD": ("Watford", EST), "WF": ("Wakefield", YORKSHIRE),
    "WN": ("Wigan", NORD_OUEST), "WR": ("Worcester", MIDLANDS_OUEST),
    "WS": ("Walsall", MIDLANDS_OUEST), "WV": ("Wolverhampton", MIDLANDS_OUEST),
    "YO": ("York", YORKSHIRE),
    # Quelques clubs affiliés jouent hors d'Angleterre : ils gardent une zone lisible.
    "CF": ("Cardiff", "Pays de Galles"), "LL": ("Llandudno", "Pays de Galles"),
    "NP": ("Newport", "Pays de Galles"), "SA": ("Swansea", "Pays de Galles"),
    "LD": ("Llandrindod Wells", "Pays de Galles"),
    "IM": ("Île de Man", "Îles"), "JE": ("Jersey", "Îles"), "GY": ("Guernesey", "Îles"),
}
AUTRE = ("Autre", "Hors régions")

# « SS3 9HD » -> zone « SS ». Une zone est faite d'une ou deux lettres.
ZONE = re.compile(r"^\s*([A-Za-z]{1,2})\d")


def zone_postale(code_postal: str) -> tuple[str, str, str]:
    """Zone, nom de la zone et région d'un code postal britannique."""
    trouve = ZONE.match(code_postal or "")
    if not trouve:
        return "", "", ""
    zone = trouve.group(1).upper()
    nom, region = ZONES.get(zone, AUTRE)
    return zone, nom, region


def code_ligue(region: str) -> str:
    """Code court et stable pour une région, par exemple « EN-NORD-OUEST »."""
    return ("EN-" + catalogue.slug(region)[:20]).upper().strip("-")


def _site(fiche: dict) -> str:
    """Adresse du site du club, en écartant les valeurs vides que le flux laisse passer."""
    for cle in ("websiteUrl", "timetableUrl"):
        adresse = (fiche.get(cle) or "").strip()
        if adresse and adresse.lower() not in {"null", "http://", "https://", "-"}:
            if not adresse.startswith(("http://", "https://")):
                adresse = "http://" + adresse
            return adresse
    return ""


def club_depuis_element(element: dict) -> Club | None:
    """Construit un club à partir d'un élément du flux ouvert."""
    fiche = element.get("data") or {}
    identifiant = fiche.get("id") or element.get("id")
    nom = (fiche.get("name") or "").strip()
    if not identifiant or not nom:
        return None

    salles = fiche.get("venue") or []
    if isinstance(salles, dict):
        salles = [salles]
    # Un club peut jouer dans plusieurs salles : on retient la principale.
    principale: dict = {}
    for salle in salles:
        if not isinstance(salle, dict):
            continue
        if not principale or str(salle.get("primaryVenue")).lower() == "true":
            principale = salle
            if str(salle.get("primaryVenue")).lower() == "true":
                break

    code_postal = (principale.get("postcode") or "").strip().upper()
    dep, dep_nom, region = zone_postale(code_postal)
    adresse = (principale.get("address") or "").strip()
    # La ville est le dernier élément lisible de l'adresse, la salle son intitulé.
    morceaux = [m.strip() for m in adresse.split(",") if m.strip()]
    ville = morceaux[-1] if morceaux else ""

    club = Club(
        pays="EN",
        numero=f"EN{identifiant}",
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=(principale.get("name") or "").strip(),
        site_web=_site(fiche),
        ligue_nom=region,
        ligue_code=code_ligue(region) if region else "",
        dep=dep,
        dep_nom=dep_nom,
        latitude=str(principale.get("lat") or "").strip(),
        longitude=str(principale.get("lng") or "").strip(),
        source_donnees=f"Table Tennis England (données ouvertes), club {identifiant}",
        maj=catalogue.aujourdhui(),
    )
    if club.latitude in {"0.0", "0"} or club.longitude in {"0.0", "0"}:
        club.latitude = club.longitude = ""
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def liste_des_clubs(client: Client, limite: int = 0, pages_max: int = 200) -> list[Club]:
    """Parcourt le flux page par page jusqu'à ce qu'il n'annonce plus rien de neuf."""
    url = FLUX
    clubs: dict[str, Club] = {}
    for page in range(1, pages_max + 1):
        # Requête directe : on veut distinguer une coupure annoncée d'une panne.
        try:
            reponse = client.session.get(url, timeout=(8, 60))
        except Exception as erreur:  # noqa: BLE001
            journal.warning("flux anglais : page %d, %s: %s", page, type(erreur).__name__, erreur)
            break
        if reponse.status_code == 503:
            raise SourceEnMaintenance(
                "Table Tennis England a suspendu son flux ouvert "
                f"(HTTP 503 : {reponse.text.strip()[:120]})")
        if reponse.status_code != 200:
            journal.warning("flux anglais : page %d, HTTP %d", page, reponse.status_code)
            break
        try:
            donnees = reponse.json()
        except ValueError:
            journal.warning("flux anglais : page %d illisible", page)
            break
        elements = donnees.get("items") or []
        if not elements:
            break
        for element in elements:
            if element.get("state") == "deleted":
                clubs.pop(f"EN{element.get('id')}", None)
                continue
            club = club_depuis_element(element)
            if club is not None:
                # Le flux rejoue les fiches modifiées : la dernière vue fait foi.
                clubs[club.numero] = club
        journal.info("flux anglais : page %d, %d clubs connus", page, len(clubs))
        if limite and len(clubs) >= limite:
            break
        suivante = donnees.get("next")
        if not suivante:
            break
        suivante = urljoin(url, suivante)
        if suivante == url:
            break
        url = suivante
    liste = sorted(clubs.values(), key=lambda c: c.nom.lower())
    return liste[:limite] if limite else liste
