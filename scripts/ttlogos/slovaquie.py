"""Clubs slovaques : l'annuaire de la SSTZ, qui tient en une page.

La fédération publie ses 832 clubs sur une même page, un par carte, avec le nom du
club et — pour une partie d'entre eux — l'adresse de son site, sous l'intitulé
« STRÁNKA KLUBU ».

Chaque carte porte aussi un courriel sous « EMAIL KLUBU » : il n'est jamais enregistré.

Page : https://www.sstz.sk/kluby
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

ANNUAIRE = "https://www.sstz.sk/kluby"

# Liens présents dans une carte sans être le site du club.
NON_CLUB = re.compile(r"sstz\.sk|facebook|instagram|youtube|twitter|x\.com|linkedin|"
                      r"google|w3\.org|tipos", re.I)


def _site(carte: Tag) -> str:
    """Adresse du site du club, prise sous l'intitulé « STRÁNKA KLUBU »."""
    adresse = ""
    for etiquette in carte.find_all("span"):
        if "STRÁNKA" in etiquette.get_text(" ", strip=True).upper():
            voisin = etiquette.find_next("a", href=True)
            if voisin is not None:
                adresse = voisin["href"].strip()
            break
    if not adresse:
        for lien in carte.find_all("a", href=True):
            candidat = lien["href"].strip()
            if candidat.startswith(("http://", "https://")) and not NON_CLUB.search(candidat):
                adresse = candidat
                break
    if not adresse:
        return ""
    # Quelques fiches empilent deux protocoles (« http://https://exemple.sk ») :
    # seul le dernier compte.
    dernier = max(adresse.rfind("http://"), adresse.rfind("https://"))
    if dernier > 0:
        adresse = adresse[dernier:]
    if not adresse.startswith(("http://", "https://")):
        adresse = "http://" + adresse
    return adresse


def club_depuis_carte(carte: Tag, rang: int = 0) -> Club | None:
    """Construit un club à partir d'une carte de l'annuaire."""
    titre = carte.find(("h2", "h3", "h4", "h5"))
    if titre is None:
        return None
    nom = re.sub(r"\s+", " ", titre.get_text(" ", strip=True))
    # Les cartes de service (« Počet: 832 », « Menu ») ne sont pas des clubs.
    if not nom or len(nom) < 3 or re.match(r"^(Menu|Počet|Filter)", nom, re.I):
        return None

    club = Club(
        pays="SK",
        numero=f"SK{rang}",
        nom=nom,
        site_web=_site(carte),
        ligue_code="SK-SSTZ",
        ligue_nom="Slovenský stolnotenisový zväz",
        source_donnees=f"SSTZ (annuaire des clubs), club {rang}",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def liste_des_clubs(client: Client, limite: int = 0) -> list[Club]:
    """Charge l'annuaire et en tire un club par carte."""
    reponse = client.get(ANNUAIRE, taille_max=20_000_000)
    if reponse is None:
        journal.error("annuaire slovaque inaccessible")
        return []
    soupe = BeautifulSoup(reponse.text, "html.parser")
    cartes = soupe.select("div.card")
    journal.info("annuaire slovaque : %d cartes", len(cartes))
    clubs: dict[str, Club] = {}
    for rang, carte in enumerate(cartes, 1):
        club = club_depuis_carte(carte, rang)
        if club is not None:
            # Deux cartes portant le même nom sont la même association.
            cle = catalogue.slug(club.nom)
            if cle not in clubs:
                club.numero = f"SK{cle[:24]}"
                clubs[cle] = club
    liste = sorted(clubs.values(), key=lambda c: c.nom.lower())
    journal.info("annuaire slovaque : %d clubs, %d avec un site",
                 len(liste), sum(1 for c in liste if c.site_web))
    return liste[:limite] if limite else liste
