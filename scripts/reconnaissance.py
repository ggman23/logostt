#!/usr/bin/env python3
"""Structure exacte des annuaires slovaque et finlandais.

Slovaquie : 897 Ko, 61 liens externes, mais aucun tableau — comment un club est-il
            agencé dans la page ?
Finlande  : 87 images dont « MBF_logo-2.jpg », « PT-Espoo.png » : la fédération
            héberge-t-elle les logos de ses clubs, comme l'Allemagne ?
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def charger(session, url: str) -> str:
    try:
        reponse = session.get(url, timeout=60)
    except Exception as erreur:  # noqa: BLE001
        print(f"    {url} -> {type(erreur).__name__}")
        return ""
    print(f"    {url} -> HTTP {reponse.status_code} | {len(reponse.content)} octets")
    return reponse.text if reponse.status_code == 200 else ""


def bloc_autour(soupe, lien, profondeur: int = 5) -> None:
    """Remonte depuis un lien de club jusqu'au bloc qui porte toute sa fiche."""
    bloc = lien
    for _ in range(profondeur):
        if bloc.parent is None:
            break
        bloc = bloc.parent
        texte = re.sub(r"\s+", " ", bloc.get_text(" ", strip=True))
        if len(texte) > 50:
            print(f"    Bloc <{bloc.name} class={bloc.get('class')}> :")
            print("      texte :", texte[:300])
            print("      HTML  :", re.sub(r"\s+", " ", str(bloc))[:800])
            return


def slovaquie(session) -> None:
    titre("SLOVAQUIE — comment un club est-il agencé ?")
    html = charger(session, "https://www.sstz.sk/kluby")
    if not html:
        return
    soupe = BeautifulSoup(html, "html.parser")
    lien = soupe.find("a", href=re.compile(r"kstztn\.sk|estranky|webnode|wordpress"))
    if lien is None:
        lien = next((a for a in soupe.find_all("a", href=True)
                     if a["href"].startswith("http") and "sstz.sk" not in a["href"]), None)
    if lien is None:
        print("    aucun lien de club repéré")
        return
    bloc_autour(soupe, lien)
    # Combien de fiches la page contient-elle, et sous quelle balise ?
    for selecteur in ("div.club", "div.card", "tr", "li", "div.row", "article", "div.item"):
        trouves = soupe.select(selecteur)
        if len(trouves) > 30:
            print(f"    {selecteur} : {len(trouves)} éléments")
    entetes = [re.sub(r"\s+", " ", h.get_text(" ", strip=True))[:50]
               for h in soupe.find_all(("h2", "h3", "h4", "h5"))]
    print(f"    {len(entetes)} titres — ex. {entetes[:12]}")


def finlande(session) -> None:
    titre("FINLANDE — la fédération héberge-t-elle les logos ?")
    html = charger(session, "https://www.sptl.fi/sptl_uudet/?cat=81")
    if not html:
        return
    soupe = BeautifulSoup(html, "html.parser")
    image = soupe.find("img", src=re.compile(r"wp-content/uploads"))
    if image is not None:
        bloc_autour(soupe, image)
    articles = soupe.select("article") or soupe.select("div.post")
    print(f"    {len(articles)} articles de présentation")
    for article in articles[:3]:
        titre_article = article.find(("h1", "h2", "h3"))
        images = [i.get("src") for i in article.find_all("img", src=True)]
        liens = [a["href"] for a in article.find_all("a", href=True)
                 if a["href"].startswith("http") and "sptl.fi" not in a["href"]]
        print(f"      « {titre_article.get_text(' ', strip=True)[:40] if titre_article else '?'} »"
              f" images={images[:2]} liens={liens[:2]}")
    # La rubrique est-elle paginée ?
    pagination = [a["href"] for a in soupe.find_all("a", href=True)
                  if re.search(r"paged|page/\d|cat=81.*page", a["href"])]
    print(f"    pagination : {sorted(set(pagination))[:6]}")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR, "Accept-Language": "sk,fi,en;q=0.8"})
    for sonde in (slovaquie, finlande):
        try:
            sonde(session)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
