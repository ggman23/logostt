#!/usr/bin/env python3
"""Reconnaissance click-TT : début de fiche club, logo hébergé et site du club."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

BASE = "https://dttb.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa"
CLUBS = ["10702", "11999", "3983", "1411", "24185"]


def fiche(client: Client, club: str) -> None:
    print("=" * 100)
    print(f"### FICHE {club}")
    html = client.texte(f"{BASE}/clubInfoDisplay?club={club}")
    if not html:
        print("    -> ÉCHEC")
        return
    soupe = BeautifulSoup(html, "html.parser")
    for inutile in soupe.find_all(("script", "style", "svg")):
        inutile.decompose()

    # Le contenu utile commence au premier <h1>/<h2> après l'en-tête de navigation.
    titre = soupe.find("h1")
    print("    h1 :", titre.get_text(" ", strip=True) if titre else "(aucun)")

    images = [(i.get("alt"), i.get("src"), i.get("height")) for i in soupe.find_all("img")]
    print("    Images :", images[:8])

    liens = [(a.get_text(" ", strip=True)[:40], a["href"]) for a in soupe.find_all("a", href=True)
             if a["href"].startswith("http") and "google" not in a["href"]
             and "tischtennis.de" not in a["href"] and "datenautomaten" not in a["href"]]
    print("    Liens externes :", liens[:8])

    premier = soupe.find("table")
    if premier:
        lignes = [l for l in premier.prettify().splitlines() if l.strip()]
        print("    --- PREMIER TABLEAU (identité du club) ---")
        for ligne in lignes[:75]:
            print("   ", ligne[:170])


def logo(client: Client, club: str) -> None:
    """Vérifie que l'image hébergée par click-TT se télécharge bien."""
    html = client.texte(f"{BASE}/clubInfoDisplay?club={club}")
    soupe = BeautifulSoup(html, "html.parser")
    for image in soupe.find_all("img", src=True):
        if "wodata" not in image["src"]:
            continue
        url = "https://dttb.click-tt.de" + image["src"]
        reponse = client.get(url, taille_max=4_000_000)
        etat = (f"HTTP {reponse.status_code} | {reponse.headers.get('Content-Type')} | "
                f"{len(reponse.content)} octets") if reponse else "ÉCHEC"
        print(f"    LOGO {club} ({image.get('alt')}) -> {etat}")
        print(f"         {url}")
        return
    print(f"    LOGO {club} : aucune image hébergée sur la fiche")


def main() -> int:
    client = Client(delai=1.2, timeout=30)
    for club in CLUBS[:3]:
        fiche(client, club)
    print("=" * 100)
    print("### TÉLÉCHARGEMENT DES LOGOS HÉBERGÉS")
    for club in CLUBS:
        logo(client, club)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
