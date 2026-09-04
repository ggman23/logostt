#!/usr/bin/env python3
"""Lit le message d'erreur du flux anglais et dissèque la réponse du moteur AFTT."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def angleterre() -> None:
    titre("ANGLETERRE — que dit exactement le refus ?")
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR, "Accept": "application/json"})
    adresses = [
        "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs",
        "https://www.tabletennis365.com/tabletennisengland/api/openactive/v1/clubs",
        "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Sessions",
        "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/Clubs",
        "https://www.tabletennis365.com/Sites",
        "https://openactive.io/data-catalogs/data-catalog-collection.jsonld",
    ]
    for adresse in adresses:
        print(f"  — {adresse}")
        try:
            reponse = session.get(adresse, timeout=45)
        except Exception as erreur:  # noqa: BLE001
            print(f"    exception {type(erreur).__name__}: {erreur}")
            continue
        print(f"    HTTP {reponse.status_code} | {len(reponse.content)} octets |"
              f" {reponse.headers.get('Content-Type')}")
        corps = re.sub(r"\s+", " ", reponse.text)
        print(f"    Corps : {corps[:400]}")
        time.sleep(2)


def aftt() -> None:
    """La recherche par distance rend des sites de clubs : sous quelle forme ?"""
    titre("BELGIQUE — anatomie d'une réponse du moteur AFTT")
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR})
    url = "https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi"
    reponse = session.post(url, data={"city": "7829", "kms": "15", "search_dist": "1"},
                           timeout=60)
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères")
    soupe = BeautifulSoup(reponse.text, "html.parser")
    for etiquette in soupe(["script", "style", "nav", "footer", "header", "select"]):
        etiquette.decompose()
    texte = re.sub(r"\n{2,}", "\n", soupe.get_text("\n", strip=True))
    # Les résultats suivent le formulaire : on repère un repère textuel puis on affiche.
    for repere in ("Résultat", "resultat", "club", "km"):
        position = texte.lower().find(repere.lower())
        if position > 0:
            print(f"    Après « {repere} » :\n{texte[position:position + 1500]}")
            break
    # Et on regarde comment un site de club est rattaché à un nom.
    for lien in soupe.find_all("a", href=True):
        if lien["href"].startswith("http") and not re.search(
                r"aftt|frbtt|facebook|instagram|youtube|twitter|linkedin|google|w3\.org|"
                r"adeps|aisf|ettu|ittf|cpdeliege|vttl", lien["href"], re.I):
            entourage = lien.find_parent(["li", "div", "p", "td", "article"])
            resume = re.sub(r"\s+", " ", entourage.get_text(" ", strip=True))[:250] if entourage else ""
            print(f"    Lien {lien['href']} — texte « {lien.get_text(strip=True)[:40]} »"
                  f" — entourage : {resume}")


def main() -> int:
    for sonde in (angleterre, aftt):
        try:
            sonde()
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
