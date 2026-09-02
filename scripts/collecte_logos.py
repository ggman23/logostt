#!/usr/bin/env python3
"""Visite le site de chaque club et en extrait le logo.

Exemples :
    python3 scripts/collecte_logos.py --dep 75           # un département
    python3 scripts/collecte_logos.py --dep tous         # toute la France
    python3 scripts/collecte_logos.py --dep 44 --forcer  # refaire les logos déjà connus
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttlogos import catalogue, logos, referentiel  # noqa: E402
from ttlogos.reseau import Client  # noqa: E402

journal = logging.getLogger("logostt")
DOSSIER_SITE = referentiel.RACINE / "site"


def a_traiter(clubs: list[catalogue.Club], deps: set[str], forcer: bool) -> list[catalogue.Club]:
    selection = []
    for club in clubs:
        if club.dep not in deps or not club.site_web:
            continue
        deja = club.logo_statut in {catalogue.LOGO_RECUPERE, catalogue.LOGO_FAVICON}
        fichier_present = deja and (DOSSIER_SITE / club.logo_fichier).exists()
        if forcer or not fichier_present:
            selection.append(club)
    return selection


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--dep", default="tous", help="département, ligue, « metropole » ou « tous »")
    analyseur.add_argument("--forcer", action="store_true", help="retélécharger les logos déjà connus")
    analyseur.add_argument("--limite", type=int, default=0, help="s'arrêter après N clubs (essais)")
    analyseur.add_argument("--parallele", type=int, default=8, help="nombre de sites visités en parallèle")
    analyseur.add_argument("--delai", type=float, default=1.5, help="délai minimal entre deux requêtes vers un même domaine (s)")
    analyseur.add_argument("--verbeux", action="store_true")
    arguments = analyseur.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if arguments.verbeux else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    deps = set(referentiel.codes_departements(arguments.dep))
    clubs = catalogue.charger()
    if not clubs:
        journal.error("catalogue vide : lancez d'abord scripts/collecte_clubs.py")
        return 1

    selection = a_traiter(clubs, deps, arguments.forcer)
    if arguments.limite:
        selection = selection[: arguments.limite]
    journal.info("%s club(s) à visiter sur %s au catalogue", len(selection), len(clubs))

    client = Client(delai=arguments.delai)
    faits = 0
    with ThreadPoolExecutor(max_workers=arguments.parallele) as pool:
        taches = {
            pool.submit(logos.recuperer_logo, club, client, DOSSIER_SITE / "logos"): club
            for club in selection
        }
        for tache in as_completed(taches):
            club = taches[tache]
            try:
                tache.result()
            except Exception as erreur:  # noqa: BLE001 - un site cassé ne doit pas arrêter la collecte
                journal.warning("%s (%s) : %s", club.nom, club.site_web, erreur)
                club.logo_statut = catalogue.LOGO_ABSENT
            faits += 1
            if faits % 25 == 0:
                journal.info("%s / %s traités", faits, len(selection))
                catalogue.enregistrer(clubs)   # sauvegarde intermédiaire

    catalogue.enregistrer(clubs)
    recuperes = sum(1 for c in clubs if c.logo_statut == catalogue.LOGO_RECUPERE)
    favicons = sum(1 for c in clubs if c.logo_statut == catalogue.LOGO_FAVICON)
    journal.info("logos : %s récupérés, %s favicones, %s clubs au total", recuperes, favicons, len(clubs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
