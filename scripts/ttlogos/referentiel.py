"""Référentiel des ligues régionales et de leurs départements."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
FICHIER_LIGUES = RACINE / "referentiel" / "ligues.json"


@dataclass(frozen=True)
class Departement:
    dep: str
    nom: str
    ligue_code: str
    ligue_nom: str
    zone: str


@lru_cache(maxsize=1)
def departements() -> dict[str, Departement]:
    """Retourne les départements indexés par code (« 75 », « 2A », « 974 »…)."""
    brut = json.loads(FICHIER_LIGUES.read_text(encoding="utf-8"))
    index: dict[str, Departement] = {}
    for ligue in brut["ligues"]:
        for dep in ligue["departements"]:
            index[dep["dep"]] = Departement(
                dep=dep["dep"],
                nom=dep["nom"],
                ligue_code=ligue["code"],
                ligue_nom=ligue["nom"],
                zone=ligue["zone"],
            )
    return index


@lru_cache(maxsize=1)
def ligues() -> list[dict]:
    """Liste des ligues, dans l'ordre du référentiel."""
    return json.loads(FICHIER_LIGUES.read_text(encoding="utf-8"))["ligues"]


def normaliser_dep(valeur: str) -> str:
    """Normalise un code département : « 5 » -> « 05 », « 2a » -> « 2A »."""
    valeur = (valeur or "").strip().upper()
    if not valeur:
        return ""
    if valeur.isdigit() and len(valeur) == 1:
        return valeur.zfill(2)
    return valeur


def departement(code: str) -> Departement | None:
    return departements().get(normaliser_dep(code))


def dep_depuis_code_postal(code_postal: str) -> str:
    """Déduit le département d'un code postal (gère la Corse et l'outre-mer)."""
    cp = (code_postal or "").strip()
    if len(cp) < 2 or not cp[:2].isdigit():
        return ""
    if cp.startswith("97") or cp.startswith("98"):
        return cp[:3]
    if cp.startswith("20"):
        # 20000-20199 et 20200-20620 : découpage approximatif Corse-du-Sud / Haute-Corse.
        try:
            numero = int(cp[:5])
        except ValueError:
            return "2A"
        return "2A" if numero < 20200 else "2B"
    return cp[:2]


def codes_departements(filtre: str | None = None) -> list[str]:
    """Codes départements à collecter. `filtre` accepte « 75 », « IDF », « metropole », « tous »."""
    tous = departements()
    if not filtre or filtre.lower() in {"tous", "toute", "france", "all"}:
        return list(tous)
    demandes: list[str] = []
    for morceau in filtre.split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        cle = morceau.upper()
        if cle in {"METROPOLE", "MÉTROPOLE"}:
            demandes += [d for d, v in tous.items() if v.zone == "metropole"]
        elif cle in {"OUTRE-MER", "OUTREMER", "DOM"}:
            demandes += [d for d, v in tous.items() if v.zone == "outre-mer"]
        elif any(v.ligue_code == cle for v in tous.values()):
            demandes += [d for d, v in tous.items() if v.ligue_code == cle]
        else:
            code = normaliser_dep(morceau)
            if code in tous:
                demandes.append(code)
            else:
                raise SystemExit(f"Code département ou ligue inconnu : {morceau}")
    # dédoublonnage en gardant l'ordre du référentiel
    retenus = set(demandes)
    return [d for d in tous if d in retenus]
