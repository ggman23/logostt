#!/usr/bin/env python3
"""Génère un aperçu du site avec un jeu de données FICTIF, sans accès réseau.

Sert à vérifier le rendu de la galerie (mise en page, filtres, fiche détaillée) avant
d'avoir lancé la vraie collecte. Le résultat est écrit dans un dossier à part : il ne
remplace jamais data/clubs.csv ni site/data.

    python3 tests/apercu_demo.py apercu/    puis    python3 -m http.server -d apercu
"""

from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from PIL import Image, ImageDraw  # noqa: E402

from ttlogos import catalogue, referentiel, site  # noqa: E402

EXEMPLES = [
    ("Club de démonstration 1", "75", "Paris", "75011", (33, 78, 189), "cercle"),
    ("Club de démonstration 2", "75", "Paris", "75013", (208, 61, 61), "raquette"),
    ("Club de démonstration 3", "77", "Melun", "77000", (18, 122, 74), "bande"),
    ("Club de démonstration 4", "78", "Versailles", "78000", (240, 165, 0), "cercle"),
    ("Club de démonstration 5", "92", "Nanterre", "92000", (103, 65, 217), "raquette"),
    ("Club de démonstration 6", "93", "Montreuil", "93100", (12, 166, 120), "bande"),
    ("Club de démonstration 7", "44", "Nantes", "44000", (25, 113, 194), "raquette"),
    ("Club de démonstration 8", "44", "Saint-Nazaire", "44600", (214, 51, 108), "cercle"),
    ("Club de démonstration 9", "49", "Angers", "49000", (134, 142, 150), "bande"),
    ("Club de démonstration 10", "35", "Rennes", "35000", (32, 91, 160), "cercle"),
    ("Club de démonstration 11", "29", "Brest", "29200", (200, 90, 20), "raquette"),
    ("Club de démonstration 12", "69", "Lyon", "69003", (176, 32, 44), "bande"),
    ("Club de démonstration 13", "38", "Grenoble", "38000", (20, 130, 160), "cercle"),
    ("Club de démonstration 14", "13", "Marseille", "13008", (0, 120, 200), "raquette"),
    ("Club de démonstration 15", "31", "Toulouse", "31000", (150, 30, 90), "bande"),
    ("Club de démonstration 16", "59", "Lille", "59000", (220, 130, 0), "cercle"),
    ("Club de démonstration 17", "67", "Strasbourg", "67000", (60, 60, 140), "raquette"),
    ("Club de démonstration 18", "33", "Bordeaux", "33000", (120, 20, 60), "bande"),
    ("Club de démonstration 19", "974", "Saint-Denis", "97400", (0, 140, 110), "cercle"),
    ("Club de démonstration 20", "2A", "Ajaccio", "20000", (40, 40, 60), "raquette"),
]


def dessiner(couleur: tuple[int, int, int], forme: str, initiales: str) -> bytes:
    image = Image.new("RGBA", (420, 260), (255, 255, 255, 0))
    dessin = ImageDraw.Draw(image)
    if forme == "cercle":
        dessin.ellipse((110, 20, 310, 220), fill=couleur)
        dessin.ellipse((150, 60, 270, 180), fill=(255, 255, 255))
    elif forme == "raquette":
        dessin.ellipse((90, 20, 290, 200), fill=couleur)
        dessin.rounded_rectangle((175, 190, 205, 245), 12, fill=(90, 60, 30))
        dessin.ellipse((300, 40, 350, 90), fill=(240, 165, 0))
    else:
        dessin.rounded_rectangle((40, 60, 380, 200), 18, fill=couleur)
        dessin.rectangle((40, 190, 380, 200), fill=(20, 20, 40))
    dessin.text((186, 96), initiales, fill=(20, 20, 40))
    tampon = io.BytesIO()
    image.save(tampon, "WEBP", quality=90)
    return tampon.getvalue()


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "apercu").resolve()
    racine = referentiel.RACINE
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for element in ("index.html", "assets"):
        source = racine / "site" / element
        cible = destination / element
        shutil.copytree(source, cible) if source.is_dir() else shutil.copy(source, cible)

    clubs = []
    for numero, (nom, dep, ville, code_postal, couleur, forme) in enumerate(EXEMPLES, start=1):
        club = catalogue.Club(
            numero=f"DEMO{numero:03d}",
            nom=nom,
            dep=dep,
            ville=ville,
            code_postal=code_postal,
            site_web="https://exemple.invalid/" if numero % 6 else "",
            source_donnees="jeu de démonstration (données fictives)",
            maj=catalogue.aujourdhui(),
        )
        club.completer_geographie()
        if numero % 7 == 0:          # quelques clubs sans logo, pour voir l'état « introuvable »
            club.logo_statut = catalogue.LOGO_ABSENT if club.site_web else catalogue.SITE_ABSENT
        else:
            chemin = Path("logos") / dep / f"{club.cle_fichier()}.webp"
            fichier = destination / chemin
            fichier.parent.mkdir(parents=True, exist_ok=True)
            initiales = "".join(mot[0] for mot in nom.split()[:3]).upper()
            fichier.write_bytes(dessiner(couleur, forme, initiales))
            club.logo_fichier = chemin.as_posix()
            club.logo_source = "https://exemple.invalid/logo.png"
            club.logo_statut = catalogue.LOGO_RECUPERE
            club.couleurs = "#%02x%02x%02x" % couleur
            club.fond = "clair"
        clubs.append(club)

    stats = site.construire(clubs, destination)
    print(f"aperçu écrit dans {destination} ({stats['clubs']} clubs fictifs, {stats['logos']} logos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
