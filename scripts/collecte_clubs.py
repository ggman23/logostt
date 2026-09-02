#!/usr/bin/env python3
"""Collecte la liste des clubs (nom, ville, site web) et met à jour data/clubs.csv.

Exemples :
    python3 scripts/collecte_clubs.py --dep 75            # un département
    python3 scripts/collecte_clubs.py --dep IDF           # toute une ligue
    python3 scripts/collecte_clubs.py --dep tous          # la France entière
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttlogos import catalogue, datasports, fftt, referentiel  # noqa: E402
from ttlogos.reseau import Client  # noqa: E402

journal = logging.getLogger("logostt")


def collecter_fftt(client: Client, deps: list[str], detail: bool) -> list[catalogue.Club]:
    api = fftt.ApiFFTT(client)
    if not api.authentifiee:
        journal.warning(
            "Aucun identifiant FFTT (FFTT_API_ID / FFTT_API_KEY) : essai des points "
            "d'entrée ouverts, qui peuvent être refusés par la fédération."
        )
    clubs: list[catalogue.Club] = []
    for dep in deps:
        info = referentiel.departement(dep)
        resumes = api.clubs_du_departement(dep)
        journal.info("%s (%s) : %s clubs", dep, info.nom if info else "?", len(resumes))
        for resume in resumes:
            fiche = api.fiche_club(resume["numero"]) if detail else {}
            clubs.append(fftt.club_depuis_fiche(dep, resume, fiche))
    return clubs


def collecter_open_data(client: Client, deps: list[str]) -> list[catalogue.Club]:
    jeux = datasports.jeux_de_donnees(client)
    journal.info("jeux de données candidats : %s", ", ".join(jeux[:10]) or "aucun")
    retenus: list[catalogue.Club] = []
    for jeu in jeux:
        trouves = datasports.clubs(client, jeu)
        if trouves:
            journal.info("%s clubs trouvés dans %s", len(trouves), jeu)
            retenus = trouves
            break
    a_garder = set(deps)
    return [club for club in retenus if club.dep in a_garder]


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument(
        "--dep", default="tous",
        help="département (75), ligue (IDF), « metropole », « outre-mer » ou « tous »",
    )
    analyseur.add_argument(
        "--source", default="fftt", choices=("fftt", "opendata"),
        help="fftt : API SmartPing (recommandé) ; opendata : data.sports.gouv.fr (secours)",
    )
    analyseur.add_argument(
        "--sans-detail", action="store_true",
        help="ne pas récupérer la fiche détaillée (plus rapide, mais sans site web)",
    )
    analyseur.add_argument("--delai", type=float, default=0.8, help="délai entre requêtes (s)")
    analyseur.add_argument("--verbeux", action="store_true")
    arguments = analyseur.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if arguments.verbeux else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    deps = referentiel.codes_departements(arguments.dep)
    journal.info("collecte de %s département(s) via %s", len(deps), arguments.source)
    client = Client(delai=arguments.delai)

    if arguments.source == "fftt":
        nouveaux = collecter_fftt(client, deps, detail=not arguments.sans_detail)
    else:
        nouveaux = collecter_open_data(client, deps)

    if not nouveaux:
        journal.error(
            "aucun club récupéré : vérifiez les identifiants FFTT ou essayez --source opendata"
        )
        return 1

    existants = catalogue.charger()
    fusionnes = catalogue.fusionner(existants, nouveaux, set(deps))
    fusionnes = catalogue.appliquer_corrections(fusionnes, catalogue.charger_corrections())
    catalogue.enregistrer(fusionnes)

    avec_site = sum(1 for club in fusionnes if club.site_web)
    journal.info(
        "catalogue : %s clubs (%s avec site web) -> %s",
        len(fusionnes), avec_site, catalogue.FICHIER_CLUBS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
