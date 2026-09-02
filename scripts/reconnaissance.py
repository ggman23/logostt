#!/usr/bin/env python3
"""Inspecte la structure des pages publiques de la FFTT (carte.fftt.com).

Ce script ne collecte rien : il affiche le balisage réel des pages afin d'écrire un
extracteur juste. Il tourne dans GitHub Actions, seul endroit de ce projet à avoir
un accès internet complet.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

PAGES = [
    ("Carte des clubs", "https://carte.fftt.com/"),
    ("Annuaire des organismes", "https://carte.fftt.com/organismes"),
    ("Recherche par comité (formulaire)", "https://carte.fftt.com/organismes?type=committee&q=cher"),
    ("Carte filtrée sur une ville", "https://carte.fftt.com/?q=Bourges"),
]


def inspecter(nom: str, url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### {nom}\n    {url}")
    reponse = client.get(url, taille_max=6_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    html = reponse.text
    print(f"    -> HTTP {reponse.status_code} | {len(html)} caractères")
    soupe = BeautifulSoup(html, "html.parser")

    # Quels liens sortent du domaine fédéral ? Ce sont les sites des clubs.
    externes = [
        a["href"] for a in soupe.find_all("a", href=True)
        if a["href"].startswith("http") and "fftt.com" not in a["href"]
    ]
    print(f"    Liens externes : {len(externes)} — exemples : {externes[:12]}")
    titres = Counter(
        re.sub(r"\s+", " ", (a.get("title") or a.get("aria-label") or "")).split(" de ")[0]
        for a in soupe.find_all("a")
        if a.get("title") or a.get("aria-label")
    )
    print(f"    Intitulés de liens (title/aria-label) : {titres.most_common(10)}")

    # Structure d'une fiche club : on isole le bloc contenant un numéro d'affiliation.
    numero = re.search(r"\b(\d{8})\b", html)
    if numero:
        cible = soupe.find(string=re.compile(numero.group(1)))
        bloc = cible.parent if cible else None
        for _ in range(4):
            if bloc is None or len(bloc.get_text(strip=True)) > 120:
                break
            bloc = bloc.parent
        if bloc is not None:
            extrait = re.sub(r"\n\s*\n", "\n", bloc.prettify())
            print("    --- BALISAGE D'UNE FICHE CLUB ---")
            print("\n".join("    " + ligne for ligne in extrait.splitlines()[:70]))

    # Classes CSS les plus fréquentes : indiquent le conteneur répété des clubs.
    classes = Counter(
        classe for balise in soupe.find_all(True) for classe in (balise.get("class") or [])
    )
    print(f"    Classes fréquentes : {classes.most_common(14)}")

    # Données éventuellement injectées en JSON dans la page.
    for motif in (r"data-[a-z-]*club[a-z-]*=", r"window\.__[A-Z_]+", r"application/json"):
        trouves = sorted(set(re.findall(motif, html)))[:6]
        if trouves:
            print(f"    Motif {motif} : {trouves}")
    for balise in soupe.find_all("script", type=re.compile("json")):
        contenu = (balise.string or "")[:800]
        if contenu.strip():
            print(f"    JSON embarqué ({balise.get('id')}) : {contenu}")


def main() -> int:
    client = Client(delai=1.5, timeout=45)
    pages = PAGES + [(f"URL fournie {i + 1}", url) for i, url in enumerate(sys.argv[1:])]
    for nom, url in pages:
        try:
            inspecter(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
