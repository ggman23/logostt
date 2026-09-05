#!/usr/bin/env python3
"""Détaille les meilleures pistes trouvées, et retente celles restées muettes.

Slovaquie et Croatie ont un annuaire complet avec les sites des clubs : on en relève
la structure exacte. La Finlande affiche 82 images sur sa page de présentation des
clubs — des logos ? Le Japon et le Portugal listent leurs fédérations régionales, ce
qui suppose un deuxième niveau.

Une douzaine de fédérations n'ont pas répondu : elles sont retentées plus patiemment,
sans exiger de certificat valide ni de HTTPS.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
import urllib3  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

urllib3.disable_warnings()
NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")


def titre(texte: str) -> None:
    print("=" * 100)
    print(f"### {texte}")


def charger(session, url: str, patient: bool = False) -> str:
    try:
        reponse = session.get(url, timeout=60 if patient else 25,
                              verify=not patient, allow_redirects=True)
    except Exception as erreur:  # noqa: BLE001
        print(f"    {url} -> {type(erreur).__name__}")
        return ""
    print(f"    {url} -> HTTP {reponse.status_code} | {len(reponse.content)} octets")
    return reponse.text if reponse.status_code == 200 else ""


def structure(html: str, nom: str, motif_interne: str) -> None:
    """Montre comment un club, son site et sa région sont agencés dans la page."""
    soupe = BeautifulSoup(html, "html.parser")
    lignes = soupe.find_all("tr")
    print(f"      {len(lignes)} lignes de tableau")
    for ligne in lignes[:4]:
        cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:32]
                    for c in ligne.find_all(("td", "th"))]
        if cellules:
            print("        |", " | ".join(cellules[:8]))
    for ligne in lignes[1:3]:
        print("        HTML :", re.sub(r"\s+", " ", str(ligne))[:400])
    externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                       if a["href"].startswith("http")
                       and not re.search(motif_interne, a["href"], re.I)})
    print(f"      {len(externes)} liens externes — ex. {externes[:8]}")
    images = [i.get("src") for i in soupe.find_all("img", src=True)]
    print(f"      {len(images)} images — ex. {images[:6]}")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR,
                            "Accept-Language": "en,sk,hr,fi,ja,pt,hu,ro,sr,sl,bg,el;q=0.7"})

    titre("SLOVAQUIE — sstz.sk/kluby")
    html = charger(session, "https://www.sstz.sk/kluby")
    if html:
        structure(html, "Slovaquie", r"sstz\.sk|facebook|instagram|youtube|google|tipos")

    titre("CROATIE — annuaire des clubs enregistrés")
    html = charger(session, "https://www.hsts.hr/index.php?option=com_hstsdata&Itemid=266")
    if html:
        structure(html, "Croatie", r"hsts\.hr|facebook|flickr|domenacom|google")

    titre("FINLANDE — présentations de clubs (82 images)")
    html = charger(session, "https://www.sptl.fi/sptl_uudet/?cat=81")
    if html:
        structure(html, "Finlande", r"sptl\.fi|facebook|spotify|instagram|youtube")

    titre("JAPON — fédérations préfectorales")
    html = charger(session, "https://www.jtta.or.jp/member-organization")
    if html:
        soupe = BeautifulSoup(html, "html.parser")
        externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                           if a["href"].startswith("http") and "jtta" not in a["href"]})
        print(f"      {len(externes)} fédérations préfectorales — ex. {externes[:12]}")

    titre("PORTUGAL — associations régionales")
    html = charger(session, "https://fptm.pt/fptm/associacoes/")
    if html:
        structure(html, "Portugal", r"fptm\.pt|facebook|crabtech|instagram")

    titre("Fédérations muettes : deuxième tentative, plus patiente")
    for nom, url in [
        ("Hongrie", "http://moatsz.hu/"),
        ("Roumanie", "http://www.frtm.ro/"),
        ("Serbie", "http://www.sts.org.rs/"),
        ("Slovénie", "http://www.nztzs.si/"),
        ("Bulgarie", "http://bftt.eu/"),
        ("Grèce", "http://www.eftt.gr/"),
        ("Luxembourg", "http://www.fltt.lu/"),
        ("Irlande", "http://www.irishtabletennis.com/"),
        ("Canada", "http://www.ttcan.ca/"),
        ("Italie", "https://www.fitet.org/index.php/societa"),
    ]:
        print(f"  — {nom}")
        page = charger(session, url, patient=True)
        if not page:
            continue
        soupe = BeautifulSoup(page, "html.parser")
        pistes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                         if re.search(r"club|klub|societ|egyesulet|egyesület|zdruz|sylog|"
                                      r"σωματε|клуб", a.get_text() + a["href"], re.I)})
        print(f"      titre : {soupe.title.get_text(' ', strip=True)[:60] if soupe.title else '?'}")
        print(f"      pistes « clubs » : {pistes[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
