#!/usr/bin/env python3
"""Sonde les sources de données publiques utilisables sans identifiants.

Ce script ne collecte rien : il interroge une liste d'adresses candidates et résume ce
qu'elles répondent (code HTTP, type de contenu, extrait). Il sert à choisir la meilleure
source ouverte pour obtenir la liste des clubs et leurs sites internet, depuis un
environnement qui a réellement accès à internet (GitHub Actions).

    python3 scripts/reconnaissance.py            # sondes par défaut
    python3 scripts/reconnaissance.py URL [URL…] # sondes supplémentaires
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bs4 import BeautifulSoup  # noqa: E402

from ttlogos.reseau import Client  # noqa: E402

SONDES: list[tuple[str, str]] = [
    # --- API SmartPing sans authentification (points d'entrée historiques) ---
    ("SmartPing pxml ouvert", "https://www.fftt.com/mobile/pxml/xml_club_dep2.php?dep=75"),
    ("SmartPing xml ouvert", "https://www.fftt.com/mobile/xml/xml_club_dep2.php?dep=75"),
    ("SmartPing apiv2 sans clé", "https://apiv2.fftt.com/mobile/pxml/xml_club_dep2.php?dep=75"),
    ("SmartPing fiche club", "https://www.fftt.com/mobile/pxml/xml_club_detail.php?club=07750123"),
    # --- Site fédéral public ---
    ("Accueil FFTT", "https://www.fftt.com/"),
    ("FFTT trouver un club", "https://www.fftt.com/trouver-un-club/"),
    ("FFTT clubs (ancien site)", "https://www.fftt.com/site/decouvrir/clubs"),
    ("FFTT WordPress REST", "https://www.fftt.com/wp-json/"),
    ("FFTT WordPress types", "https://www.fftt.com/wp-json/wp/v2/types"),
    ("MonClub FFTT", "https://monclub.fftt.com/"),
    # --- Annuaires tiers ---
    ("Pongiste clubs", "https://www.pongiste.fr/clubs"),
    ("Pongiste département 75", "https://www.pongiste.fr/clubs/75"),
    # --- Open data ---
    ("data.sports.gouv catalogue", "https://data.sports.gouv.fr/api/explore/v2.1/catalog/datasets?limit=20&where=search(%22club%22)"),
    ("Overpass (clubs TT France)", "https://overpass-api.de/api/interpreter?data=[out:json][timeout:60];area[\"ISO3166-1\"=\"FR\"][admin_level=2]->.a;nwr[\"sport\"=\"table_tennis\"][\"website\"](area.a);out tags 40;"),
    # --- Moteurs de recherche utilisables en secours ---
    ("DuckDuckGo HTML", "https://html.duckduckgo.com/html/?q=club+tennis+de+table+Rennes+site+officiel"),
]

INTERESSANT = re.compile(r"club|annuaire|trouver|recherche|departement|département|ligue", re.I)


def resumer(nom: str, url: str, client: Client) -> None:
    print("=" * 100)
    print(f"### {nom}\n    {url}")
    reponse = client.get(url, taille_max=2_500_000)
    if reponse is None:
        print("    -> ÉCHEC (pas de réponse exploitable : erreur réseau, refus ou code >= 400)")
        return
    type_contenu = (reponse.headers.get("Content-Type") or "?").split(";")[0]
    print(f"    -> HTTP {reponse.status_code} | {type_contenu} | {len(reponse.content)} octets")
    if reponse.url != url:
        print(f"    -> redirigé vers {reponse.url}")

    texte = reponse.text
    if "json" in type_contenu:
        try:
            donnees = json.loads(texte)
        except ValueError:
            print("    JSON illisible")
        else:
            apercu = json.dumps(donnees, ensure_ascii=False)[:1500]
            print(f"    JSON : {apercu}")
        return
    if "xml" in type_contenu or texte.lstrip().startswith("<?xml"):
        print("    XML :", texte[:1200].replace("\n", " "))
        return
    if "html" not in type_contenu:
        print("    Extrait :", texte[:600].replace("\n", " "))
        return

    soupe = BeautifulSoup(texte, "html.parser")
    titre = soupe.title.string.strip() if soupe.title and soupe.title.string else "(sans titre)"
    print(f"    Titre : {titre}")
    liens = []
    for lien in soupe.find_all("a", href=True):
        libelle = " ".join(lien.get_text(" ", strip=True).split())[:60]
        if INTERESSANT.search(lien["href"]) or INTERESSANT.search(libelle):
            liens.append(f"{libelle or '(sans texte)'} -> {lien['href']}")
    print(f"    Liens « club » ({len(liens)}) :")
    for ligne in liens[:25]:
        print("      ·", ligne[:150])
    formulaires = soupe.find_all("form")
    if formulaires:
        print(f"    Formulaires ({len(formulaires)}) :")
        for formulaire in formulaires[:4]:
            champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
            print(f"      · action={formulaire.get('action')} méthode={formulaire.get('method')} champs={champs[:10]}")
    scripts = [s.get("src") for s in soupe.find_all("script", src=True)]
    interessants = [s for s in scripts if INTERESSANT.search(s or "")]
    if interessants:
        print("    Scripts liés aux clubs :", interessants[:6])
    for motif in (r"https?://[^\s\"']*api[^\s\"']{0,60}", r"/wp-json/[^\s\"']{0,60}", r"ajax[^\s\"']{0,60}"):
        trouves = sorted(set(re.findall(motif, texte)))[:8]
        if trouves:
            print(f"    Motif {motif[:20]}… :", trouves)


def main() -> int:
    client = Client(delai=1.0, timeout=30)
    sondes = SONDES + [(f"URL fournie {i + 1}", url) for i, url in enumerate(sys.argv[1:])]
    for nom, url in sondes:
        try:
            resumer(nom, url, client)
        except Exception as erreur:  # noqa: BLE001 - une sonde ne doit jamais arrêter les autres
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
