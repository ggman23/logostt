#!/usr/bin/env python3
"""Insiste sur le flux anglais (503) et interroge pour de bon le moteur de l'AFTT."""

from __future__ import annotations

import json
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
    """Le flux a répondu 503 : est-ce passager, lié à l'agent, ou à l'adresse ?"""
    titre("ANGLETERRE — obstination sur le flux ouvert")
    adresses = [
        "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs",
        "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs?afterId=0",
        "https://www.tabletennis365.com/TableTennisEngland/",
    ]
    entetes = {
        "User-Agent": NAVIGATEUR,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-GB,en;q=0.9",
    }
    session = requests.Session()  # sans réessais automatiques : on veut voir chaque réponse
    for adresse in adresses:
        print(f"  — {adresse}")
        for essai in range(1, 4):
            try:
                reponse = session.get(adresse, headers=entetes, timeout=60)
            except Exception as erreur:  # noqa: BLE001
                print(f"    essai {essai} : exception {type(erreur).__name__}: {erreur}")
                time.sleep(5)
                continue
            print(f"    essai {essai} : HTTP {reponse.status_code} |"
                  f" {len(reponse.content)} octets | {reponse.headers.get('Content-Type')}"
                  f" | serveur {reponse.headers.get('Server')}")
            if reponse.status_code == 200 and "json" in (reponse.headers.get("Content-Type") or ""):
                donnees = reponse.json()
                elements = donnees.get("items", [])
                avec = sum(1 for e in elements if (e.get("data") or {}).get("websiteUrl"))
                print(f"    {len(elements)} éléments, {avec} avec un site,"
                      f" suivante : {donnees.get('next')}")
                print("    Exemple :", json.dumps(elements[0], ensure_ascii=False)[:800]
                      if elements else "(vide)")
                return
            if reponse.status_code != 503:
                print("    Corps :", re.sub(r"\s+", " ", reponse.text)[:250])
                break
            time.sleep(8)


def aftt() -> None:
    """Le moteur « trouver un club » sait-il rendre la fiche d'un club, site compris ?"""
    titre("BELGIQUE — formulaires de l'AFTT")
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR})
    url = "https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi/"
    page = session.get(url, timeout=60)
    print(f"    page : HTTP {page.status_code} | {len(page.text)} caractères")
    soupe = BeautifulSoup(page.text, "html.parser")
    for selecteur in soupe.find_all("select"):
        options = selecteur.find_all("option")
        exemples = [(o.get("value"), o.get_text(strip=True)[:40]) for o in options[1:4]]
        print(f"    <select name={selecteur.get('name')}> : {len(options)} options — {exemples}")
    for formulaire in soupe.find_all("form"):
        champs = [(c.get("name"), c.get("type") or c.name) for c in
                  formulaire.find_all(("input", "select", "button")) if c.get("name")]
        print(f"    <form action={formulaire.get('action')} method={formulaire.get('method')}> {champs}")

    # On rejoue la recherche par club avec la première valeur proposée.
    selecteurs = {s.get("name"): s for s in soupe.find_all("select")}
    choix = selecteurs.get("club")
    if choix is not None:
        options = [o for o in choix.find_all("option") if (o.get("value") or "").strip()]
        if options:
            valeur = options[0]["value"]
            print(f"  — recherche du club {valeur} ({options[0].get_text(strip=True)})")
            reponse = session.post("https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi/",
                                   data={"club": valeur, "search_club": "1"}, timeout=60)
            resultat(reponse)

    # Et la recherche par commune, qui doit rendre plusieurs clubs d'un coup.
    ville = selecteurs.get("city")
    if ville is not None:
        options = [o for o in ville.find_all("option") if (o.get("value") or "").strip()]
        if options:
            valeur = options[0]["value"]
            print(f"  — recherche autour de {options[0].get_text(strip=True)} ({valeur})")
            reponse = session.post("https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi/",
                                   data={"city": valeur, "kms": "50", "search_dist": "1"},
                                   timeout=60)
            resultat(reponse)


def resultat(reponse) -> None:
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères")
    soupe = BeautifulSoup(reponse.text, "html.parser")
    interne = re.compile(r"aftt\.be|frbtt|facebook|instagram|youtube|twitter|linkedin|"
                         r"google|w3\.org|adeps|aisf|ettu|elementor", re.I)
    externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                       if a["href"].startswith("http") and not interne.search(a["href"])})
    print(f"    Liens externes (sites de clubs ?) : {len(externes)} — ex. {externes[:10]}")
    lignes = soupe.find_all("tr")
    print(f"    Lignes de tableau : {len(lignes)}")
    for ligne in lignes[:4]:
        cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:45]
                    for c in ligne.find_all(("td", "th"))]
        if cellules:
            print("      |", " | ".join(cellules[:7]))
    # Sinon, les résultats sont peut-être dans des blocs plutôt que dans un tableau.
    for classe in ("club", "result", "resultat", "card"):
        blocs = soupe.find_all(class_=re.compile(classe, re.I))
        if blocs:
            extrait = re.sub(r"[ \t]+", " ", blocs[0].get_text("\n", strip=True))[:300]
            print(f"    Blocs « {classe} » : {len(blocs)} — ex. {extrait}")
            break


def main() -> int:
    for sonde in (angleterre, aftt):
        try:
            sonde()
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
