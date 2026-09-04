"""Clubs belges : annuaire de l'API TabT, sites web du moteur de recherche de l'AFTT.

La fédération publie une API SOAP ouverte (TabT) qui liste les 500 et quelques clubs
du pays, des deux ailes linguistiques, avec leur province et leur salle — mais sans
adresse de site. Le moteur « trouver un club » de l'AFTT, lui, affiche cette adresse :
on l'interroge club par club à partir de l'index renvoyé par l'API.

Seule l'adresse du site est retenue de cette seconde page : les coordonnées du
correspondant qui y figurent aussi ne sont jamais enregistrées.

API : https://api.vttl.be/0.7/?wsdl
"""

from __future__ import annotations

import html as bibliotheque_html
import re
import time

from bs4 import BeautifulSoup

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

API = "https://api.vttl.be/0.7/"
RECHERCHE_AFTT = "https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi"

# Les catégories de l'API sont les provinces : elles tiennent lieu de ligues.
PROVINCES: dict[str, tuple[str, str]] = {
    "Antwerpen": ("BE-ANTWERPEN", "Anvers"),
    "Br. & Brabant Wallon": ("BE-BRUXELLES-BRABANT", "Bruxelles et Brabant wallon"),
    "Hainaut": ("BE-HAINAUT", "Hainaut"),
    "Liège": ("BE-LIEGE", "Liège"),
    "Limburg": ("BE-LIMBURG", "Limbourg"),
    "Luxembourg": ("BE-LUXEMBOURG", "Luxembourg"),
    "Namur": ("BE-NAMUR", "Namur"),
    "Oost-Vlaanderen": ("BE-OOST-VLAANDEREN", "Flandre-Orientale"),
    "Vlaams-Brabant & Br.": ("BE-VLAAMS-BRABANT", "Brabant flamand"),
    "West-Vlaanderen": ("BE-WEST-VLAANDEREN", "Flandre-Occidentale"),
}
# Entrées de service de l'API : ce ne sont pas des clubs.
CATEGORIES_ADMINISTRATIVES = {"AFTT", "VTTL", "FRBTT", ""}

# Le moteur de l'AFTT affiche en permanence quelques liens qui ne sont pas des clubs.
MEUBLES = re.compile(
    r"aftt\.be|frbtt|vttl\.be|facebook|instagram|youtube|twitter|linkedin|tiktok|"
    r"google|w3\.org|adeps|aisf|ettu\.org|ittf\.com|cpdeliege|wordpress|elementor|"
    r"gravatar|gstatic|cloudflare", re.I)


def _enveloppe(espace: str) -> bytes:
    return ('<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><GetClubs xmlns="{espace}"></GetClubs></soap:Body>'
            '</soap:Envelope>').encode()


def _champ(fiche: str, nom: str) -> str:
    """Valeur d'un champ de la réponse SOAP, entités HTML décodées.

    L'API encode deux fois les caractères accentués (« Li&amp;egrave;ge ») : il faut
    donc deux passes. Une troisième serait sans effet, et un « &amp; » légitime dans un
    nom de club redevient simplement « & » dès la première.
    """
    trouve = re.search(rf"<\w+:{nom}>(.*?)</\w+:{nom}>", fiche, re.S)
    if not trouve:
        return ""
    valeur = re.sub(r"\s+", " ", trouve.group(1))
    return bibliotheque_html.unescape(bibliotheque_html.unescape(valeur)).strip()


def zone_postale(code_postal: str) -> str:
    """Regroupement géographique : les deux premiers chiffres du code postal."""
    if len(code_postal) < 2 or not code_postal[:2].isdigit():
        return ""
    return f"BE{code_postal[:2]}"


