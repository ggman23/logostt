#!/usr/bin/env python3
"""Reconnaissance des sources publiques allemandes (click-TT / nuLiga).

Ne collecte rien : affiche ce que répondent les pages et leur balisage, pour écrire
l'extracteur. Tourne dans GitHub Actions, seul endroit du projet à avoir un accès
internet complet.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

NULIGA = "cgi-bin/WebObjects/nuLigaTTDE.woa/wa"

PAGES = [
    ("Portail national click-TT", "https://dttb.click-tt.de/"),
    ("Recherche de clubs (national)", f"https://dttb.click-tt.de/{NULIGA}/clubSearch?federation=DTTB"),
    ("Recherche de clubs (Niedersachsen)", f"https://ttvn.click-tt.de/{NULIGA}/clubSearch?federation=TTVN"),
    ("Recherche de clubs (Westdeutscher)", f"https://wttv.click-tt.de/{NULIGA}/clubSearch?federation=WTTV"),
    ("Fiche club 10702", f"https://dttb.click-tt.de/{NULIGA}/clubInfoDisplay?club=10702"),
    ("Fiche club 11999", f"https://dttb.click-tt.de/{NULIGA}/clubInfoDisplay?club=11999"),
    ("Recherche avec critère vide", f"https://dttb.click-tt.de/{NULIGA}/clubSearch?federation=DTTB&club=&zip=&town="),
    ("Recherche par lettre", f"https://ttvn.click-tt.de/{NULIGA}/clubSearch?federation=TTVN&club=a&searchType=1"),
    ("Portail fédéral", "https://www.tischtennis.de/"),
]


def inspecter(nom: str, url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### {nom}\n    {url}")
    reponse = client.get(url, taille_max=6_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    html = reponse.text
    print(f"    -> HTTP {reponse.status_code} | {reponse.headers.get('Content-Type')} | {len(html)} caractères")
    if reponse.url != url:
        print(f"    -> redirigé vers {reponse.url}")
    soupe = BeautifulSoup(html, "html.parser")
    print("    Titre :", soupe.title.get_text(strip=True) if soupe.title else "(aucun)")

    for formulaire in soupe.find_all("form")[:3]:
        champs = [(c.get("name"), c.get("type") or c.name) for c in formulaire.find_all(("input", "select")) if c.get("name")]
        print(f"    Formulaire action={formulaire.get('action')} méthode={formulaire.get('method')} champs={champs[:14]}")

    liens = [a["href"] for a in soupe.find_all("a", href=True)]
    clubs = [l for l in liens if "clubInfoDisplay" in l or "club=" in l]
    print(f"    Liens vers des fiches club : {len(clubs)} — exemples {clubs[:5]}")
    externes = [l for l in liens if l.startswith("http") and "click-tt" not in l and "nuliga" not in l.lower()]
    print(f"    Liens externes : {len(externes)} — exemples {externes[:10]}")

    tableaux = soupe.find_all("table")
    print(f"    Tableaux : {len(tableaux)}")
    for tableau in tableaux[:2]:
        lignes = tableau.find_all("tr")[:4]
        for ligne in lignes:
            cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:38] for c in ligne.find_all(("th", "td"))]
            if cellules:
                print("      |", " | ".join(cellules[:7]))

    classes = Counter(c for b in soupe.find_all(True) for c in (b.get("class") or []))
    print("    Classes fréquentes :", classes.most_common(10))
    if "clubInfoDisplay" in url:
        principal = soupe.find("div", id="content-row1") or soupe.find("main") or soupe.find("body")
        lignes = [l for l in principal.prettify().splitlines() if l.strip()]
        print("    --- BALISAGE DE LA FICHE ---")
        for ligne in lignes[:90]:
            print("   ", ligne[:170])


def main() -> int:
    client = Client(delai=1.5, timeout=30)
    for nom, url in PAGES + [(f"URL fournie {i+1}", u) for i, u in enumerate(sys.argv[1:])]:
        try:
            inspecter(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
