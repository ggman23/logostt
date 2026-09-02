"""Source publique de la FFTT : l'annuaire des clubs et leurs fiches, sans identifiants.

Deux pages suffisent à reconstituer le catalogue national :

* ``carte.fftt.com/organismes`` liste en une seule page tous les clubs affiliés
  (numéro d'affiliation et nom), regroupés par comité départemental ;
* ``inscriptionenligne.fftt.com/club/<numéro>`` est la fiche publique d'un club :
  comité, ligue, salle, adresse et — c'est ce qui nous intéresse — le lien vers son
  site internet.

Seules les informations relatives au club sont retenues : la fiche affiche aussi les
coordonnées d'un correspondant (nom, téléphone, courriel), qui sont des données
personnelles et ne sont jamais extraites ni enregistrées.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from . import catalogue, referentiel
from .catalogue import Club
from .reseau import Client

journal = logging.getLogger("logostt")

ANNUAIRE = "https://carte.fftt.com/organismes"
FICHE = "https://inscriptionenligne.fftt.com/club/{numero}"

# Liens communs à toutes les fiches : ce ne sont pas les sites des clubs.
DOMAINES_IGNORES = re.compile(
    r"(^|\.)(fftt\.com|fftt\.fr|sportetfondations\.fr|youtube\.com|instagram\.com|"
    r"facebook\.com|x\.com|twitter\.com|linkedin\.com|tiktok\.com|flickr\.com|"
    r"google\.[a-z.]+|apple\.com)$",
    re.I,
)


def liste_des_clubs(client: Client) -> list[dict[str, str]]:
    """Tous les clubs affiliés (numéro et nom), lus dans l'annuaire public."""
    html = client.texte(ANNUAIRE, taille_max=16_000_000)
    if not html:
        journal.error("annuaire des organismes inaccessible : %s", ANNUAIRE)
        return []
    soupe = BeautifulSoup(html, "html.parser")
    clubs: dict[str, str] = {}
    for lien in soupe.select("a[href*='/club/']"):
        correspondance = re.search(r"/club/(\d+)", lien["href"])
        if not correspondance:
            continue
        identifiant = lien.find(class_="committee-clubs__identifier")
        nom = lien.find(class_="committee-clubs__name")
        numero = (identifiant.get_text(strip=True) if identifiant else "") or correspondance.group(1)
        libelle = nom.get_text(" ", strip=True) if nom else ""
        if libelle:
            clubs[numero] = re.sub(r"\s+", " ", libelle)
    journal.info("annuaire public : %s clubs affiliés", len(clubs))
    return [{"numero": numero, "nom": nom} for numero, nom in sorted(clubs.items())]


def dep_probable(numero: str) -> str:
    """Département déduit du numéro d'affiliation (3e et 4e chiffres), à confirmer."""
    return referentiel.normaliser_dep(numero[2:4]) if len(numero) >= 4 else ""


def _carte(soupe: BeautifulSoup, titre: str) -> Tag | None:
    """Retrouve le bloc d'information dont l'intitulé est donné (« Liens », « Salle »…)."""
    for entete in soupe.find_all(class_="plugin-title-small"):
        if entete.get_text(strip=True).lower() == titre.lower():
            return entete.parent
    return None


def _site_du_club(soupe: BeautifulSoup) -> str:
    bloc = _carte(soupe, "Liens")
    if bloc is None:
        return ""
    for lien in bloc.find_all("a", href=True):
        adresse = lien["href"].strip()
        if adresse.startswith("//"):
            adresse = "https:" + adresse
        if not adresse.lower().startswith("http"):
            continue
        if DOMAINES_IGNORES.search(catalogue.domaine_de(adresse)):
            continue
        return catalogue.normaliser_url(adresse)
    return ""


def _salle(soupe: BeautifulSoup) -> tuple[str, str, str]:
    """Renvoie (salle et adresse, code postal, ville)."""
    bloc = _carte(soupe, "Salle")
    if bloc is None:
        return "", "", ""
    info = bloc.find(class_="salle-info") or bloc
    texte = re.sub(r"\s+", " ", info.get_text(" ", strip=True)).strip()
    lieu = re.search(r"(\d{5})\s+([^\d]{2,60})$", texte)
    if not lieu:
        return texte, "", ""
    code_postal, ville = lieu.group(1), lieu.group(2).strip(" ,").title()
    return texte[: lieu.start()].strip(" ,-"), code_postal, ville


def club_depuis_fiche(numero: str, html: str, nom_connu: str = "") -> Club | None:
    """Construit un club à partir du HTML de sa fiche publique."""
    soupe = BeautifulSoup(html, "html.parser")
    entete = soupe.find(class_="club-heading")
    if entete is None:
        return None
    titre = re.sub(r"\s+", " ", entete.get_text(" ", strip=True))
    nom = re.sub(r"\s*N°\s*:?\s*\d+\s*$", "", titre).strip() or nom_connu
    if not nom:
        return None

    salle, code_postal, ville = _salle(soupe)
    club = Club(
        numero=numero,
        nom=nom,
        ville=ville,
        code_postal=code_postal,
        salle=salle,
        site_web=_site_du_club(soupe),
        source_donnees="annuaire public FFTT (carte.fftt.com)",
        maj=catalogue.aujourdhui(),
    )
    if not club.code_postal:
        club.dep = dep_probable(numero)
    club.completer_geographie()
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    return club


def fiche_club(client: Client, numero: str, nom_connu: str = "") -> Club | None:
    html = client.texte(FICHE.format(numero=numero), taille_max=4_000_000)
    if not html:
        return None
    return club_depuis_fiche(numero, html, nom_connu)
