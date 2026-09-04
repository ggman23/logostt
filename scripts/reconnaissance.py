#!/usr/bin/env python3
"""Sonde en détail les annuaires belge (TabT) et anglais (Table Tennis England)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def apercu(reponse) -> None:
    print(f"    -> HTTP {reponse.status_code} | {len(reponse.text)} caractères"
          f" | {reponse.headers.get('Content-Type')}")


def belgique_wsdl(client: Client) -> None:
    """Le WSDL décrit les opérations disponibles et les champs de chaque club."""
    titre("BELGIQUE — WSDL de l'API TabT")
    reponse = client.get("https://api.vttl.be/0.7/?wsdl", taille_max=6_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    apercu(reponse)
    wsdl = reponse.text
    operations = sorted(set(re.findall(r'<(?:wsdl:)?operation name="([^"]+)"', wsdl)))
    print(f"    Opérations ({len(operations)}) : {operations}")
    # Les types nous disent quels champs un club expose (site web ? logo ?).
    for bloc in re.findall(r'<(?:xsd:|s:)?complexType name="(?:Club|ClubEntry|VenueEntry|'
                           r'GetClubs|GetClubsResponse)[^"]*".*?</(?:xsd:|s:)?complexType>',
                           wsdl, re.S)[:6]:
        nom = re.search(r'name="([^"]+)"', bloc).group(1)
        champs = re.findall(r'<(?:xsd:|s:)?element[^>]*name="([^"]+)"[^>]*type="([^"]+)"', bloc)
        print(f"    Type {nom} : {champs}")
    for mot in ("Website", "Url", "URL", "Logo", "Homepage", "Web"):
        if mot in wsdl:
            for ligne in [l.strip() for l in wsdl.splitlines() if mot in l][:3]:
                print(f"    « {mot} » : {ligne[:150]}")


def belgique_json(client: Client) -> None:
    """TabT expose une passerelle JSON qui évite d'écrire du SOAP à la main."""
    for nom, url in [
        ("VTTL GetClubs (JSON)", "https://api.vttl.be/0.7/json/?action=GetClubs"),
        ("VTTL GetClubs cat. 1", "https://api.vttl.be/0.7/json/?action=GetClubs&ClubCategory=1"),
        ("VTTL GetClubTeams", "https://api.vttl.be/0.7/json/?action=GetClubTeams&Club=BBW100"),
        ("AFTT GetClubs (JSON)", "https://resultats.aftt.be/api/0.7/json/?action=GetClubs"),
        ("AFTT api GetClubs", "https://api.aftt.be/0.7/json/?action=GetClubs"),
    ]:
        titre(f"BELGIQUE — {nom}\n    {url}")
        reponse = client.get(url, taille_max=20_000_000)
        if reponse is None:
            print("    -> ÉCHEC")
            continue
        apercu(reponse)
        texte = reponse.text.strip()
        if not texte.startswith(("{", "[")):
            print("    Réponse non-JSON :", texte[:400].replace("\n", " "))
            continue
        try:
            donnees = json.loads(texte)
        except ValueError as erreur:
            print("    JSON illisible :", erreur)
            continue
        clubs = donnees.get("ClubEntries") if isinstance(donnees, dict) else None
        if clubs is None:
            print("    Clés :", list(donnees)[:12] if isinstance(donnees, dict) else type(donnees))
            print("    Extrait :", json.dumps(donnees, ensure_ascii=False)[:600])
            continue
        print(f"    {len(clubs)} clubs")
        for club in clubs[:2]:
            print("    Exemple :", json.dumps(club, ensure_ascii=False)[:900])
        champs: set[str] = set()
        for club in clubs:
            champs |= set(club)
        print("    Champs rencontrés :", sorted(champs))


def angleterre(client: Client) -> None:
    """Table Tennis England : trouver l'annuaire derrière le moteur de recherche."""
    for nom, url in [
        ("Plan du site", "https://tabletennisengland.co.uk/sitemap.xml"),
        ("Annuaire clubs", "https://tabletennisengland.co.uk/clubs/find-a-club/"),
        ("Recherche de club", "https://tabletennisengland.co.uk/find-a-club/"),
        ("API WordPress (types)", "https://tabletennisengland.co.uk/wp-json/wp/v2/types"),
        ("TT Leagues clubs", "https://www.ttleagues.com/clubs"),
    ]:
        titre(f"ANGLETERRE — {nom}\n    {url}")
        reponse = client.get(url, taille_max=8_000_000)
        if reponse is None:
            print("    -> ÉCHEC")
            continue
        apercu(reponse)
        texte = reponse.text
        if texte.lstrip().startswith("{"):
            try:
                print("    Clés JSON :", list(json.loads(texte))[:40])
            except ValueError:
                print("    Extrait :", texte[:400])
            continue
        if "<sitemap" in texte or "<urlset" in texte:
            adresses = re.findall(r"<loc>([^<]+)</loc>", texte)
            print(f"    {len(adresses)} adresses — ex. {adresses[:12]}")
            continue
        soupe = BeautifulSoup(texte, "html.parser")
        print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
        for formulaire in soupe.find_all("form")[:3]:
            champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
            print(f"    Formulaire action={formulaire.get('action')} champs={champs[:10]}")
        # Un annuaire piloté par JavaScript trahit son API dans les scripts de la page.
        for script in soupe.find_all("script"):
            contenu = script.string or ""
            for adresse in set(re.findall(r'https?://[^"\'\s]+(?:api|ajax|club)[^"\'\s]*', contenu))[:6]:
                print("    Appel repéré :", adresse[:140])
        liens = [a["href"] for a in soupe.find_all("a", href=True) if re.search(r"club", a["href"], re.I)]
        print(f"    Liens « club » : {len(liens)} — ex. {liens[:6]}")


def main() -> int:
    client = Client(delai=1.0, timeout=45)
    belgique_wsdl(client)
    belgique_json(client)
    angleterre(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
