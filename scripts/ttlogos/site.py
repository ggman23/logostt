"""Génération des données consommées par le site (site/data/*.json)."""

from __future__ import annotations

import json
from pathlib import Path

from . import catalogue, referentiel
from .catalogue import Club

DOSSIER_SITE = referentiel.RACINE / "site"

# Familles de couleurs proposées comme filtre dans la galerie.
FAMILLES = [
    ("rouge", (0, 15), (25, 100)),
    ("orange", (15, 45), (25, 100)),
    ("jaune", (45, 70), (25, 100)),
    ("vert", (70, 165), (20, 100)),
    ("cyan", (165, 195), (20, 100)),
    ("bleu", (195, 255), (20, 100)),
    ("violet", (255, 290), (20, 100)),
    ("rose", (290, 345), (20, 100)),
    ("rouge", (345, 360), (25, 100)),
]


def famille_couleur(hexa: str) -> str:
    """Range une couleur dans une famille (bleu, rouge…) ou « neutre »."""
    try:
        rouge, vert, bleu = (int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (ValueError, IndexError):
        return ""
    maxi, mini = max(rouge, vert, bleu), min(rouge, vert, bleu)
    delta = maxi - mini
    saturation = 0 if maxi == 0 else delta / maxi
    if saturation < 0.18 or maxi < 0.12:
        return "neutre"
    if delta == 0:
        teinte = 0.0
    elif maxi == rouge:
        teinte = 60 * (((vert - bleu) / delta) % 6)
    elif maxi == vert:
        teinte = 60 * (((bleu - rouge) / delta) + 2)
    else:
        teinte = 60 * (((rouge - vert) / delta) + 4)
    for nom, (debut, fin), _ in FAMILLES:
        if debut <= teinte < fin:
            return nom
    return "neutre"


def club_en_dictionnaire(club: Club) -> dict:
    couleurs = [c for c in club.couleurs.split() if c]
    familles = []
    for couleur in couleurs:
        famille = famille_couleur(couleur)
        if famille and famille not in familles:
            familles.append(famille)
    return {
        "id": club.numero or catalogue.slug(f"{club.dep}-{club.nom}"),
        "pays": club.pays or "FR",
        "nom": club.nom,
        "ville": club.ville,
        "cp": club.code_postal,
        "dep": club.dep,
        "depNom": club.dep_nom,
        "ligue": club.ligue_code,
        "ligueNom": club.ligue_nom,
        "site": club.site_web,
        "logo": club.logo_fichier,
        "logoSource": club.logo_source,
        # « officiel » : logo déposé par le club auprès de sa fédération, donc sûr ;
        # « site » : logo extrait du site du club, donc trié automatiquement.
        "origine": "officiel" if "click-tt" in club.logo_source else (
            "site" if club.logo_fichier else ""),
        "statut": club.logo_statut,
        "couleurs": couleurs,
        "familles": familles,
        "fond": club.fond,
    }


def statistiques(clubs: list[Club]) -> dict:
    """Comptes par pays, ligue et département, pour alimenter les filtres du site."""
    pays = {
        "FR": {"code": "FR", "nom": "France", "ligues": _ligues_de_france()},
        "DE": {"code": "DE", "nom": "Allemagne", "ligues": {}},
        "CH": {"code": "CH", "nom": "Suisse", "ligues": {}},
    }
    for club in clubs:
        groupe = pays.setdefault(
            club.pays or "FR", {"code": club.pays, "nom": club.pays, "ligues": {}}
        )
        ligue = groupe["ligues"].get(club.ligue_code)
        if ligue is None:
            # Hors France, les ligues et les regroupements sont ceux que la source annonce.
            ligue = groupe["ligues"][club.ligue_code] = {
                "code": club.ligue_code,
                "nom": club.ligue_nom or club.ligue_code,
                "zone": "",
                "clubs": 0, "logos": 0, "sites": 0,
                "departements": {},
            }
        departement = ligue["departements"].get(club.dep)
        if departement is None:
            departement = ligue["departements"][club.dep] = {
                "dep": club.dep, "nom": club.dep_nom or club.dep,
                "clubs": 0, "logos": 0, "sites": 0,
            }
        avec_logo = club.logo_statut in {catalogue.LOGO_RECUPERE, catalogue.LOGO_FAVICON}
        for compteur in (ligue, departement):
            compteur["clubs"] += 1
            compteur["logos"] += int(avec_logo)
            compteur["sites"] += int(bool(club.site_web))

    resultat = []
    for groupe in pays.values():
        ligues = []
        for ligue in groupe["ligues"].values():
            ligue = dict(ligue)
            ligue["departements"] = sorted(
                ligue["departements"].values(), key=lambda d: d["dep"]
            )
            ligues.append(ligue)
        if not any(l["clubs"] for l in ligues):
            continue
        resultat.append({
            "code": groupe["code"],
            "nom": groupe["nom"],
            "clubs": sum(l["clubs"] for l in ligues),
            "sites": sum(l["sites"] for l in ligues),
            "logos": sum(l["logos"] for l in ligues),
            "ligues": ligues,
        })

    return {
        "clubs": len(clubs),
        "logos": sum(1 for c in clubs
                     if c.logo_statut in {catalogue.LOGO_RECUPERE, catalogue.LOGO_FAVICON}),
        "sites": sum(1 for c in clubs if c.site_web),
        "pays": resultat,
        # Compatibilité : la liste des ligues françaises reste accessible à plat.
        "ligues": next((p["ligues"] for p in resultat if p["code"] == "FR"), []),
    }


def _ligues_de_france() -> dict:
    """Les ligues françaises viennent du référentiel, pour rester dans l'ordre officiel."""
    return {
        ligue["code"]: {
            "code": ligue["code"],
            "nom": ligue["nom"],
            "zone": ligue["zone"],
            "clubs": 0, "logos": 0, "sites": 0,
            "departements": {
                d["dep"]: {"dep": d["dep"], "nom": d["nom"], "clubs": 0, "logos": 0, "sites": 0}
                for d in ligue["departements"]
            },
        }
        for ligue in referentiel.ligues()
    }


def construire(clubs: list[Club], dossier: Path = DOSSIER_SITE) -> dict:
    """Écrit site/data/clubs.json et site/data/stats.json."""
    donnees = dossier / "data"
    donnees.mkdir(parents=True, exist_ok=True)
    fiches = [club_en_dictionnaire(club) for club in catalogue.trier(clubs)]
    stats = statistiques(clubs)
    (donnees / "clubs.json").write_text(
        json.dumps({"maj": catalogue.aujourdhui(), "clubs": fiches}, ensure_ascii=False),
        encoding="utf-8",
    )
    (donnees / "stats.json").write_text(
        json.dumps({"maj": catalogue.aujourdhui(), **stats}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return stats
