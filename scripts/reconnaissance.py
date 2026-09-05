#!/usr/bin/env python3
"""Tchéquie et Pologne : trouver la liste des clubs et, si possible, leurs sites.

Tchéquie : le registre fédéral répond normalement — où liste-t-il les oddíly ?
Pologne  : le tableau des licences donne 486 clubs ; les fiches ou les associations
           régionales donnent-elles leur site ?
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def charger(session, url: str) -> str:
    try:
        reponse = session.get(url, timeout=60)
    except Exception as erreur:  # noqa: BLE001
        print(f"    {url}\n    exception {type(erreur).__name__}: {erreur}")
        return ""
    print(f"    {url}\n    HTTP {reponse.status_code} | {len(reponse.content)} octets")
    return reponse.text if reponse.status_code == 200 else ""


def resume(html: str, url: str, motif: str) -> BeautifulSoup | None:
    if not html:
        return None
    soupe = BeautifulSoup(html, "html.parser")
    print("      titre :", soupe.title.get_text(' ', strip=True)[:70] if soupe.title else "(aucun)")
    lignes = soupe.find_all("tr")
    print(f"      lignes de tableau : {len(lignes)}")
    for ligne in lignes[:4]:
        cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:35]
                    for c in ligne.find_all(("td", "th"))]
        if cellules:
            print("        |", " | ".join(cellules[:7]))
    vises = sorted({a["href"] for a in soupe.find_all("a", href=True)
                    if re.search(motif, a["href"], re.I)})
    print(f"      liens visés : {len(vises)} — ex. {vises[:8]}")
    hote = re.match(r"https?://[^/]+", url)
    externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                       if a["href"].startswith("http")
                       and not (hote and a["href"].startswith(hote.group(0)))
                       and not re.search(r"facebook|google|w3\.org|youtube|instagram", a["href"], re.I)})
    print(f"      liens externes : {len(externes)} — ex. {externes[:8]}")
    return soupe


def tchequie(session) -> None:
    titre("TCHÉQUIE — explorer le registre")
    racine = "https://registr.ping-pong.cz/htm/"
    soupe = resume(charger(session, racine), racine, r"oddil|oddíl|klub|subjekt|adresar")
    if soupe is None:
        return
    # On suit les entrées de menu qui promettent une liste d'oddíly.
    candidats = []
    for lien in soupe.find_all("a", href=True):
        intitule = lien.get_text(" ", strip=True)
        if re.search(r"oddíl|oddil|klub|subjekt|adresá|adresa", intitule + lien["href"], re.I):
            candidats.append((intitule[:40], urljoin(racine, lien["href"])))
    print("    Candidats :", candidats[:12])
    for intitule, url in candidats[:5]:
        print(f"  — « {intitule} »")
        resume(charger(session, url), url, r"oddil|oddíl|klub|subjekt")


def pologne(session) -> None:
    titre("POLOGNE — la fiche d'un club donne-t-elle son site ?")
    base = "https://rozgrywki.pzts.pl/rozgrywki-indywidualne/"
    for url in (f"{base}licencje?season=18&region=12&c_id=1280",
                f"{base}licencje?season=18&region=1&c_id=200"):
        resume(charger(session, url), url, r"klub|www")

    titre("POLOGNE — les associations régionales listent-elles les sites ?")
    for url in ("http://www.mzts.pl/kluby-czlonkowskie/",
                "http://ozts.cba.pl/kluby/",
                "http://kozts.pl/",
                "http://pozts.org/"):
        resume(charger(session, url), url, r"klub")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR, "Accept-Language": "cs,pl,en;q=0.8"})
    for sonde in (tchequie, pologne):
        try:
            sonde(session)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