def club_depuis_fiche(fiche: str) -> Club | None:
    """Construit un club à partir d'une entrée ClubEntries de l'API."""
    index = _champ(fiche, "UniqueIndex")
    categorie = _champ(fiche, "CategoryName")
    if not index or categorie in CATEGORIES_ADMINISTRATIVES:
        return None
    ligue_code, ligue_nom = PROVINCES.get(categorie, ("BE-AUTRE", categorie or "Belgique"))

    # « 2800 Mechelen » : la commune de la salle donne code postal et ville.
    code_postal, ville = "", ""
    commune = _champ(fiche, "Town")
    trouve = re.match(r"\s*(\d{4})\s+(.+)", commune)
    if trouve:
        code_postal, ville = trouve.group(1), trouve.group(2).strip()
    elif commune:
        ville = commune

    nom_court = _champ(fiche, "Name")  # le premier <Name> est le nom court du club
    nom_salle = ""
    salles = re.search(r"<\w+:VenueEntries>(.*?)</\w+:VenueEntries>", fiche, re.S)
    if salles:
        nom_salle = _champ(salles.group(1), "Name")

    club = Club(
        pays="BE",
        numero=f"BE{index}",
        nom=_champ(fiche, "LongName") or nom_court,
        ville=ville,
        code_postal=code_postal,
        salle=nom_salle,
        ligue_code=ligue_code,
        ligue_nom=ligue_nom,
        dep=zone_postale(code_postal),
        dep_nom=f"CP {code_postal[:2]}" if code_postal else "",
        source_donnees=f"API TabT (FRBTT), club {index}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.SITE_ABSENT
    return club


def liste_des_clubs(client: Client) -> list[Club]:
    """Appelle GetClubs et rend un club par entrée exploitable."""
    wsdl = client.get(f"{API}?wsdl", taille_max=6_000_000)
    if wsdl is None:
        journal.error("API TabT : le WSDL est inaccessible")
        return []
    espace = re.search(r'targetNamespace="([^"]+)"', wsdl.text)
    espace = espace.group(1) if espace else "http://api.frenoy.net/TabTAPI"
    try:
        reponse = client.session.post(
            API, data=_enveloppe(espace),
            headers={"Content-Type": "text/xml; charset=utf-8",
                     "SOAPAction": f'"{espace}#GetClubs"'}, timeout=120)
    except Exception as erreur:  # noqa: BLE001
        journal.error("API TabT : %s: %s", type(erreur).__name__, erreur)
        return []
    fiches = re.findall(r"<\w+:ClubEntries>(.*?)</\w+:ClubEntries>", reponse.text, re.S)
    journal.info("API TabT : %d entrées reçues", len(fiches))
    clubs = [club for club in (club_depuis_fiche(f) for f in fiches) if club is not None]
    return sorted(clubs, key=lambda c: c.nom.lower())


def _liens_externes(html: str) -> set[str]:
    soupe = BeautifulSoup(html, "html.parser")
    return {a["href"] for a in soupe.find_all("a", href=True)
            if a["href"].startswith("http") and not MEUBLES.search(a["href"])}


def site_du_club(index: str, client: Client, meubles: set[str]) -> str:
    """Interroge le moteur de l'AFTT et rend l'adresse du site du club, si elle existe.

    Le moteur ne connaît que les clubs de l'aile francophone : pour les autres, la
    réponse est une page vide de tout lien nouveau, et le club reste sans site.
    """
    try:
        reponse = client.session.post(RECHERCHE_AFTT,
                                      data={"club": index, "search_club": "1"}, timeout=45)
    except Exception as erreur:  # noqa: BLE001
        journal.debug("AFTT %s : %s", index, erreur)
        return ""
    if reponse.status_code != 200:
        return ""
    # Le nom du club doit apparaître : sinon la recherche n'a rien trouvé et les liens
    # de la page ne le concernent pas.
    if index.upper() not in reponse.text.upper():
        return ""
    nouveaux = sorted(_liens_externes(reponse.text) - meubles)
    return nouveaux[0] if nouveaux else ""


def completer_les_sites(clubs: list[Club], client: Client, budget: float = 0) -> int:
    """Renseigne l'adresse du site de chaque club, un appel au moteur AFTT par club."""
    vide = client.session.post(RECHERCHE_AFTT,
                               data={"club": "ZZZZZZZZ", "search_club": "1"}, timeout=45)
    meubles = _liens_externes(vide.text) if vide.status_code == 200 else set()
    journal.info("moteur AFTT : %d liens de décor à ignorer", len(meubles))

    depart = time.monotonic()
    trouves = 0
    for rang, club in enumerate(clubs, 1):
        if budget and time.monotonic() - depart > budget * 60:
            journal.warning("budget épuisé après %d clubs", rang - 1)
            break
        index = club.numero[2:]
        adresse = site_du_club(index, client, meubles)
        if adresse:
            club.site_web = adresse
            club.logo_statut = catalogue.LOGO_ABSENT
            trouves += 1
        if rang % 50 == 0:
            journal.info("sites : %d clubs interrogés, %d adresses trouvées", rang, trouves)
        time.sleep(0.4)
    journal.info("sites : %d adresses trouvées sur %d clubs", trouves, len(clubs))
    return trouves
