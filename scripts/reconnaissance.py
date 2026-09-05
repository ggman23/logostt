#!/usr/bin/env python3
"""Sonde décisive : la structure exacte des annuaires retenus.

Autriche  : une page contient les 587 clubs et leurs sites — comment sont-ils groupés ?
Pays-Bas  : chaque division régionale a une page « aperçu des associations ».
Tchéquie  : le registre fédéral est-il lisible sans passer par l'anti-robot ?
Pologne   : le tableau des licences donne 487 clubs et leur voïvodie ; et les sites ?
Espagne   : dernière tentative avant de conclure.
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
        print(f"    {url}\n    exception {type(erreur).__name__}: {erreur}")
        return ""
    print(f"    {url}\n    HTTP {reponse.status_code} | {len(reponse.content)} octets")
    return reponse.text if reponse.status_code in (200, 202) else ""


def autriche(session) -> None:
    titre("AUTRICHE — structure de la page des Vereine")
    html = charger(session, "https://www.oettv.org/organisation/vereine")
    if not html:
        return
    soupe = BeautifulSoup(html, "html.parser")
    # On part d'un lien de club et on remonte : le bloc parent porte tout le reste.
    lien = soupe.find("a", href=re.compile(r"clubId%5D=\d+"))
    if lien is None:
        print("    Aucun lien de club reconnu.")
        return
    bloc = lien
    for _ in range(5):
        if bloc.parent is None:
            break
        bloc = bloc.parent
        texte = re.sub(r"\s+", " ", bloc.get_text(" ", strip=True))
        liens = [a.get("href") for a in bloc.find_all("a", href=True)]
        if len(texte) > 60 and any(str(h).startswith("http") for h in liens):
            print(f"    Bloc <{bloc.name} class={bloc.get('class')}> :")
            print("      texte :", texte[:400])
            print("      liens :", liens[:6])
            print("      HTML  :", re.sub(r"\s+", " ", str(bloc))[:900])
            break
    # Les Landesverbände servent-ils de regroupement ? On regarde les titres de la page.
    entetes = [re.sub(r"\s+", " ", h.get_text(" ", strip=True))[:60]
               for h in soupe.find_all(("h1", "h2", "h3", "h4"))]
    print("    Titres de la page :", entetes[:20])
    # Combien de clubs, combien de sites ?
    clubs = set(re.findall(r"clubId%5D=(\d+)", html))
    print(f"    {len(clubs)} identifiants de club distincts")


def pays_bas(session) -> None:
    titre("PAYS-BAS — l'aperçu des associations d'une division")
    html = charger(session, "https://gelre.nttb.nl/organisatie/overzicht-gelderse-verenigingen/")
    if html:
        soupe = BeautifulSoup(html, "html.parser")
        lignes = soupe.find_all("tr")
        print(f"    Lignes de tableau : {len(lignes)}")
        for ligne in lignes[:5]:
            cellules = [re.sub(r"\s+", " ", c.get_text(" ", strip=True))[:40]
                        for c in ligne.find_all(("td", "th"))]
            if cellules:
                print("      |", " | ".join(cellules[:6]))
        externes = sorted({a["href"] for a in soupe.find_all("a", href=True)
                           if a["href"].startswith("http") and "nttb.nl" not in a["href"]
                           and not re.search(r"facebook|google|w3\.org|wordpress", a["href"], re.I)})
        print(f"    Liens externes (sites de clubs ?) : {len(externes)} — ex. {externes[:10]}")
    # Les autres divisions ont-elles une page équivalente ?
    for division in ("holland-noord", "midden", "limburg", "west", "oost", "zuid"):
        for chemin in ("/verenigingen/", "/organisatie/verenigingen/"):
            texte = charger(session, f"https://{division}.nttb.nl{chemin}")
            if texte:
                soupe = BeautifulSoup(texte, "html.parser")
                liens = sorted({a["href"] for a in soupe.find_all("a", href=True)
                                if re.search(r"verenig", a["href"], re.I)})
                print(f"      liens « verenigingen » : {liens[:5]}")
                break


def tchequie(session) -> None:
    titre("TCHÉQUIE — le registre fédéral")
    for url in ("https://registr.ping-pong.cz/htm/",
                "https://registr.ping-pong.cz/",
                "https://stis.ping-pong.cz/"):
        html = charger(session, url)
        if not html:
            continue
        print("    Corps :", re.sub(r"\s+", " ", html)[:600])


def pologne(session) -> None:
    titre("POLOGNE — les 487 clubs et leur voïvodie ; les associations régionales")
    html = charger(session, "https://rozgrywki.pzts.pl/rozgrywki-indywidualne/club_licenses?season=18")
    if html:
        soupe = BeautifulSoup(html, "html.parser")
        lignes = soupe.find_all("tr")
        print(f"    {len(lignes)} lignes")
        for ligne in lignes[:3]:
            print("      HTML :", re.sub(r"\s+", " ", str(ligne))[:400])
        voivodies = {c.get_text(strip=True) for ligne in lignes
                     for c in ligne.find_all("td")[-1:]}
        print("    Voïvodies rencontrées :", sorted(v for v in voivodies if v)[:20])
    # Une association régionale liste-t-elle ses clubs avec leur site ?
    for url in ("http://mzts.pl/", "http://ozts.pl/", "http://dozts.pl/"):
        texte = charger(session, url)
        if not texte:
            continue
        soupe = BeautifulSoup(texte, "html.parser")
        liens = sorted({a["href"] for a in soupe.find_all("a", href=True)
                        if re.search(r"klub", a["href"], re.I)})
        print(f"      liens « klub » : {liens[:6]}")


def espagne(session) -> None:
    titre("ESPAGNE — un annuaire existe-t-il quelque part ?")
    html = charger(session, "https://www.rfetm.es/")
    if html:
        soupe = BeautifulSoup(html, "html.parser")
        menu = sorted({(a.get_text(" ", strip=True)[:30], a["href"])
                       for a in soupe.find_all("a", href=True)
                       if re.search(r"club|federac|territor|autonom", a.get_text() + a["href"], re.I)})
        print(f"    Entrées de menu « club / fédération » : {len(menu)}")
        for entree in menu[:15]:
            print("      ", entree)


def main() -> int:
    session = requests.Session()
    session.headers.update({"User-Agent": NAVIGATEUR,
                            "Accept-Language": "de,nl,cs,pl,es,en;q=0.8"})
    for sonde in (autriche, pays_bas, tchequie, pologne, espagne):
        try:
            sonde(session)
        except Exception as erreur:  # noqa: BLE001
            print(f"    -> exception : {type(erreur).__name__}: {erreur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
