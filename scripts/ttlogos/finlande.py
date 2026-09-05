"""Clubs finlandais : les présentations de clubs de la SPTL.

La fédération consacre une page à présenter ses clubs, ville par ville, et y héberge
elle-même leur logo. C'est le cas le plus favorable : la source est sûre, il n'y a
aucun tri à faire, contrairement aux images glanées sur le site d'un club.

La page est faite d'une suite de titres : un titre de ville, puis un titre par club de
cette ville, suivi de son logo, de sa salle et de l'adresse de son site.

Page : https://www.sptl.fi/sptl_uudet/?cat=81
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from . import catalogue
from .catalogue import Club
from .reseau import Client, journal

PRESENTATIONS = "https://www.sptl.fi/sptl_uudet/?cat=81"

# Liens présents dans une présentation sans être le site du club.
NON_CLUB = re.compile(r"sptl\.fi|facebook|instagram|youtube|twitter|x\.com|linkedin|"
                      r"tiktok|google|w3\.org|spotify|wordpress", re.I)
# Les vignettes que le thème fabrique : « -300x300 », « -253x300 »…
VIGNETTE = re.compile(r"-\d{2,4}x\d{2,4}(?=\.[a-z]{3,4}$)", re.I)


class Presentation:
    """Un titre de la page et tout ce qui le suit jusqu'au titre suivant."""

    def __init__(self, titre: str) -> None:
        self.titre = titre
        self.images: list[str] = []
        self.liens: list[str] = []
        self.texte: list[str] = []

    @property
    def est_un_club(self) -> bool:
        """Un titre de ville n'est suivi de rien ; un club, de son logo ou de sa salle."""
        return bool(self.images or self.liens or self.texte)


def decouper(contenu: Tag) -> list[Presentation]:
    """Découpe la page en présentations, une par titre rencontré."""
    presentations: list[Presentation] = []
    courante: Presentation | None = None
    for element in contenu.descendants:
        if not isinstance(element, Tag):
            continue
        if element.name in ("h1", "h2", "h3", "h4"):
            courante = Presentation(re.sub(r"\s+", " ", element.get_text(" ", strip=True)))
            presentations.append(courante)
        elif courante is None:
            continue
        elif element.name == "img" and element.get("src"):
            courante.images.append(element["src"])
        elif element.name == "a" and element.get("href", "").startswith("http"):
            courante.liens.append(element["href"])
        elif element.name == "p":
            texte = re.sub(r"\s+", " ", element.get_text(" ", strip=True))
            if texte:
                courante.texte.append(texte)
    return presentations


def _logo(presentation: Presentation) -> str:
    """Adresse du logo, en préférant l'image pleine taille à sa vignette."""
    hebergees = [i for i in presentation.images if "wp-content/uploads" in i]
    if not hebergees:
        return ""
    pleines = [i for i in hebergees if not VIGNETTE.search(i)]
    return (pleines or hebergees)[0]


def _site(presentation: Presentation) -> str:
    for adresse in presentation.liens:
        if not NON_CLUB.search(adresse):
            return adresse
    return ""


def clubs_depuis_page(html: str) -> list[tuple[Club, str]]:
    """Rend les clubs de la page, chacun avec l'adresse de son logo hébergé."""
    soupe = BeautifulSoup(html, "html.parser")
    contenu = soupe.select_one("div.entry-content") or soupe
    ville = ""
    resultat: list[tuple[Club, str]] = []
    for presentation in decouper(contenu):
        if not presentation.est_un_club:
            # Un titre seul annonce la ville des clubs qui suivent.
            if presentation.titre and len(presentation.titre) < 40:
                ville = presentation.titre
            continue
        nom = presentation.titre
        if not nom or len(nom) < 3:
            continue
        salle = ""
        for ligne in presentation.texte:
            trouve = re.match(r"Kotisali:\s*(.{2,70})", ligne)
            if trouve:
                salle = trouve.group(1).strip()
                break
        club = Club(
            pays="FI",
            numero=f"FI{catalogue.slug(nom)[:24]}",
            nom=nom,
            ville=ville,
            salle=salle,
            site_web=_site(presentation),
            ligue_code="FI-SPTL",
            ligue_nom="Suomen Pöytätennisliitto",
            source_donnees=f"SPTL (présentations de clubs), {nom}",
            maj=catalogue.aujourdhui(),
        )
        club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
        resultat.append((club, _logo(presentation)))
    return resultat


def liste_des_clubs(client: Client, limite: int = 0) -> list[tuple[Club, str]]:
    """Charge la page de présentations et rend les clubs avec l'adresse de leur logo."""
    reponse = client.get(PRESENTATIONS, taille_max=20_000_000)
    if reponse is None:
        journal.error("présentations finlandaises inaccessibles")
        return []
    couples = clubs_depuis_page(reponse.text)
    journal.info("annuaire finlandais : %d clubs, %d avec un logo hébergé, %d avec un site",
                 len(couples), sum(1 for _, logo in couples if logo),
                 sum(1 for club, _ in couples if club.site_web))
    return couples[:limite] if limite else couples
