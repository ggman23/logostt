#!/usr/bin/env python3
"""Cherche, pour la Belgique et l'Angleterre, une source donnant sites web et logos.

L'API TabT belge liste bien tous les clubs mais sa fiche ne contient ni adresse de
site ni logo : il faut donc trouver le frontal web qui, lui, les affiche.
"""

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


def apercu(reponse) -> None:
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères"
          f" | {reponse.headers.get('Content-Type')}")


def belgique_soap(client: Client) -> None:
    """Appelle GetClubs en SOAP : c'est la seule façon d'obtenir la liste complète."""
    titre("BELGIQUE — GetClubs en SOAP")
    reponse = client.get("https://api.vttl.be/0.7/?wsdl", taille_max=6_000_000)
    if reponse is None:
        print("    -> WSDL inaccessible")
        return
    espace = re.search(r'targetNamespace="([^"]+)"', reponse.text)
    espace = espace.group(1) if espace else "urn:TabTAPI"
    print(f"    Espace de noms : {espace}")
    try:
        soap = client.session.post(
            "https://api.vttl.be/0.7/", data=ENVELOPPE.format(espace=espace).encode(),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{espace}#GetClubs"'},
            timeout=90)
    except Exception as erreur:  # noqa: BLE001
        print(f"    -> échec {type(erreur).__name__}: {erreur}")
        return
    print(f"    -> HTTP {soap.status_code} | {len(soap.text)} caractères")
    if "Fault" in soap.text[:2000]:
        print("    Erreur SOAP :", re.sub(r"\s+", " ", soap.text)[:400])
        return
    clubs = re.findall(r"<ClubEntries>(.*?)</ClubEntries>", soap.text, re.S)
    print(f"    {len(clubs)} clubs renvoyés")
    for club in clubs[:2]:
        print("    Exemple :", re.sub(r"\s+", " ", club)[:500])


def belgique_frontal(client: Client) -> None:
    """Le frontal TabT affiche une fiche par club : y trouve-t-on un site web ?"""
    for nom, url in [
        ("VTTL liste des clubs", "https://competitie.vttl.be/?menu=6"),
        ("VTTL fiche club", "https://competitie.vttl.be/club/BBW100"),
        ("AFTT liste des clubs", "https://resultats.aftt.be/?menu=6"),
        ("AFTT fiche club", "https://resultats.aftt.be/club/H001"),
        ("VTTL site fédéral", "https://www.vttl.be/clubs"),
    ]:
        titre(f"BELGIQUE — {nom}\n    {url}")
        reponse = client.get(url, taille_max=8_000_000)
        if reponse is None:
            print("    -> ÉCHEC")
            continue
        apercu(reponse)
        soupe = BeautifulSoup(reponse.text, "html.parser")
        print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
        interne = re.compile(r"vttl\.be|aftt\.be|tabt|google|facebook|twitter|w3\.org", re.I)
        externes = [a["href"] for a in soupe.find_all("a", href=True)
                    if a["href"].startswith("http") and not interne.search(a["href"])]
        print(f"    Liens externes (sites de clubs ?) : {len(externes)} — ex. {externes[:5]}")
        fiches = [a["href"] for a in soupe.find_all("a", href=True) if re.search(r"club", a["href"], re.I)]
        print(f"    Liens « club » : {len(fiches)} — ex. {fiches[:5]}")
        images = [i.get("src") for i in soupe.find_all("img", src=True)]
        print(f"    Images : {len(images)} — ex. {images[:5]}")
        lignes = soupe.find_all("tr")
        print(f"    Lignes de tableau : {len(lignes)}")
        for ligne in lignes[1:3]:
            cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:40]
                        for c in ligne.find_all(("td", "th"))]
            if cellules:
                print("      |", " | ".join(cellules[:7]))


def angleterre(client: Client) -> None:
    """Table Tennis England : localiser l'annuaire (le domaine impose le préfixe www)."""
    titre("ANGLETERRE — plan du site complet")
    reponse = client.get("https://www.tabletennisengland.co.uk/sitemap.xml", taille_max=8_000_000)
    if reponse is not None:
        adresses = re.findall(r"<loc>([^<]+)</loc>", reponse.text)
        print(f"    {len(adresses)} sous-plans :")
        for adresse in adresses:
            print("      ", adresse)

    for nom, url in [
        ("Annuaire clubs", "https://www.tabletennisengland.co.uk/clubs/find-a-club/"),
        ("Page clubs", "https://www.tabletennisengland.co.uk/clubs/"),
        ("Recherche de club", "https://www.tabletennisengland.co.uk/find-a-club/"),
        ("Types WordPress", "https://www.tabletennisengland.co.uk/wp-json/wp/v2/types"),
        ("Ligues (WP)", "https://www.tabletennisengland.co.uk/wp-json/wp/v2/leagues?per_page=3"),
    ]:
        titre(f"ANGLETERRE — {nom}\n    {url}")
        reponse = client.get(url, taille_max=8_000_000)
        if reponse is None:
            print("    -> ÉCHEC")
            continue
        apercu(reponse)
        texte = reponse.text
        if texte.lstrip().startswith(("{", "[")):
            try:
                donnees = json.loads(texte)
            except ValueError:
                print("    Extrait :", texte[:400])
                continue
            print("    JSON :", json.dumps(donnees, ensure_ascii=False)[:800])
            continue
        soupe = BeautifulSoup(texte, "html.parser")
        print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
        for formulaire in soupe.find_all("form")[:3]:
            champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
            print(f"    Formulaire action={formulaire.get('action')} champs={champs[:10]}")
        # Un annuaire piloté par JavaScript trahit son API dans les scripts de la page.
        reperes: set[str] = set()
        for script in soupe.find_all("script"):
            reperes |= set(re.findall(r'https?://[^"\'\s<>]{6,120}?(?:api|ajax|club|finder)[^"\'\s<>]*',
                                      script.string or ""))
        for adresse in sorted(reperes)[:8]:
            print("    Appel repéré :", adresse[:140])
        liens = [a["href"] for a in soupe.find_all("a", href=True) if re.search(r"club", a["href"], re.I)]
        print(f"    Liens « club » : {len(liens)} — ex. {liens[:6]}")


def main() -> int:
    client = Client(delai=1.0, timeout=60)
    for sonde in (belgique_soap, belgique_frontal, angleterre):
        try:
            sonde(client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
