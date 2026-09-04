#!/usr/bin/env python3
"""Valide le flux ouvert anglais et cherche les sites des clubs belges."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

ENVELOPPE = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body><GetClubs xmlns="{espace}"></GetClubs></soap:Body>
</soap:Envelope>"""


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def angleterre(client: Client) -> None:
    """Le flux OpenActive de Table Tennis England, page après page."""
    titre("ANGLETERRE — flux ouvert des clubs (OpenActive RPDE)")
    url = "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs"
    total = 0
    avec_site = 0
    exemples: list[dict] = []
    for page in range(1, 4):
        reponse = client.get(url, taille_max=20_000_000)
        if reponse is None:
            print(f"    page {page} -> ÉCHEC")
            return
        try:
            donnees = reponse.json()
        except ValueError:
            print("    Réponse non-JSON :", reponse.text[:400])
            return
        if page == 1:
            print(f"    Clés du flux : {list(donnees)}")
        elements = donnees.get("items", [])
        total += len(elements)
        for element in elements:
            fiche = element.get("data") or {}
            if fiche.get("websiteUrl"):
                avec_site += 1
            if len(exemples) < 2:
                exemples.append(element)
        suivante = donnees.get("next")
        print(f"    page {page} : {len(elements)} éléments — suivante {suivante}")
        if not elements or not suivante or suivante == url:
            break
        url = suivante
    print(f"    => {total} clubs vus, {avec_site} avec une adresse de site")
    for exemple in exemples:
        print("    Exemple :", json.dumps(exemple, ensure_ascii=False)[:1100])


def belgique_soap(client: Client) -> None:
    """Lecture correcte de GetClubs : les balises sont préfixées par leur espace de noms."""
    titre("BELGIQUE — GetClubs en SOAP")
    reponse = client.get("https://api.vttl.be/0.7/?wsdl", taille_max=6_000_000)
    espace = re.search(r'targetNamespace="([^"]+)"', reponse.text).group(1) if reponse else "urn:TabTAPI"
    try:
        soap = client.session.post(
            "https://api.vttl.be/0.7/", data=ENVELOPPE.format(espace=espace).encode(),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{espace}#GetClubs"'},
            timeout=90)
    except Exception as erreur:  # noqa: BLE001
        print(f"    -> échec {type(erreur).__name__}: {erreur}")
        return
    soupe = BeautifulSoup(soap.text, "xml")
    clubs = soupe.find_all(re.compile(r"ClubEntries$"))
    print(f"    {len(clubs)} clubs renvoyés (HTTP {soap.status_code})")
    for club in clubs[:3]:
        champs = {e.name: (e.get_text(strip=True)[:60]) for e in club.find_all(recursive=False)}
        print("    Exemple :", champs)
    if clubs:
        noms: set[str] = set()
        for club in clubs:
            noms |= {e.name for e in club.find_all()}
        print("    Champs rencontrés :", sorted(noms))


def belgique_sites(client: Client) -> None:
    """Les deux ailes linguistiques publient-elles un annuaire avec les sites des clubs ?"""
    for nom, url in [
        ("VTTL annuaire", "https://www.vttl.be/content/clubs"),
        ("AFTT accueil clubs", "https://aftt.be/index.php/clubs/"),
        ("AFTT recherche club", "https://aftt.be/index.php/trouver-un-club/"),
        ("AFTT plan du site", "https://aftt.be/wp-sitemap.xml"),
        ("VTTL plan du site", "https://www.vttl.be/sitemap.xml"),
    ]:
        titre(f"BELGIQUE — {nom}\n    {url}")
        reponse = client.get(url, taille_max=8_000_000)
        if reponse is None:
            print("    -> ÉCHEC")
            continue
        print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères")
        texte = reponse.text
        if "<urlset" in texte or "<sitemapindex" in texte:
            adresses = re.findall(r"<loc>([^<]+)</loc>", texte)
            print(f"    {len(adresses)} adresses — ex. {adresses[:15]}")
            continue
        soupe = BeautifulSoup(texte, "html.parser")
        print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
        for formulaire in soupe.find_all("form")[:3]:
            champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
            print(f"    Formulaire action={formulaire.get('action')} champs={champs[:10]}")
        interne = re.compile(r"vttl\.be|aftt\.be|facebook|twitter|instagram|linkedin|w3\.org|google", re.I)
        externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                           if a["href"].startswith("http") and not interne.search(a["href"])})
        print(f"    Liens externes : {len(externes)} — ex. {externes[:8]}")
        lignes = soupe.find_all("tr")
        print(f"    Lignes de tableau : {len(lignes)}")
        for ligne in lignes[1:3]:
            cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:40]
                        for c in ligne.find_all(("td", "th"))]
            if cellules:
                print("      |", " | ".join(cellules[:7]))


def main() -> int:
    client = Client(delai=1.0, timeout=60)
    for sonde in (angleterre, belgique_soap, belgique_sites):
        try:
            sonde(client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
