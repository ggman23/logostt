#!/usr/bin/env python3
"""Cherche, dans une trentaine de fédérations, celles dont l'annuaire est exploitable.

Plutôt que d'explorer un pays à la fois, ce script part de la page d'accueil de chaque
fédération, y repère l'entrée de menu qui mène aux clubs — dans la langue du pays — et
mesure ce que cette page contient : des clubs listés, des liens vers leurs sites, des
logos hébergés par la fédération.

Il ne collecte rien : il classe les pistes par rendement attendu en logos.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

NAVIGATEUR = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

# Fédérations nationales, avec une estimation du nombre de clubs pour ordonner l'effort.
FEDERATIONS = [
    ("Japon", "https://www.jtta.or.jp/", 7000),
    ("Italie", "https://www.fitet.org/", 1400),
    ("Angleterre", "https://www.tabletennisengland.co.uk/", 1500),
    ("Tchéquie", "https://www.ping-pong.cz/", 800),
    ("Espagne", "https://www.rfetm.es/", 800),
    ("Suède", "https://www.svenskbordtennis.com/", 600),
    ("Pays-Bas", "https://www.nttb.nl/", 600),
    ("Hongrie", "https://moatsz.hu/", 500),
    ("Roumanie", "https://www.frtm.ro/", 450),
    ("Portugal", "https://www.fptm.pt/", 400),
    ("Danemark", "https://bordtennisdanmark.dk/", 350),
    ("Norvège", "https://bordtennis.no/", 300),
    ("Slovaquie", "https://www.sstz.sk/", 300),
    ("Croatie", "https://www.hsts.hr/", 300),
    ("Serbie", "https://www.sts.org.rs/", 250),
    ("Finlande", "https://www.sptl.fi/", 200),
    ("Slovénie", "https://www.nztzs.si/", 150),
    ("Bulgarie", "https://bftt.eu/", 150),
    ("Grèce", "https://www.eftt.gr/", 150),
    ("Turquie", "https://www.tmtf.gov.tr/", 400),
    ("Ukraine", "https://ttable.org.ua/", 300),
    ("États-Unis", "https://www.usatt.org/", 300),
    ("Canada", "https://www.ttcan.ca/", 150),
    ("Australie", "https://tabletennis.org.au/", 200),
    ("Brésil", "https://cbtm.org.br/", 300),
    ("Inde", "https://ttfi.org/", 400),
    ("Corée du Sud", "https://www.koreatta.or.kr/", 400),
    ("Luxembourg", "https://www.fltt.lu/", 80),
    ("Irlande", "https://www.irishtabletennis.com/", 100),
    ("Écosse", "https://www.tabletennisscotland.co.uk/", 150),
]

# « clubs » dans les langues des fédérations sondées.
MOT_CLUB = re.compile(
    r"club|klub|kluby|kluben|klubb|clubes|clubs|verein|vereine|vereniging|"
    r"societ|förening|foreninger|seura|egyesület|egyesulet|oddil|oddíl|"
    r"asociac|asociat|associa|szakoszt|takım|kul[üu]p|команд|клуб|クラブ|加盟",
    re.I)
# Images qui ne sont jamais le logo d'un club.
DECOR = re.compile(r"logo[-_]?(fed|fftt|federation)|sponsor|banner|header|footer|"
                   r"facebook|instagram|youtube|twitter|flag|drapeau|icon", re.I)


def charger(session, url: str, taille_max: int = 8_000_000) -> str:
    try:
        reponse = session.get(url, timeout=25, allow_redirects=True)
    except Exception:  # noqa: BLE001
        return ""
    if reponse.status_code != 200 or len(reponse.content) > taille_max:
        return ""
    return reponse.text


def evaluer(html: str, url: str) -> dict:
    """Mesure ce qu'une page contient d'exploitable pour la collecte."""
    soupe = BeautifulSoup(html, "html.parser")
    hote = urlparse(url).netloc.replace("www.", "")
    lignes = len(soupe.find_all("tr"))
    articles = len(soupe.select("li")) + len(soupe.select("div.card"))
    externes = {a["href"] for a in soupe.find_all("a", href=True)
                if a["href"].startswith("http") and hote not in a["href"]
                and not re.search(r"facebook|instagram|youtube|twitter|x\.com|linkedin|"
                                  r"google|w3\.org|tiktok|wordpress|ittf|ettu",
                                  a["href"], re.I)}
    images = {i.get("src") for i in soupe.find_all("img", src=True)
              if not DECOR.search(i.get("src", ""))}
    return {"lignes": lignes, "articles": articles,
            "sites": len(externes), "images": len(images),
            "exemples": sorted(externes)[:4]}


def sonder(session, nom: str, racine: str, clubs: int) -> None:
    print("=" * 100)
    print(f"### {nom} (~{clubs} clubs) — {racine}")
    accueil = charger(session, racine)
    if not accueil:
        print("    accueil inaccessible")
        return
    soupe = BeautifulSoup(accueil, "html.parser")

    # On retient les entrées de menu qui parlent de clubs, dans la langue du pays.
    pistes: list[tuple[str, str]] = []
    for lien in soupe.find_all("a", href=True):
        intitule = lien.get_text(" ", strip=True)
        if MOT_CLUB.search(intitule) or MOT_CLUB.search(lien["href"]):
            adresse = urljoin(racine, lien["href"])
            if adresse.startswith("http") and (adresse, intitule) not in pistes:
                pistes.append((adresse, intitule[:35]))
    vues: set[str] = set()
    retenues = []
    for adresse, intitule in pistes:
        if adresse in vues:
            continue
        vues.add(adresse)
        retenues.append((adresse, intitule))
        if len(retenues) >= 4:
            break
    if not retenues:
        print("    aucune entrée de menu « clubs » repérée")
        return

    for adresse, intitule in retenues:
        page = charger(session, adresse)
        if not page:
            print(f"    « {intitule} » -> inaccessible  {adresse}")
            continue
        mesure = evaluer(page, adresse)
        print(f"    « {intitule} » : {mesure['lignes']} lignes, {mesure['articles']} éléments,"
              f" {mesure['sites']} liens externes, {mesure['images']} images")
        print(f"      {adresse}")
        if mesure["exemples"]:
            print(f"      ex. {mesure['exemples']}")


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR,
                            "Accept-Language": "en,fr,de,it,es,sv,da,no,fi,hu,pl,cs;q=0.7"})
    for nom, racine, clubs in FEDERATIONS:
        try:
            sonder(session, nom, racine, clubs)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
