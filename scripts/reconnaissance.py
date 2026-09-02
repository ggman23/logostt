#!/usr/bin/env python3
"""Relève le balisage exact d'une fiche club publique, pour écrire l'extracteur.

Ne collecte rien : affiche le HTML du contenu principal de deux fiches afin d'en tirer
des sélecteurs fiables et un échantillon de test.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

FICHES = [
    "https://inscriptionenligne.fftt.com/club/04180613",   # club avec site internet
    "https://inscriptionenligne.fftt.com/club/07750123",   # un club parisien, pour comparer
]


def afficher(url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### {url}")
    reponse = client.get(url, taille_max=4_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    soupe = BeautifulSoup(reponse.text, "html.parser")
    for inutile in soupe.find_all(("script", "style", "svg", "header", "footer", "nav")):
        inutile.decompose()
    principal = soupe.find("main") or soupe.find("body") or soupe
    lignes = [
        ligne for ligne in principal.prettify().splitlines()
        if ligne.strip() and not re.fullmatch(r"\s*</?(div|span|i|br)/?>\s*", ligne)
    ]
    print(f"    {len(lignes)} lignes de balisage utile")
    for ligne in lignes[:170]:
        print("   ", ligne[:190])


def main() -> int:
    client = Client(delai=1.5, timeout=45)
    for url in FICHES + sys.argv[1:]:
        try:
            afficher(url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
