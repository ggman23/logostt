"""Source de secours sans identifiants : l'open data du ministère des Sports.

data.sports.gouv.fr publie le recensement des clubs des fédérations agréées via une API
Opendatasoft. On y trouve le nom, la commune et le département des clubs, mais pas leur
site web : cette source sert donc à obtenir une liste de clubs quand l'API FFTT n'est pas
accessible, les sites étant ensuite complétés à la main (data/corrections.csv).

Le schéma exact des jeux de données évolue ; le code découvre les champs plutôt que de
les coder en dur, et signale ce qu'il a trouvé.
"""

from __future__ import annotations

import json
import logging

from . import catalogue
from .catalogue import Club
from .reseau import Client

journal = logging.getLogger("logostt")

BASE = "https://data.sports.gouv.fr/api/explore/v2.1/catalog"
FEDERATION = "tennis de table"


def _json(client: Client, url: str) -> dict:
    contenu = client.texte(url)
    if not contenu:
        return {}
    try:
        return json.loads(contenu)
    except ValueError:
        journal.warning("réponse non JSON depuis %s", url[:120])
        return {}


def jeux_de_donnees(client: Client) -> list[str]:
    """Identifiants des jeux de données susceptibles de contenir la liste des clubs."""
    reponse = _json(client, f"{BASE}/datasets?limit=100&where=search(%22club%22)")
    return [
        jeu.get("dataset_id", "")
        for jeu in reponse.get("results", [])
        if jeu.get("dataset_id")
    ]


def _champ(enregistrement: dict, *motifs: str) -> str:
    """Retrouve la valeur d'un champ dont le nom contient l'un des motifs."""
    for motif in motifs:
        for cle, valeur in enregistrement.items():
            if motif in cle.lower() and isinstance(valeur, (str, int, float)) and str(valeur).strip():
                return str(valeur).strip()
    return ""


def clubs(client: Client, dataset: str, limite: int = 5000) -> list[Club]:
    """Télécharge les clubs de tennis de table d'un jeu de données Opendatasoft."""
    resultats: list[Club] = []
    offset = 0
    while offset < limite:
        url = (
            f"{BASE}/datasets/{dataset}/records?limit=100&offset={offset}"
            f"&where=search(%22{FEDERATION.replace(' ', '%20')}%22)"
        )
        reponse = _json(client, url)
        lignes = reponse.get("results") or []
        if not lignes:
            break
        for ligne in lignes:
            aplati = {c: v for c, v in ligne.items() if not isinstance(v, (dict, list))}
            nom = _champ(aplati, "nom_club", "nomclub", "denomination", "libelle", "nom")
            if not nom:
                continue
            club = Club(
                numero=_champ(aplati, "numero", "code_club", "id_club", "siret"),
                nom=nom,
                ville=_champ(aplati, "commune", "ville", "libelle_commune").title(),
                code_postal=_champ(aplati, "code_postal", "cp"),
                dep=_champ(aplati, "dep", "departement"),
                latitude=_champ(aplati, "latitude", "lat"),
                longitude=_champ(aplati, "longitude", "lon"),
                source_donnees=f"data.sports.gouv.fr / {dataset}",
                maj=catalogue.aujourdhui(),
                logo_statut=catalogue.SITE_ABSENT,
            )
            club.completer_geographie()
            if club.dep:
                resultats.append(club)
        offset += 100
        if len(lignes) < 100:
            break
    return resultats
