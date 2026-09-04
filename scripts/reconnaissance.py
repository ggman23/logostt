#!/usr/bin/env python3
"""Dernière piste pour les sites des clubs flamands (VTTL).

Le moteur de l'AFTT ne connaît que l'aile francophone : 150 clubs flamands restent
sans adresse de site. La VTTL publie-t-elle la sienne quelque part ?
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
# Trois clubs flamands réels, pour tester les adresses qui prennent un index.
EXEMPLES = ("A003", "OVL013", "WVL021")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def examiner(session, url: str, methode: str = "get", donnees: dict | None = None) -> None:
    print(f"  — {methode.upper()} {url}" + (f" {donnees}" if donnees else ""))
    try:
        reponse = (session.post(url, data=donnees, timeout=45) if methode == "post"
                   else session.get(url, timeout=45))
    except Exception as erreur:  # noqa: BLE001
        print(f"    exception {type(erreur).__name__}: {erreur}")
        return
    print(f"    HTTP {reponse.status_code} | {len(reponse.content)} octets |"
          f" {reponse.headers.get('Content-Type')}")
    if reponse.status_code != 200:
        return
    texte = reponse.text
    if texte.lstrip().startswith(("{", "[")):
        try:
            print("    JSON :", json.dumps(json.loads(texte), ensure_ascii=False)[:600])
        except ValueError:
            print("    Extrait :", texte[:300])
        return
    if "<urlset" in texte or "<sitemapindex" in texte:
        adresses = re.findall(r"<loc>([^<]+)</loc>", texte)
        interessantes = [a for a in adresses if re.search(r"club", a, re.I)]
        print(f"    {len(adresses)} adresses, dont {len(interessantes)} « club » —"
              f" ex. {(interessantes or adresses)[:10]}")
        return
    soupe = BeautifulSoup(texte, "html.parser")
    print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
    interne = re.compile(r"vttl\.be|frbtt|aftt|facebook|instagram|youtube|twitter|linkedin|"
                         r"google|w3\.org|flickr|mailchimp|campaign-archive|sport\.vlaanderen|"
                         r"nationale-loterij|tibhar|1712\.be|shop-ping", re.I)
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
    for formulaire in soupe.find_all("form")[:3]:
        champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
        print(f"    Formulaire action={formulaire.get('action')} champs={champs[:8]}")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR})

    titre("VTTL — plans du site et pages d'annuaire")
    for url in ("https://www.vttl.be/sitemap.xml",
                "https://www.vttl.be/sitemap_index.xml",
                "https://www.vttl.be/clubs",
                "https://www.vttl.be/content/clubs",
                "https://www.vttl.be/nl/clubs",
                "https://www.vttl.be/clubzoeker"):
        examiner(session, url)

    titre("VTTL — pages de club à partir de l'index")
    for index in EXEMPLES:
        for gabarit in ("https://www.vttl.be/club/{i}",
                        "https://www.vttl.be/content/club/{i}",
                        "https://www.vttl.be/clubs/{i}"):
            examiner(session, gabarit.format(i=index))

    titre("VTTL — recherche interne du site")
    examiner(session, "https://www.vttl.be/search/node?keys=clubs")

    titre("Autre piste — annuaire indépendant")
    examiner(session, "https://www.tafeltennis.be/clubs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
