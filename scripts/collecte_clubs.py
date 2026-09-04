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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ttlogos import carte, catalogue, clicktt, datasports, fftt, referentiel  # noqa: E402
from ttlogos.logos import recuperer_logo_heberge  # noqa: E402
from ttlogos.reseau import Client  # noqa: E402

journal = logging.getLogger("logostt")


def collecter_carte(client: Client, deps: list[str], tous: bool) -> list[catalogue.Club]:
    """Source par défaut : l'annuaire public de la FFTT, sans identifiants."""
    annuaire = carte.liste_des_clubs(client)
    if not annuaire:
        return []
    a_visiter = [
        entree for entree in annuaire
        # Le numéro d'affiliation porte le département : il sert de pré-filtre. Un numéro
        # inhabituel (Corse, outre-mer) est conservé, le département sera lu sur la fiche.
        if tous or carte.dep_probable(entree["numero"]) in deps
        or carte.dep_probable(entree["numero"]) not in referentiel.departements()
    ]
    journal.info("%s fiches club à lire sur %s", len(a_visiter), len(annuaire))
    attendus = set(deps)
    clubs: list[catalogue.Club] = []
    for rang, entree in enumerate(a_visiter, start=1):
        club = carte.fiche_club(client, entree["numero"], entree["nom"])
        if club and (tous or club.dep in attendus):
            clubs.append(club)
        if rang % 100 == 0:
            avec_site = sum(1 for c in clubs if c.site_web)
            journal.info("%s / %s fiches lues — %s clubs retenus, %s avec site web",
                         rang, len(a_visiter), len(clubs), avec_site)
    return clubs


def collecter_clicktt(
    client: Client, limite: int = 0, reprendre: bool = True, budget: float = 0
) -> list[catalogue.Club]:
    """Allemagne : annuaire public click-TT du DTTB, logo officiel compris.

    Neuf mille fiches ne tiennent pas toujours dans une seule exécution : le catalogue est
    enregistré au fil de l'eau et une relance reprend là où la précédente s'est arrêtée.
    """
    annuaire = clicktt.liste_des_clubs(client)
    if not annuaire:
        return []
    if limite:
        annuaire = annuaire[:limite]

    existants = catalogue.charger()
    deja = {c.numero for c in existants if c.pays == "DE"} if reprendre else set()
    a_lire = [e for e in annuaire if f"DE{e['id']}" not in deja]
    journal.info("%s clubs allemands recensés, %s déjà au catalogue, %s à lire",
                 len(annuaire), len(deja), len(a_lire))

    dossier_logos = referentiel.RACINE / "site" / "logos"
    clubs: list[catalogue.Club] = []
    debut = time.monotonic()

    for rang, entree in enumerate(a_lire, start=1):
        if budget and time.monotonic() - debut > budget * 60:
            # On rend la main avant que le workflow ne soit coupé : ce qui est collecté
            # est publié, et la prochaine collecte reprendra la suite de la liste.
            journal.info("budget de %s min atteint après %s fiches ; le reste sera repris "
                         "à la prochaine collecte", budget, rang - 1)
            break
        html = client.texte(clicktt.FICHE.format(club=entree["id"]), taille_max=4_000_000)
        if not html:
            continue
        club = clicktt.club_depuis_fiche(entree["id"], html, entree["nom"])
        if club is None:
            continue
        # Le logo officiel est servi par click-TT avec un jeton propre à la requête :
        # il faut le suivre tout de suite, avec la même session.
        recuperer_logo_heberge(club, client, html, dossier_logos)
        clubs.append(club)
        if rang % 200 == 0:
            avec_logo = sum(1 for c in clubs if c.logo_fichier)
            journal.info("%s / %s fiches lues — %s logos officiels récupérés",
                         rang, len(a_lire), avec_logo)
            # Sauvegarde intermédiaire : une exécution interrompue n'est jamais perdue.
            catalogue.enregistrer(
                catalogue.fusionner_pays(catalogue.charger(), clubs, "DE", remplacer=False))
    return clubs


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
        "--source", default="carte", choices=("carte", "clicktt", "fftt", "opendata"),
        help="carte : annuaire public FFTT (France, recommandé) ; "
             "clicktt : annuaire public du DTTB (Allemagne, logos officiels compris) ; "
             "fftt : API SmartPing (demande une clé) ; opendata : data.sports.gouv.fr",
    )
    analyseur.add_argument(
        "--sans-detail", action="store_true",
        help="ne pas récupérer la fiche détaillée (plus rapide, mais sans site web)",
    )
    analyseur.add_argument("--delai", type=float, default=0.5,
                           help="délai minimal entre deux requêtes vers le même serveur (s)")
    analyseur.add_argument("--limite", type=int, default=0,
                           help="s'arrêter après N clubs (mise au point)")
    analyseur.add_argument("--budget", type=float, default=0,
                           help="durée maximale de la collecte, en minutes (0 = sans limite)")
    analyseur.add_argument("--recommencer", action="store_true",
                           help="relire toutes les fiches au lieu de reprendre là où on s'était arrêté")
    analyseur.add_argument("--verbeux", action="store_true")
    arguments = analyseur.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if arguments.verbeux else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    deps = referentiel.codes_departements(arguments.dep)
    journal.info("collecte de %s département(s) via %s", len(deps), arguments.source)
    client = Client(delai=arguments.delai, timeout=30.0, duree_max=90.0)

    if arguments.source == "clicktt":
        nouveaux = collecter_clicktt(client, arguments.limite,
                                     reprendre=not arguments.recommencer,
                                     budget=arguments.budget)
    elif arguments.source == "carte":
        nouveaux = collecter_carte(client, deps, tous=len(deps) == len(referentiel.departements()))
    elif arguments.source == "fftt":
        nouveaux = collecter_fftt(client, deps, detail=not arguments.sans_detail)
    else:
        nouveaux = collecter_open_data(client, deps)

    if not nouveaux:
        journal.error("aucun club récupéré : source %s indisponible", arguments.source)
        return 1

    existants = catalogue.charger()
    if arguments.source == "clicktt":
        # Les clubs allemands ne sont pas découpés par département : on remplace
        # l'ensemble du pays et on laisse la France intacte.
        fusionnes = catalogue.fusionner_pays(existants, nouveaux, "DE",
                                             remplacer=arguments.recommencer)
    else:
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
