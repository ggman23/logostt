#!/usr/bin/env python3
"""Repère les annuaires de clubs de cinq fédérations : Tchéquie, Pays-Bas, Espagne,
Pologne, Autriche.

Pour chaque adresse : le code de retour, la forme de la réponse, et ce qui ressemble à
une liste de clubs (tableau, liens, formulaire de recherche, données JSON).
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

# Domaines qui décorent toutes les pages : ils ne sont jamais le site d'un club.
DECOR = re.compile(r"facebook|instagram|youtube|twitter|x\.com|linkedin|tiktok|google|"
                   r"w3\.org|wordpress|jquery|bootstrap|gstatic|cloudflare|ittf|ettu", re.I)


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def examiner(session, url: str, motif_club: str = r"club|klub|vereniging|verein|oddil|oddíl") -> None:
    print(f"  — {url}")
    try:
        reponse = session.get(url, timeout=45)
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
            print("    JSON :", json.dumps(json.loads(texte), ensure_ascii=False)[:700])
        except ValueError:
            print("    Extrait :", texte[:300])
        return
    if "<urlset" in texte or "<sitemapindex" in texte:
        adresses = re.findall(r"<loc>([^<]+)</loc>", texte)
        vise = [a for a in adresses if re.search(motif_club, a, re.I)]
        print(f"    {len(adresses)} adresses, dont {len(vise)} « club » — ex. {(vise or adresses)[:10]}")
        return

    soupe = BeautifulSoup(texte, "html.parser")
    print("    Titre :", soupe.title.get_text(' ', strip=True)[:80] if soupe.title else "(aucun)")
    lignes = soupe.find_all("tr")
    print(f"    Lignes de tableau : {len(lignes)}")
    for ligne in lignes[:4]:
        cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:38]
                    for c in ligne.find_all(("td", "th"))]
        if cellules:
            print("      |", " | ".join(cellules[:7]))
    fiches = sorted({a["href"] for a in soupe.find_all("a", href=True)
                     if re.search(motif_club, a["href"], re.I)})
    print(f"    Liens « club » : {len(fiches)} — ex. {fiches[:6]}")
    externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                       if a["href"].startswith("http") and not DECOR.search(a["href"])
                       and not a["href"].startswith(url[:30])})
    print(f"    Liens externes : {len(externes)} — ex. {externes[:6]}")
    for formulaire in soupe.find_all("form")[:3]:
        champs = [c.get("name") for c in formulaire.find_all(("input", "select")) if c.get("name")]
        print(f"    Formulaire action={formulaire.get('action')} méthode={formulaire.get('method')}"
              f" champs={champs[:8]}")
    options = soupe.find_all("option")
    if len(options) > 20:
        exemples = [(o.get("value"), o.get_text(strip=True)[:30]) for o in options[1:4]]
        print(f"    {len(options)} options de menu — ex. {exemples}")
    # Une liste pilotée par JavaScript trahit son API dans les scripts de la page.
    reperes: set[str] = set()
    for script in soupe.find_all("script"):
        reperes |= set(re.findall(r'["\'](/?[\w./?=&-]{8,90}?(?:api|ajax|json|klub|club)[\w./?=&-]*)["\']',
                                  script.string or ""))
    for repere in sorted(reperes)[:6]:
        print("    Appel repéré :", repere[:120])


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR,
                            "Accept-Language": "cs,nl,es,pl,de,en;q=0.8"})

    titre("TCHÉQUIE — ČAST / STIS")
    for url in ("https://stis.ping-pong.cz/htm/",
                "https://stis.ping-pong.cz/htm/?adresar",
                "https://stis.ping-pong.cz/htm/?id=oddily",
                "https://www.ping-pong.cz/oddily",
                "https://www.ping-pong.cz/sitemap.xml"):
        examiner(session, url)

    titre("PAYS-BAS — NTTB")
    for url in ("https://www.nttb.nl/zoek-een-club/",
                "https://www.nttb.nl/wp-json/wp/v2/types",
                "https://www.nttb.nl/sitemap_index.xml",
                "https://www.nttb.nl/wp-sitemap.xml",
                "https://ttapp.nl/"):
        examiner(session, url, r"club|vereniging")

    titre("ESPAGNE — RFETM")
    for url in ("https://clubs.rfetm.es/",
                "https://www.rfetm.es/clubes",
                "https://www.rfetm.es/sitemap.xml",
                "https://www.rfetm.es/wp-json/wp/v2/types"):
        examiner(session, url, r"club")

    titre("POLOGNE — PZTS")
    for url in ("https://rozgrywki.pzts.pl/",
                "https://rozgrywki.pzts.pl/kluby",
                "https://pzts.pl/kluby/",
                "https://pzts.pl/wp-json/wp/v2/types"):
        examiner(session, url, r"klub")

    titre("AUTRICHE — ÖTTV")
    for url in ("https://www.oettv.org/organisation/vereine",
                "https://www.oettv.org/vereine",
                "https://www.oettv.org/sitemap.xml",
                # L'Autriche utilise-t-elle nuLiga, comme l'Allemagne et la Suisse ?
                "https://www.click-tt.at/cgi-bin/WebObjects/nuLigaTTAT.woa/wa/clubSearch",
                "https://oettv.nuliga.at/"):
        examiner(session, url, r"verein|club")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
