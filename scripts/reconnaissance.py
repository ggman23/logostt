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
    # --- Applications publiques de la FFTT (repérées au premier passage) ---
    ("Carte des clubs", "https://carte.fftt.com/"),
    ("Annuaire des organismes", "https://carte.fftt.com/organismes"),
    ("Carte : API supposée", "https://carte.fftt.com/api"),
    ("Carte : clubs", "https://carte.fftt.com/api/clubs?page=1&itemsPerPage=5"),
    ("MonClub : documentation API", "https://monclub.fftt.com/api/docs.jsonld"),
    ("MonClub : racine API", "https://monclub.fftt.com/api"),
    ("MonClub : clubs", "https://monclub.fftt.com/api/clubs?page=1&itemsPerPage=5"),
    ("MonClub : recherche de tournois (XHR connu)",
     "https://monclub.fftt.com/api/tournaments?page=1&itemsPerPage=2"),
    # --- Open data géographique ---
    ("Overpass : clubs TT avec site", "https://overpass-api.de/api/interpreter?data=[out:json][timeout:90];area[\"ISO3166-1\"=\"FR\"][admin_level=2]->.a;(nwr[\"club\"=\"table_tennis\"](area.a);nwr[\"sport\"=\"table_tennis\"][\"club\"](area.a););out count;"),
    ("Overpass : détail clubs", "https://overpass-api.de/api/interpreter?data=[out:json][timeout:90];area[\"ISO3166-1\"=\"FR\"][admin_level=2]->.a;nwr[\"club\"=\"table_tennis\"](area.a);out tags 15;"),
]

# Applications à page unique dont il faut fouiller les scripts pour trouver l'API.
SPA = [
    ("Carte des clubs", "https://carte.fftt.com/"),
    ("MonClub", "https://monclub.fftt.com/"),
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


MOTIFS_API = (
    r"[\"'`](/(?:api|v[0-9])/[A-Za-z0-9_\-/{}.]{2,60})[\"'`]",
    r"https://[A-Za-z0-9.\-]*fftt\.[a-z]{2,4}/[A-Za-z0-9_\-/.]{0,60}",
    r"[\"'`](https?://[A-Za-z0-9.\-]+/api[A-Za-z0-9_\-/.]{0,50})[\"'`]",
)


def fouiller_scripts(nom: str, url: str, client: Client) -> None:
    """Télécharge les scripts d'une application à page unique et y cherche l'adresse de l'API."""
    print("=" * 100)
    print(f"### FOUILLE DES SCRIPTS — {nom}\n    {url}")
    reponse = client.get(url)
    if reponse is None:
        print("    -> page inaccessible")
        return
    soupe = BeautifulSoup(reponse.text, "html.parser")
    sources = [s.get("src") for s in soupe.find_all("script", src=True)]
    sources = [s if s.startswith("http") else url.rstrip("/") + "/" + s.lstrip("/") for s in sources]
    print(f"    {len(sources)} script(s) : {sources[:8]}")
    trouvailles: set[str] = set()
    for source in sources[:6]:
        code = client.texte(source, taille_max=6_000_000)
        if not code:
            continue
        print(f"    · {source.split('/')[-1]} ({len(code)} caractères)")
        for motif in MOTIFS_API:
            trouvailles.update(re.findall(motif, code))
    interessantes = sorted(
        adresse for adresse in trouvailles
        if not re.search(r"\.(png|jpe?g|svg|css|woff2?|ico|map)$", adresse)
    )
    print(f"    Adresses d'API repérées ({len(interessantes)}) :")
    for adresse in interessantes[:60]:
        print("      ·", adresse[:160])


def main() -> int:
    client = Client(delai=1.0, timeout=30)
    sondes = SONDES + [(f"URL fournie {i + 1}", url) for i, url in enumerate(sys.argv[1:])]
    for nom, url in sondes:
        try:
            resumer(nom, url, client)
        except Exception as erreur:  # noqa: BLE001 - une sonde ne doit jamais arrêter les autres
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    for nom, url in SPA:
        try:
            fouiller_scripts(nom, url, client)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
