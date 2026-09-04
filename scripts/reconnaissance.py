#!/usr/bin/env python3
"""Comprend le refus du flux anglais et fouille le moteur « trouver un club » de l'AFTT."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def brut(session, url: str, entetes: dict | None = None) -> None:
    """Requête sans filet, pour voir le vrai code de retour et le vrai message."""
    try:
        reponse = session.get(url, headers=entetes or {}, timeout=60)
    except Exception as erreur:  # noqa: BLE001
        print(f"    -> exception {type(erreur).__name__}: {erreur}")
        return None
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.content)} octets"
          f" | {reponse.headers.get('Content-Type')}")
    if reponse.status_code != 200:
        print("    Corps :", re.sub(r"\s+", " ", reponse.text)[:300])
        return None
    return reponse


def angleterre(client: Client) -> None:
    titre("ANGLETERRE — pourquoi le flux refuse-t-il de répondre ?")
    url = "https://www.tabletennis365.com/TableTennisEngland/API/OpenActive/v1/Clubs"
    for intitule, entetes in [
        ("agent par défaut", None),
        ("agent navigateur", {"User-Agent": NAVIGATEUR, "Accept": "application/json"}),
    ]:
        print(f"  — {intitule}")
        reponse = brut(client.session, url, entetes)
        if reponse is None:
            continue
        try:
            donnees = reponse.json()
        except ValueError:
            print("    Réponse non-JSON :", reponse.text[:300])
            continue
        elements = donnees.get("items", [])
        print(f"    Clés : {list(donnees)} | {len(elements)} éléments"
              f" | suivante : {donnees.get('next')}")
        avec_site = sum(1 for e in elements if (e.get("data") or {}).get("websiteUrl"))
        print(f"    {avec_site} des {len(elements)} fiches portent une adresse de site")
        if elements:
            print("    Exemple :", json.dumps(elements[0], ensure_ascii=False)[:900])
        return


def belgique_soap(client: Client) -> None:
    titre("BELGIQUE — GetClubs en SOAP (lecture sans lxml)")
    wsdl = client.get("https://api.vttl.be/0.7/?wsdl", taille_max=6_000_000)
    espace = re.search(r'targetNamespace="([^"]+)"', wsdl.text).group(1) if wsdl else ""
    enveloppe = ('<?xml version="1.0" encoding="utf-8"?>'
                 '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
                 f'<soap:Body><GetClubs xmlns="{espace}"></GetClubs></soap:Body></soap:Envelope>')
    try:
        soap = client.session.post(
            "https://api.vttl.be/0.7/", data=enveloppe.encode(),
            headers={"Content-Type": "text/xml; charset=utf-8",
                     "SOAPAction": f'"{espace}#GetClubs"'}, timeout=90)
    except Exception as erreur:  # noqa: BLE001
        print(f"    -> échec {type(erreur).__name__}: {erreur}")
        return
    print(f"    -> HTTP {soap.status_code} | {len(soap.text)} caractères")
    fiches = re.findall(r"<ClubEntries>(.*?)</ClubEntries>", soap.text, re.S)
    if not fiches:  # les balises peuvent porter un préfixe d'espace de noms
        fiches = re.findall(r"<\w*:?ClubEntries[^>]*>(.*?)</\w*:?ClubEntries>", soap.text, re.S)
    print(f"    {len(fiches)} clubs")
    balises = set()
    for fiche in fiches:
        balises |= set(re.findall(r"<(\w+)>", fiche))
    print("    Champs :", sorted(balises))
    for fiche in fiches[:2]:
        print("    Exemple :", re.sub(r"\s+", " ", fiche)[:400])


def belgique_aftt(client: Client) -> None:
    """La page « trouver un club » pèse 470 Ko : contient-elle déjà tout l'annuaire ?"""
    titre("BELGIQUE — moteur « trouver un club » de l'AFTT")
    url = "https://aftt.be/index.php/trouver-un-club-pres-de-chez-toi/"
    reponse = client.get(url, taille_max=8_000_000)
    if reponse is None:
        reponse = client.get("https://aftt.be/index.php/trouver-un-club/", taille_max=8_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    texte = reponse.text
    print(f"    -> HTTP {reponse.status_code} | {len(texte)} caractères")
    soupe = BeautifulSoup(texte, "html.parser")
    options = soupe.find_all("option")
    print(f"    Options de menu déroulant : {len(options)} — ex."
          f" {[(o.get('value'), o.get_text(strip=True)[:30]) for o in options[:6]]}")
    # Les moteurs de ce genre embarquent souvent leurs données dans un script.
    for script in soupe.find_all("script"):
        contenu = script.string or ""
        for cle in ("clubs", "markers", "locations", "sites"):
            trouve = re.search(rf'"{cle}"\s*:\s*[\[{{]', contenu)
            if trouve:
                print(f"    Script contenant « {cle} » : {contenu[max(0,trouve.start()-80):trouve.start()+500]}")
                break
    liens_clubs = sorted({a["href"] for a in soupe.find_all("a", href=True)
                          if re.search(r"/club|club=|clubs/", a["href"], re.I)})
    print(f"    Liens de fiches club : {len(liens_clubs)} — ex. {liens_clubs[:8]}")
    for mot in ("frbtt", "tabt", "vttl.be/clubs", "webform"):
        if mot in texte:
            extrait = re.sub(r"\s+", " ", texte[texte.find(mot) - 100: texte.find(mot) + 200])
            print(f"    « {mot} » : {extrait[:250]}")


def belgique_tabt_navigateur(client: Client) -> None:
    """Le frontal TabT bloque les robots : un agent de navigateur suffit-il ?"""
    titre("BELGIQUE — frontal TabT avec un agent de navigateur")
    for url in ("https://competitie.vttl.be/club/BBW100",
                "https://resultats.aftt.be/club/H001"):
        print(f"  — {url}")
        reponse = brut(client.session, url, {"User-Agent": NAVIGATEUR})
        if reponse is None:
            continue
        soupe = BeautifulSoup(reponse.text, "html.parser")
        print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
        interne = re.compile(r"vttl\.be|aftt\.be|facebook|google|w3\.org", re.I)
        externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                           if a["href"].startswith("http") and not interne.search(a["href"])})
        print(f"    Liens externes : {len(externes)} — ex. {externes[:6]}")


def main() -> int:
    client = Client(delai=1.0, timeout=60)
    for sonde in (angleterre, belgique_soap, belgique_aftt, belgique_tabt_navigateur):
        try:
            sonde(client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
