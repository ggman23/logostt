#!/usr/bin/env python3
"""Repère comment la carte publique de la FFTT charge ses clubs, et ce que contient
une fiche club. Sert à écrire l'extracteur ; ne collecte rien.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

FICHES = [
    ("Fiche club sur la carte", "https://carte.fftt.com/club/04180613"),
    ("Fiche club (inscription en ligne)", "https://inscriptionenligne.fftt.com/club/04180613"),
    ("Recherche carte (paramètres du formulaire)", "https://carte.fftt.com/?q=Bourges&type=club"),
    ("Recherche carte en JSON ?", "https://carte.fftt.com/search?q=Bourges"),
]

SCRIPTS = [
    "https://carte.fftt.com/build/assets/map-CZZd2YIf.js",
    "https://carte.fftt.com/build/assets/app-BPdAoDsu.js",
]

# Ce qui trahit un appel réseau dans un paquet JavaScript minifié.
INDICES = (
    r"fetch\(",
    r"XMLHttpRequest",
    r"axios",
    r"\"/[a-z][a-z0-9\-/_.]{2,50}\"",
    r"`/[a-z][a-z0-9\-/_.${}]{2,60}`",
    r"\.json",
    r"geojson",
)


def contexte(code: str, motif: str, fenetre: int = 110, maximum: int = 12) -> list[str]:
    extraits = []
    for trouve in list(re.finditer(motif, code))[:maximum]:
        debut = max(0, trouve.start() - fenetre)
        extraits.append(code[debut:trouve.end() + fenetre].replace("\n", " "))
    return extraits


def fouiller(url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### SCRIPT {url}")
    code = client.texte(url, taille_max=8_000_000)
    if not code:
        print("    -> inaccessible")
        return
    print(f"    {len(code)} caractères")
    for motif in INDICES:
        extraits = contexte(code, motif)
        if extraits:
            print(f"    --- {motif} ({len(extraits)}) ---")
            for extrait in extraits:
                print("      ·", extrait[:230])


def fiche(nom: str, url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### {nom}\n    {url}")
    reponse = client.get(url, taille_max=4_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    html = reponse.text
    print(f"    -> HTTP {reponse.status_code} | {reponse.headers.get('Content-Type')} | {len(html)} caractères")
    if reponse.url != url:
        print(f"    -> redirigé vers {reponse.url}")
    if not html.lstrip().startswith("<"):
        print("    Contenu :", html[:1200])
        return
    soupe = BeautifulSoup(html, "html.parser")
    print("    Titre :", soupe.title.get_text(strip=True) if soupe.title else "(aucun)")
    externes = [
        a["href"] for a in soupe.find_all("a", href=True)
        if a["href"].startswith(("http", "//")) and "fftt" not in a["href"]
    ]
    print(f"    Liens externes ({len(externes)}) :", externes[:15])
    images = [i.get("src") for i in soupe.find_all("img", src=True)]
    print(f"    Images ({len(images)}) :", images[:10])
    texte = re.sub(r"\s+", " ", soupe.get_text(" ", strip=True))
    print("    Texte :", texte[:900])


def main() -> int:
    client = Client(delai=1.5, timeout=45)
    for nom, url in FICHES + [(f"URL fournie {i + 1}", u) for i, u in enumerate(sys.argv[1:])]:
        try:
            fiche(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    for url in SCRIPTS:
        try:
            fouiller(url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
