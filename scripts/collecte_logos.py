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
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as DelaiDepasse, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttlogos import catalogue, logos, referentiel  # noqa: E402
from ttlogos.reseau import Client  # noqa: E402

journal = logging.getLogger("logostt")
DOSSIER_SITE = referentiel.RACINE / "site"


def a_traiter(
    clubs: list[catalogue.Club], deps: set[str], forcer: bool, tout_le_monde: bool = False
) -> list[catalogue.Club]:
    selection = []
    for club in clubs:
        # « tous » couvre aussi les clubs étrangers, dont les regroupements ne sont pas
        # des départements français.
        if not tout_le_monde and club.dep not in deps:
            continue
        if not club.site_web:
            continue
        if "click-tt" in club.logo_source:
            continue  # logo officiel fourni par la fédération : rien à chercher ailleurs
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
    analyseur.add_argument("--timeout", type=float, default=10.0,
                           help="délai d'attente maximal par requête (s)")
    analyseur.add_argument("--budget", type=float, default=120.0,
                           help="durée maximale de la collecte des logos, en minutes")
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

    complet = len(deps) == len(referentiel.departements())
    selection = a_traiter(clubs, deps, arguments.forcer, tout_le_monde=complet)
    if arguments.limite:
        selection = selection[: arguments.limite]
    journal.info("%s club(s) à visiter sur %s au catalogue", len(selection), len(clubs))

    client = Client(delai=arguments.delai, timeout=arguments.timeout, duree_max=15.0)
    faits = 0
    debut = time.monotonic()
    epuise = False
    pool = ThreadPoolExecutor(max_workers=arguments.parallele)
    taches = {
        pool.submit(logos.recuperer_logo, club, client, DOSSIER_SITE / "logos"): club
        for club in selection
    }
    try:
        for tache in as_completed(taches, timeout=arguments.budget * 60):
            club = taches[tache]
            try:
                tache.result()
            except Exception as erreur:  # noqa: BLE001 - un site cassé ne doit pas arrêter la collecte
                journal.warning("%s (%s) : %s", club.nom, club.site_web, erreur)
                club.logo_statut = catalogue.LOGO_ABSENT
            faits += 1
            if faits % 25 == 0:
                journal.info("%s / %s traités en %.0f min", faits, len(selection),
                             (time.monotonic() - debut) / 60)
                catalogue.enregistrer(clubs)   # sauvegarde intermédiaire
    except DelaiDepasse:
        epuise = True
        journal.warning(
            "budget de %s min épuisé après %s / %s clubs : les sites restants seront "
            "repris à la prochaine collecte", arguments.budget, faits, len(selection))

    doublons = logos.dedoublonner(clubs, DOSSIER_SITE)
    orphelins = logos.supprimer_les_orphelins(clubs, DOSSIER_SITE)
    if doublons or orphelins:
        journal.info("%s logo(s) écarté(s) car partagé(s), %s fichier(s) orphelin(s) supprimé(s)",
                     doublons, orphelins)
    catalogue.enregistrer(clubs)
    recuperes = sum(1 for c in clubs if c.logo_statut == catalogue.LOGO_RECUPERE)
    favicons = sum(1 for c in clubs if c.logo_statut == catalogue.LOGO_FAVICON)
    journal.info("logos : %s récupérés, %s favicones, %s clubs au total", recuperes, favicons, len(clubs))
    if epuise:
        # Des fils d'exécution restent bloqués sur des serveurs qui ne répondent jamais :
        # le catalogue est enregistré, on rend la main sans les attendre.
        sys.stdout.flush()
        os._exit(0)
    pool.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
