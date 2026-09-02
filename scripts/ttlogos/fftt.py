"""Client de l'API SmartPing de la FFTT (liste des clubs et fiches détaillées).

L'API officielle demande un identifiant et une clé délivrés gratuitement par la FFTT
(formulaire sur https://www.fftt.com/api/). Renseignez-les dans les variables
d'environnement FFTT_API_ID et FFTT_API_KEY. Sans identifiants, on tente les anciens
points d'entrée mobiles, ouverts historiquement mais qui peuvent être fermés.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import xml.etree.ElementTree as ET

from . import catalogue
from .catalogue import Club
from .reseau import Client

journal = logging.getLogger("logostt")

BASE_AUTHENTIFIEE = "https://apiv2.fftt.com/mobile/pxml"
BASE_OUVERTE = "https://www.fftt.com/mobile/pxml"


class ApiFFTT:
    def __init__(self, client: Client, identifiant: str = "", cle: str = "") -> None:
        self.client = client
        self.identifiant = identifiant or os.environ.get("FFTT_API_ID", "")
        self.cle = cle or os.environ.get("FFTT_API_KEY", "")

    @property
    def authentifiee(self) -> bool:
        return bool(self.identifiant and self.cle)

    def _url(self, service: str, parametres: dict[str, str]) -> str:
        arguments = dict(parametres)
        if self.authentifiee:
            horodatage = str(round(time.time() * 1000))
            signature = hmac.new(
                hashlib.md5(self.cle.encode()).hexdigest().encode(),
                horodatage.encode(),
                hashlib.sha1,
            ).hexdigest()
            arguments = {
                "serie": self.identifiant,
                "tm": horodatage,
                "tmc": signature,
                "id": self.identifiant,
                **arguments,
            }
            base = BASE_AUTHENTIFIEE
        else:
            base = BASE_OUVERTE
        requete = "&".join(f"{cle}={valeur}" for cle, valeur in arguments.items())
        return f"{base}/{service}.php?{requete}"

    def _xml(self, service: str, parametres: dict[str, str]) -> ET.Element | None:
        contenu = self.client.texte(self._url(service, parametres))
        if not contenu.strip().startswith("<"):
            if contenu:
                journal.warning("réponse inattendue de %s : %s", service, contenu[:120])
            return None
        try:
            return ET.fromstring(contenu)
        except ET.ParseError as erreur:
            journal.warning("XML illisible pour %s : %s", service, erreur)
            return None

    def clubs_du_departement(self, dep: str) -> list[dict[str, str]]:
        racine = self._xml("xml_club_dep2", {"dep": dep})
        if racine is None:
            return []
        clubs = []
        for noeud in racine.findall("club"):
            clubs.append({
                "numero": (noeud.findtext("numero") or "").strip(),
                "nom": (noeud.findtext("nom") or "").strip(),
            })
        return [c for c in clubs if c["numero"]]

    def fiche_club(self, numero: str) -> dict[str, str]:
        racine = self._xml("xml_club_detail", {"club": numero})
        if racine is None:
            return {}
        noeud = racine.find("club")
        if noeud is None:
            return {}
        return {
            (enfant.tag or ""): (enfant.text or "").strip() for enfant in noeud
        }


def club_depuis_fiche(dep: str, resume: dict[str, str], fiche: dict[str, str]) -> Club:
    """Construit un Club à partir d'une fiche xml_club_detail."""
    club = Club(
        numero=resume.get("numero", "") or fiche.get("numero", ""),
        nom=fiche.get("nom") or resume.get("nom", ""),
        dep=dep,
        ville=(fiche.get("villesalle") or "").title(),
        code_postal=fiche.get("codepsalle", ""),
        salle=fiche.get("nomsalle", ""),
        site_web=catalogue.normaliser_url(fiche.get("web", "")),
        latitude=fiche.get("latitude", ""),
        longitude=fiche.get("longitude", ""),
        source_donnees="API FFTT SmartPing",
        maj=catalogue.aujourdhui(),
    )
    club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
    club.completer_geographie()
    return club
