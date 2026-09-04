#!/usr/bin/env python3
"""Mesure le volume et l'accessibilité des annuaires de clubs les plus prometteurs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402


def compter_suisse(client: Client) -> None:
    """Suisse : même moteur nuLiga que l'Allemagne, donc même méthode de comptage."""
    print("=" * 100)
    print("### SUISSE — click-tt.ch (nuLiga, identique à l'Allemagne)")
    base = "https://www.click-tt.ch/cgi-bin/WebObjects/nuLigaTTCH.woa/wa/clubSearch"
    clubs: set[str] = set()
    for terme in ("e", "a", "i", "o", "u", "s", "n", "r", "t", "c"):
        try:
            reponse = client.session.post(
                base, data={"federation": "STT", "federations": "STT", "searchFor": terme},
                timeout=45)
        except Exception as erreur:  # noqa: BLE001
            print(f"    « {terme} » : échec {erreur}")
            continue
        trouves = set(re.findall(r"clubInfoDisplay\?club=(\d+)", reponse.text))
        clubs |= trouves
        print(f"    « {terme} » : {len(trouves):>4} clubs sur la page — total distinct {len(clubs)}")
    print(f"    => {len(clubs)} clubs suisses atteignables par la même méthode qu'en Allemagne")
    if clubs:
        exemple = sorted(clubs)[0]
        html = client.texte(
            f"https://www.click-tt.ch/cgi-bin/WebObjects/nuLigaTTCH.woa/wa/clubInfoDisplay?club={exemple}")
        soupe = BeautifulSoup(html, "html.parser")
        titre = soupe.find("h1")
        images = [i.get("src") for i in soupe.find_all("img", src=True) if "wodata" in i.get("src", "")]
        liens = [a["href"] for a in soupe.find_all("a", href=True)
                 if a["href"].startswith("http") and "click-tt" not in a["href"]
                 and "google" not in a["href"] and "tischtennis" not in a["href"]]
        print(f"    Fiche {exemple} : {titre.get_text(' ', strip=True)[:70] if titre else '?'}")
        print(f"      logo hébergé : {'OUI ' + images[0][:60] if images else 'non'}")
        print(f"      liens externes (site du club ?) : {liens[:3]}")


def sonder(nom: str, url: str, client: Client, motif: str = r"club|verein|oddil|societ") -> None:
    print("=" * 100)
    print(f"### {nom}\n    {url}")
    reponse = client.get(url, taille_max=6_000_000)
    if reponse is None:
        print("    -> ÉCHEC")
        return
    html = reponse.text
    print(f"    -> HTTP {reponse.status_code} | {len(html)} caractères | {reponse.headers.get('Content-Type')}")
    if html.lstrip().startswith(("{", "[")):
        try:
            donnees = json.loads(html)
            print("    JSON :", json.dumps(donnees, ensure_ascii=False)[:700])
            return
        except ValueError:
            pass
    soupe = BeautifulSoup(html, "html.parser")
    print("    Titre :", soupe.title.get_text(' ', strip=True)[:70] if soupe.title else "(aucun)")
    liens = [a["href"] for a in soupe.find_all("a", href=True) if re.search(motif, a["href"], re.I)]
    print(f"    Liens « club » : {len(liens)} — ex. {liens[:4]}")
    for formulaire in soupe.find_all("form")[:2]:
        champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
        print(f"    Formulaire action={formulaire.get('action')} méthode={formulaire.get('method')} champs={champs[:8]}")
    lignes = soupe.find_all("tr")
    print(f"    Lignes de tableau : {len(lignes)}")
    for ligne in lignes[1:4]:
        cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:34] for c in ligne.find_all(("td", "th"))]
        if cellules:
            print("      |", " | ".join(cellules[:6]))


def main() -> int:
    client = Client(delai=1.0, timeout=45)
    compter_suisse(client)
    for nom, url in [
        ("Espagne — portail clubs", "https://clubs.rfetm.es/"),
        ("Autriche — liste des vereine", "https://www.oettv.org/organisation/vereine"),
        ("Pays-Bas — chercher un club", "https://www.nttb.nl/zoek-een-club/"),
        ("Tchéquie — STIS clubs", "https://stis.ping-pong.cz/htm/?id=souteze"),
        ("Belgique — API TabT", "https://api.vttl.be/0.7/?wsdl"),
        ("Belgique — TabT REST", "https://tabt.frenoy.net/api/?action=GetClubs&Season=26"),
        ("Pologne — licences par club", "https://rozgrywki.pzts.pl/rozgrywki-indywidualne/club_licenses?season=18"),
        ("Angleterre — annuaire clubs", "https://www.tabletennisengland.co.uk/clubs/tt-clubs/"),
    ]:
        try:
            sonder(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
