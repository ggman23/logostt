#!/usr/bin/env python3
"""Reconnaissance click-TT (Allemagne) : recherche de clubs et balisage des fiches."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

BASE = "https://dttb.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa"
RECHERCHE = f"{BASE}/clubSearch"


def formulaire(client: Client) -> None:
    """Relève les champs cachés du formulaire de recherche (dont la liste des fédérations)."""
    print("=" * 100)
    print("### CHAMPS DU FORMULAIRE DE RECHERCHE")
    html = client.texte(f"{RECHERCHE}?federation=DTTB")
    soupe = BeautifulSoup(html, "html.parser")
    for champ in soupe.find_all("input"):
        valeur = (champ.get("value") or "")[:600]
        print(f"    {champ.get('name')} ({champ.get('type')}) = {valeur}")
    for pastille in soupe.find_all(class_="region-pills"):
        liens = [(a.get_text(strip=True), a.get("href")) for a in pastille.find_all("a")]
        print(f"    Régions ({len(liens)}) : {liens[:30]}")


def rechercher(client: Client, terme: str, federation: str = "DTTB") -> None:
    print("=" * 100)
    print(f"### RECHERCHE POST « {terme} » ({federation})")
    try:
        reponse = client.session.post(
            RECHERCHE,
            data={"federation": federation, "federations": federation, "searchFor": terme},
            timeout=30,
        )
    except Exception as erreur:  # noqa: BLE001
        print("    -> échec :", erreur)
        return
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères | {reponse.url}")
    soupe = BeautifulSoup(reponse.text, "html.parser")
    fiches = [a["href"] for a in soupe.find_all("a", href=True) if "clubInfoDisplay" in a["href"]]
    print(f"    Fiches club listées : {len(fiches)} — exemples {fiches[:4]}")
    pagination = [a["href"] for a in soupe.find_all("a", href=True)
                  if re.search(r"offset|page|next|weiter", a["href"], re.I)]
    print(f"    Pagination : {pagination[:6]}")
    for tableau in soupe.find_all("table")[:1]:
        for ligne in tableau.find_all("tr")[:5]:
            cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:40] for c in ligne.find_all(("th", "td"))]
            if cellules:
                print("      |", " | ".join(cellules))
    texte = re.sub(r"\s+", " ", soupe.get_text(" ", strip=True))
    trouve = re.search(r"(\d+)\s*(Treffer|Vereine|Ergebnis)", texte, re.I)
    if trouve:
        print("    Nombre annoncé :", trouve.group(0))


def fiche(client: Client, club: str) -> None:
    print("=" * 100)
    print(f"### BALISAGE DE LA FICHE {club}")
    html = client.texte(f"{BASE}/clubInfoDisplay?club={club}")
    soupe = BeautifulSoup(html, "html.parser")
    for inutile in soupe.find_all(("script", "style", "svg", "nav")):
        inutile.decompose()
    corps = soupe.find("body") or soupe
    lignes = [l for l in corps.prettify().splitlines() if l.strip()]
    debut = next((i for i, l in enumerate(lignes) if "Verein" in l or "Vereinsnummer" in l), 0)
    for ligne in lignes[debut:debut + 110]:
        print("   ", ligne[:175])


def main() -> int:
    client = Client(delai=1.5, timeout=30)
    formulaire(client)
    for terme in ("a", "tt", "TTC"):
        rechercher(client, terme)
    fiche(client, "10702")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
