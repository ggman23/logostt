#!/usr/bin/env python3
"""Décide de la forme des collectes belge et anglaise.

Trois questions :
  1. l'API TabT de la VTTL couvre-t-elle aussi les clubs francophones (préfixes) ?
  2. la recherche par nom de l'AFTT rend-elle la fiche d'un club donné, site compris ?
  3. que contient l'annuaire des sites hébergés par tabletennis365 ?
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
AFTT = "https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi"


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def couverture_tabt(session) -> None:
    titre("BELGIQUE — l'API TabT couvre-t-elle les deux ailes linguistiques ?")
    wsdl = session.get("https://api.vttl.be/0.7/?wsdl", timeout=60).text
    espace = re.search(r'targetNamespace="([^"]+)"', wsdl).group(1)
    enveloppe = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                 f'<soap:Body><GetClubs xmlns="{espace}"></GetClubs></soap:Body></soap:Envelope>')
    soap = session.post("https://api.vttl.be/0.7/", data=enveloppe.encode(),
                        headers={"Content-Type": "text/xml; charset=utf-8",
                                 "SOAPAction": f'"{espace}#GetClubs"'}, timeout=120)
    fiches = re.findall(r"<ns1:ClubEntries>(.*?)</ns1:ClubEntries>", soap.text, re.S)
    print(f"    {len(fiches)} clubs")
    prefixes = collections.Counter()
    categories = collections.Counter()
    for fiche in fiches:
        index = re.search(r"<ns1:UniqueIndex>([^<]+)</ns1:UniqueIndex>", fiche)
        categorie = re.search(r"<ns1:CategoryName>([^<]*)</ns1:CategoryName>", fiche)
        if index:
            prefixes[re.match(r"[A-Za-z]+", index.group(1)).group(0)] += 1
        if categorie:
            categories[categorie.group(1)] += 1
    print("    Préfixes d'index :", dict(prefixes))
    print("    Catégories (provinces) :", dict(categories))
    # Un exemple complet, pour connaître tous les champs exploitables.
    if fiches:
        print("    Fiche complète :", re.sub(r"\s+", " ", fiches[1])[:600])


def fiche_aftt(session) -> None:
    titre("BELGIQUE — la recherche par nom rend-elle la fiche d'un club précis ?")
    for recherche in ("BBW205", "ZENITH", "A003", "Salamander"):
        print(f"  — recherche « {recherche} »")
        reponse = session.post(AFTT, data={"club": recherche, "search_club": "1"}, timeout=60)
        soupe = BeautifulSoup(reponse.text, "html.parser")
        for etiquette in soupe(["script", "style", "nav", "footer", "header", "select"]):
            etiquette.decompose()
        texte = re.sub(r"\n{2,}", "\n", soupe.get_text("\n", strip=True))
        depart = texte.find("Liste des clubs")
        if depart < 0:
            depart = max(texte.find("Trouver un club près de chez toi"), 0)
        extrait = texte[depart:depart + 700]
        print("   ", extrait.replace("\n", " | ")[:700])


def sites_hebergés(session) -> None:
    titre("ANGLETERRE — annuaire des sites hébergés par tabletennis365")
    reponse = session.get("https://www.tabletennis365.com/Sites", timeout=60)
    soupe = BeautifulSoup(reponse.text, "html.parser")
    liens = [(a.get_text(" ", strip=True)[:45], a["href"])
             for a in soupe.find_all("a", href=True)
             if "tabletennis365.com/" in a["href"] and a["href"].count("/") >= 3]
    print(f"    {len(liens)} liens vers des sites hébergés — ex. {liens[:10]}")
    entetes = [h.get_text(" ", strip=True)[:60] for h in soupe.find_all(("h1", "h2", "h3"))]
    print("    Titres de la page :", entetes[:12])


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR})
    for sonde in (couverture_tabt, fiche_aftt, sites_hebergés):
        try:
            sonde(session)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
