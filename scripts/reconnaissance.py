#!/usr/bin/env python3
"""Reconnaissance des annuaires de clubs, pays par pays.

Cherche, pour chaque fédération candidate, s'il existe un annuaire public exploitable
comme l'ont été carte.fftt.com (France) et click-TT (Allemagne). Ne collecte rien.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

NU = "cgi-bin/WebObjects"

CANDIDATS = [
    # --- nuLiga / click-TT hors Allemagne : le même extracteur pourrait servir ---
    ("Suisse — click-tt.ch", "https://www.click-tt.ch/"),
    ("Suisse — recherche clubs", f"https://www.click-tt.ch/{NU}/nuLigaTTCH.woa/wa/clubSearch?federation=STT"),
    ("Autriche — nuLiga", "https://ttv.nuliga.at/"),
    ("Autriche — ÖTTV", "https://www.oettv.org/"),
    ("Luxembourg — FLTT", "https://fltt.lu/"),
    # --- Belgique ---
    ("Belgique — VTTL compétition", "https://competitie.vttl.be/"),
    ("Belgique — VTTL clubs", "https://competitie.vttl.be/clubs"),
    ("Belgique — AFTT résultats", "https://resultats.aftt.be/"),
    # --- Pays-Bas ---
    ("Pays-Bas — NTTB", "https://www.nttb.nl/"),
    ("Pays-Bas — NAS compétition", "https://nas.nttb.nl/"),
    ("Pays-Bas — clubs", "https://www.nttb.nl/verenigingen/"),
    # --- Royaume-Uni ---
    ("Angleterre — TT England clubs", "https://www.tabletennisengland.co.uk/clubs/"),
    ("Angleterre — club finder", "https://tabletennisengland.co.uk/clubs/find-a-club/"),
    # --- Europe centrale et du Nord ---
    ("Tchéquie — STIS (registre)", "https://stis.ping-pong.cz/"),
    ("Tchéquie — liste des clubs", "https://stis.ping-pong.cz/htm/?id=oddily"),
    ("Pologne — PZTS", "https://pzts.pl/"),
    ("Suède — SBTF", "https://www.svenskbordtennis.com/"),
    ("Danemark — BTDK", "https://bttdk.dk/"),
    ("Norvège — NBTF", "https://bordtennis.no/"),
    # --- Europe du Sud ---
    ("Italie — FITET", "https://www.fitet.org/"),
    ("Italie — société affiliées", "https://portale.fitet.org/"),
    ("Espagne — RFETM", "https://www.rfetm.es/"),
    ("Portugal — FPTM", "https://www.fptm.pt/"),
    ("Hongrie — MOATSZ", "https://moatsz.hu/"),
]

INDICES = re.compile(r"club|verein|vereniging|oddil|oddíl|societ|asociac|forening|klubb", re.I)


def sonder(nom: str, url: str, client: Client) -> None:
    reponse = client.get(url, taille_max=4_000_000)
    if reponse is None:
        print(f"{nom:<34} ÉCHEC (bloqué, injoignable ou erreur)")
        return
    html = reponse.text
    soupe = BeautifulSoup(html, "html.parser")
    titre = soupe.title.get_text(" ", strip=True)[:44] if soupe.title else "(sans titre)"
    liens = [a["href"] for a in soupe.find_all("a", href=True)]
    pistes = [l for l in liens if INDICES.search(l)]
    formulaires = len(soupe.find_all("form"))
    nuliga = "nuLiga" in html or "click-tt" in html.lower() or "nuliga" in html.lower()
    print(f"{nom:<34} HTTP {reponse.status_code} | {len(html):>7} car. | {titre}")
    print(f"{'':<34} liens « club » : {len(pistes):<4} formulaires : {formulaires}"
          f"{'  ⟵ nuLiga détecté' if nuliga else ''}")
    if pistes:
        print(f"{'':<34} ex. {pistes[:3]}")


def main() -> int:
    client = Client(delai=1.0, timeout=20)
    print("=" * 110)
    for nom, url in CANDIDATS + [(f"URL fournie {i+1}", u) for i, u in enumerate(sys.argv[1:])]:
        try:
            sonder(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"{nom:<34} exception : {type(erreur).__name__}: {erreur}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
