#!/usr/bin/env python3
"""Deuxième passe sur les quatre annuaires qui ont résisté.

Tchéquie : le système fédéral renvoie un 202 d'anti-robot — le registre est-il ouvert ?
Pays-Bas : le moteur est en JavaScript, mais les neuf divisions régionales ont leur site.
Espagne  : l'espace clubs demande une connexion — le site public liste-t-il autre chose ?
Pologne  : les licences par club et les seize associations régionales.
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
DECOR = re.compile(r"facebook|instagram|youtube|twitter|x\.com|linkedin|tiktok|google|"
                   r"w3\.org|wordpress|jquery|bootstrap|gstatic|cloudflare|ittf|ettu|"
                   r"whatsapp|pinterest|europa\.eu", re.I)


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def examiner(session, url: str, motif: str = r"club|klub|oddil|oddíl|vereniging|vereine",
             donnees: dict | None = None) -> str:
    print(f"  — {url}" + (f"  {donnees}" if donnees else ""))
    try:
        reponse = (session.post(url, data=donnees, timeout=45) if donnees
                   else session.get(url, timeout=45))
    except Exception as erreur:  # noqa: BLE001
        print(f"    exception {type(erreur).__name__}: {erreur}")
        return ""
    print(f"    HTTP {reponse.status_code} | {len(reponse.content)} octets |"
          f" {reponse.headers.get('Content-Type')}")
    texte = reponse.text
    if reponse.status_code not in (200, 202):
        return ""
    if len(texte) < 1500:
        print("    Corps entier :", re.sub(r"\s+", " ", texte)[:900])
        return texte
    if texte.lstrip().startswith(("{", "[")):
        try:
            print("    JSON :", json.dumps(json.loads(texte), ensure_ascii=False)[:700])
        except ValueError:
            print("    Extrait :", texte[:300])
        return texte
    if "<urlset" in texte or "<sitemapindex" in texte:
        adresses = re.findall(r"<loc>([^<]+)</loc>", texte)
        vise = [a for a in adresses if re.search(motif, a, re.I)]
        print(f"    {len(adresses)} adresses, dont {len(vise)} visées — ex. {(vise or adresses)[:10]}")
        return texte

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
                     if re.search(motif, a["href"], re.I)})
    print(f"    Liens visés : {len(fiches)} — ex. {fiches[:6]}")
    hote = re.match(r"https?://[^/]+", url)
    externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                       if a["href"].startswith("http") and not DECOR.search(a["href"])
                       and not (hote and a["href"].startswith(hote.group(0)))})
    print(f"    Liens externes : {len(externes)} — ex. {externes[:8]}")
    return texte


def tchequie(session) -> None:
    titre("TCHÉQUIE — le registre est-il ouvert ?")
    for url in ("https://registr.ping-pong.cz/htm/",
                "https://old.ping-pong.cz/",
                "https://old.ping-pong.cz/oddily",
                "https://stis.ping-pong.cz/htm/?id=adresar"):
        examiner(session, url)
    # La page /oddily est une application : son code source nomme peut-être son API.
    html = examiner(session, "https://www.ping-pong.cz/oddily")
    if html:
        soupe = BeautifulSoup(html, "html.parser")
        reperes: set[str] = set()
        for script in soupe.find_all("script", src=True):
            reperes.add(script["src"])
        for script in soupe.find_all("script"):
            reperes |= set(re.findall(r'["\'](/[\w./?=&-]{6,80})["\']', script.string or ""))
        print("    Ressources de la page :", sorted(reperes)[:20])


def pays_bas(session) -> None:
    titre("PAYS-BAS — les divisions régionales listent-elles leurs clubs ?")
    for url in ("https://gelre.nttb.nl/verenigingen/",
                "https://gelre.nttb.nl/",
                "https://limburg.nttb.nl/",
                "https://www.nttb.nl/wp-json/",
                "https://www.tafeltennis.nl/"):
        examiner(session, url, r"club|vereniging")
    # Le moteur de recherche du site fédéral passe par admin-ajax : quelle action ?
    html = examiner(session, "https://www.nttb.nl/zoek-een-club/", r"club|vereniging")
    if html:
        for cle in ("action", "nonce", "ajaxurl", "rest_url", "clubs"):
            for trouve in list(re.finditer(rf'["\']{cle}["\']\s*:\s*["\']([^"\']{{3,80}})["\']',
                                           html))[:4]:
                print(f"    « {cle} » : {trouve.group(1)}")


def espagne(session) -> None:
    titre("ESPAGNE — le site fédéral, sans www et par ses chemins usuels")
    for url in ("https://rfetm.es/",
                "https://rfetm.es/clubes/",
                "https://rfetm.es/wp-json/wp/v2/types",
                "https://rfetm.es/sitemap_index.xml",
                "https://www.rfetm.es/"):
        examiner(session, url, r"club")


def pologne(session) -> None:
    titre("POLOGNE — licences par club et associations régionales")
    for url in ("https://rozgrywki.pzts.pl/rozgrywki-indywidualne/club_licenses?season=18",
                "https://rozgrywki.pzts.pl/rozgrywki-indywidualne/kluby",
                "https://www.pzts.pl/wp-json/wp/v2/pages?search=kluby&per_page=5",
                "https://www.pzts.pl/struktura/wojewodzkie-zwiazki/"):
        examiner(session, url, r"klub|zwiaz|związ")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR,
                            "Accept-Language": "cs,nl,es,pl,en;q=0.8"})
    for sonde in (tchequie, pays_bas, espagne, pologne):
        try:
            sonde(session)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
