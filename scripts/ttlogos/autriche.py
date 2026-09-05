"""Clubs autrichiens : l'annuaire de l'ÖTTV, qui tient en une seule page.

La fédération publie tous ses clubs sur une même page, chacun dans une carte qui donne
son nom, son sigle, son Landesverband, sa salle et — pour près de la moitié d'entre
eux — l'adresse de son site. Une requête suffit donc pour tout l'annuaire.

Ces cartes affichent aussi le nom, le téléphone et le courriel d'un correspondant :
ces données personnelles ne sont ni extraites ni enregistrées.

Page : https://www.oettv.org/organisation/vereine
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

ANNUAIRE = "https://www.oettv.org/organisation/vereine"

# Liens présents dans une carte sans être le site du club.
NON_CLUB = re.compile(r"google\.|oettv\.org|facebook|instagram|youtube|twitter|x\.com|"
                      r"linkedin|tiktok|maps\.|openstreetmap", re.I)
# « 5340 St. Gilgen » : les codes postaux autrichiens ont quatre chiffres.
ADRESSE = re.compile(r"\b(\d{4})\s+([A-Za-zÀ-ÿ][^\n,;]{1,40})")


def zone_postale(code_postal: str) -> str:
    """Regroupement géographique : les deux premiers chiffres du code postal."""
    if len(code_postal) < 2 or not code_postal[:2].isdigit():
        return ""
    return f"AT{code_postal[:2]}"


def code_ligue(sigle: str) -> str:
    """Code court et stable pour un Landesverband : « STTV » -> « AT-STTV »."""
    racine = catalogue.slug(sigle).upper()
    return f"AT-{racine}" if racine else ""


def _bloc_apres(carte: Tag, intitule: str) -> str:
    """Texte qui suit un intitulé de la carte (« Halle », « Kontakt »).

    L'adresse n'est cherchée que là : celle du correspondant, sous « Kontakt », ne doit
    jamais servir, et le reste de la carte contient d'autres nombres à quatre chiffres
    (le numéro de registre des associations, par exemple).
    """
    for etiquette in carte.find_all("div"):
        if etiquette.get_text(strip=True) == intitule and "text-muted" in (
                etiquette.get("class") or []):
            morceaux = []
            for suivant in etiquette.find_next_siblings():
                if suivant.name == "div" and suivant.get_text(strip=True) in (
                        "Kontakt", "Halle", "Anmerkung"):
                    break
                morceaux.append(suivant.get_text("\n", strip=True))
            return "\n".join(morceaux)
    return ""


def _site(carte: Tag) -> str:
    """Adresse du site du club, parmi les liens de la carte."""
    for lien in carte.find_all("a", href=True):
        adresse = lien["href"].strip()
        if adresse.startswith(("http://", "https://")) and not NON_CLUB.search(adresse):
            # Certaines fiches écrivent « http://Www.exemple.at » : l'hôte est insensible
            # à la casse, mais une adresse propre évite des doublons dans le catalogue.
            protocole, reste = adresse.split("://", 1)
            hote, _, chemin = reste.partition("/")
            return f"{protocole}://{hote.lower()}" + (f"/{chemin}" if chemin else "")
    return ""


def _coordonnees(carte: Tag) -> tuple[str, str]:
    """Latitude et longitude, que la fédération place dans son lien vers la carte."""
    for lien in carte.find_all("a", href=True):
        trouve = re.search(r"place/(-?\d+\.\d+),(-?\d+\.\d+)", lien["href"])
        if trouve:
            return trouve.group(1), trouve.group(2)
    return "", ""


def club_depuis_carte(carte: Tag) -> Club | None:
    """Construit un club à partir d'une carte de l'annuaire."""
    titre = carte.select_one("h3.card-title")
    if titre is None:
        return None
    nom_gras = titre.find("b")
    nom = (nom_gras or titre).get_text(" ", strip=True)
    if not nom:
        return None
    sigle_court = titre.find("div")
    sigle_court = sigle_court.get_text(strip=True) if sigle_court else ""

    lien_fiche = carte.find("a", href=re.compile(r"clubId%5D=(\d+)"))
    identifiant = re.search(r"clubId%5D=(\d+)", lien_fiche["href"]).group(1) if lien_fiche else ""
    if not identifiant:
        identifiant = catalogue.slug(sigle_court or nom)[:12]

    # Le Landesverband est le seul <span> de la carte à porter un intitulé complet.
    sigle_verband, nom_verband = "", ""
    for etiquette in carte.find_all("span"):
        if etiquette.get_text(strip=True).startswith("Landesverband"):
            valeur = etiquette.find_next("span")
            if valeur is not None:
                sigle_verband = valeur.get_text(strip=True)
                nom_verband = valeur.get("title") or sigle_verband
            break

    salle_texte = _bloc_apres(carte, "Halle")
    code_postal, ville = "", ""
    trouve = ADRESSE.search(salle_texte)
    if trouve:
        code_postal, ville = trouve.group(1), trouve.group(2).strip()
    premiere_ligne = [l for l in salle_texte.split("\n") if l.strip()]
    salle = premiere_ligne[0][:80] if premiere_ligne else ""

    latitude, longitude = _coordonnees(carte)
    club = Club(
        pays="AT",
        numero=f"AT{identifiant}",
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=salle,
        site_web=_site(carte),
        ligue_code=code_ligue(sigle_verband),
        ligue_nom=nom_verband or sigle_verband,
        dep=zone_postale(code_postal),
        dep_nom=f"PLZ {code_postal[:2]}" if code_postal else "",
        latitude=latitude,
        longitude=longitude,
        source_donnees=f"ÖTTV, club {identifiant}"
                       + (f" ({sigle_court})" if sigle_court else ""),
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def liste_des_clubs(client: Client, limite: int = 0) -> list[Club]:
    """Charge l'annuaire et en tire un club par carte."""
    reponse = client.get(ANNUAIRE, taille_max=20_000_000)
    if reponse is None:
        journal.error("annuaire autrichien inaccessible")
        return []
    soupe = BeautifulSoup(reponse.text, "html.parser")
    cartes = soupe.select("div.card")
    journal.info("annuaire autrichien : %d cartes", len(cartes))
    clubs: dict[str, Club] = {}
    for carte in cartes:
        club = club_depuis_carte(carte)
        if club is not None:
            clubs[club.numero] = club
    liste = sorted(clubs.values(), key=lambda c: c.nom.lower())
    journal.info("annuaire autrichien : %d clubs, %d avec un site",
                 len(liste), sum(1 for c in liste if c.site_web))
    return liste[:limite] if limite else liste
