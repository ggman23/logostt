"""Clubs croates : l'annuaire des clubs enregistrés de la HSTS.

La fédération publie ses clubs sur une seule page, un par ligne de tableau, avec le
nom, la commune, la salle et — pour un quart d'entre eux — l'adresse de leur site.

Chaque ligne donne aussi le nom, le courriel et le téléphone d'une personne de
contact : ces données personnelles ne sont ni extraites ni enregistrées.

Page : https://www.hsts.hr/index.php?option=com_hstsdata&Itemid=266
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

ANNUAIRE = "https://www.hsts.hr/index.php?option=com_hstsdata&Itemid=266"

# Liens présents dans une ligne sans être le site du club.
NON_CLUB = re.compile(r"hsts\.hr|facebook|instagram|youtube|twitter|x\.com|linkedin|"
                      r"google|w3\.org|flickr|domenacom|joomla", re.I)
# « Mjesto: 10010 , Zagreb-Novi Zagreb-istok » : le code postal croate a cinq chiffres.
COMMUNE = re.compile(r"Mjesto:\s*(\d{5})\s*,?\s*([^\n<]{1,60})")


def zone_postale(code_postal: str) -> str:
    """Regroupement géographique : les deux premiers chiffres du code postal."""
    if len(code_postal) < 2 or not code_postal[:2].isdigit():
        return ""
    return f"HR{code_postal[:2]}"


def _site(ligne: Tag) -> str:
    """Adresse du site du club, parmi les liens de la ligne."""
    for lien in ligne.find_all("a", href=True):
        adresse = lien["href"].strip()
        if adresse.startswith(("http://", "https://")) and not NON_CLUB.search(adresse):
            return adresse
    return ""


def club_depuis_ligne(ligne: Tag, rang: int = 0) -> Club | None:
    """Construit un club à partir d'une ligne de l'annuaire."""
    titre = ligne.find("h4")
    if titre is None:
        return None
    nom = re.sub(r"\s+", " ", titre.get_text(" ", strip=True))
    if not nom:
        return None

    # L'adresse n'est lue que dans le bloc <address>, jamais ailleurs : le reste de la
    # ligne contient un téléphone et d'autres nombres.
    bloc = ligne.find("address")
    texte = bloc.get_text("\n", strip=True) if bloc else ""
    code_postal, ville = "", ""
    trouve = COMMUNE.search(texte)
    if trouve:
        code_postal = trouve.group(1)
        ville = trouve.group(2).strip(" ,")

    salle = ""
    salle_trouvee = re.search(r"Adresa dvorane:\s*([^\n]{1,70})", texte)
    if salle_trouvee:
        salle = salle_trouvee.group(1).split(",")[0].strip()

    numero = ligne.find("td")
    identifiant = numero.get_text(strip=True) if numero else ""
    if not identifiant.isdigit():
        identifiant = str(rang)

    club = Club(
        pays="HR",
        numero=f"HR{identifiant}",
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=salle,
        site_web=_site(ligne),
        ligue_code="HR-HSTS",
        ligue_nom="Hrvatski stolnoteniski savez",
        dep=zone_postale(code_postal),
        dep_nom=f"HR {code_postal[:2]}" if code_postal else "",
        source_donnees=f"HSTS (clubs enregistrés), club {identifiant}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def liste_des_clubs(client: Client, limite: int = 0) -> list[Club]:
    """Charge l'annuaire et en tire un club par ligne."""
    reponse = client.get(ANNUAIRE, taille_max=20_000_000)
    if reponse is None:
        journal.error("annuaire croate inaccessible")
        return []
    soupe = BeautifulSoup(reponse.text, "html.parser")
    clubs: dict[str, Club] = {}
    for rang, ligne in enumerate(soupe.find_all("tr"), 1):
        club = club_depuis_ligne(ligne, rang)
        if club is not None:
            clubs[club.numero] = club
    liste = sorted(clubs.values(), key=lambda c: c.nom.lower())
    journal.info("annuaire croate : %d clubs, %d avec un site",
                 len(liste), sum(1 for c in liste if c.site_web))
    return liste[:limite] if limite else liste
