"""Recherche, téléchargement et normalisation des logos de clubs.

La logique est volontairement conservatrice : on préfère ne rien afficher plutôt que
d'afficher la bannière du sponsor ou l'icône par défaut d'un thème WordPress.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from PIL import Image, ImageChops

from . import catalogue
from .catalogue import Club
from .reseau import Client, decoder

journal = logging.getLogger("logostt")

TAILLE_MAX = 512          # côté maximal du logo enregistré, en pixels
TAILLE_MIN = 40           # en dessous, l'image est trop petite pour être un logo exploitable
POIDS_MAX_SVG = 400_000   # octets

# Mots qui trahissent une image qui n'est pas le logo du club.
REJET = re.compile(
    r"sponsor|partenaire|publicit|banniere|banner|slider|carousel|diaporama|"
    r"facebook|instagram|twitter|youtube|tiktok|linkedin|whatsapp|helloasso|"
    r"paypal|cookie|rgpd|avatar|spacer|pixel|tracking|loader|spinner|"
    r"drapeau|flag-|/flags/|emoji|smiley|captcha|placeholder|photo-|galerie|"
    r"affiche|flyer|tournoi|resultat|classement|calendrier|arbitre|joueur",
    re.I,
)
# Mots qui, eux, désignent très probablement le logo.
INDICE_LOGO = re.compile(r"logo|blason|ecusson|écusson|armoiries|identite-visuelle", re.I)
# Logos fédéraux : intéressants à repérer mais ce ne sont pas les logos des clubs.
FEDERAL = re.compile(r"fftt|federation|ligue|comite|comité", re.I)

EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/avif": ".avif",
}


@dataclass
class Candidat:
    url: str
    score: int
    origine: str

    def __str__(self) -> str:  # pragma: no cover - confort de journalisation
        return f"{self.score:>4} {self.origine:<14} {self.url[:90]}"


def _absolu(base: str, url: str | None) -> str:
    if not url:
        return ""
    url = url.strip().split(" ")[0]  # gère les attributs srcset « url 2x »
    if url.startswith("data:image/"):
        return url
    if not url or url.startswith(("javascript:", "#", "mailto:")):
        return ""
    return urljoin(base, url)


def _entier(valeur) -> int:
    try:
        return int(re.sub(r"[^0-9]", "", str(valeur or "")) or 0)
    except ValueError:
        return 0


def candidats(html: str, url_page: str, nom_club: str = "") -> list[Candidat]:
    """Classe les images de la page de la plus au moins susceptible d'être le logo."""
    soupe = BeautifulSoup(html or "", "html.parser")
    trouves: dict[str, Candidat] = {}

    def proposer(url: str, score: int, origine: str) -> None:
        url = _absolu(url_page, url)
        if not url:
            return
        if REJET.search(url):
            score -= 70
        if INDICE_LOGO.search(url):
            score += 25
        if url.lower().endswith(".svg"):
            score += 15
        if FEDERAL.search(url):
            # Logo de la fédération, de la ligue ou du comité : ce n'est pas celui du club.
            score -= 45
        if score <= 0:
            return
        connu = trouves.get(url)
        if connu is None or score > connu.score:
            trouves[url] = Candidat(url, score, origine)

    # 1. Donnée structurée schema.org : la source la plus fiable quand elle existe.
    for balise in soupe.find_all("script", type="application/ld+json"):
        try:
            donnees = json.loads(balise.string or "{}")
        except (ValueError, TypeError):
            continue
        for bloc in donnees if isinstance(donnees, list) else [donnees]:
            if not isinstance(bloc, dict):
                continue
            logo = bloc.get("logo") or bloc.get("image")
            if isinstance(logo, dict):
                logo = logo.get("url")
            if isinstance(logo, list) and logo:
                logo = logo[0] if isinstance(logo[0], str) else logo[0].get("url")
            if isinstance(logo, str):
                proposer(logo, 100, "schema.org")

    # 2. Balises <img> : on tient compte du nom de fichier, des classes et du contexte.
    mots_du_club = {m for m in re.split(r"[^a-z0-9]+", catalogue.slug(nom_club)) if len(m) > 3}
    for image in soupe.find_all("img"):
        source = image.get("src") or image.get("data-src") or image.get("data-lazy-src") or ""
        if not source and image.get("srcset"):
            source = image["srcset"].split(",")[0]
        if not source:
            continue
        signature = " ".join(
            str(image.get(attribut, "")) for attribut in ("class", "id", "alt", "title")
        )
        score = 30
        origine = "img"
        if INDICE_LOGO.search(signature):
            score = 80
            origine = "img[logo]"
        if REJET.search(signature):
            score -= 70
        parents = " ".join(
            str(parent.get("class", "")) + str(parent.get("id", ""))
            for parent in image.find_parents(limit=3)
        )
        if re.search(r"header|banner-top|navbar|brand|site-title|masthead|identite", parents, re.I):
            score += 25
        if re.search(r"footer|sidebar|widget", parents, re.I):
            score -= 20
        if mots_du_club and any(mot in catalogue.slug(signature) for mot in mots_du_club):
            score += 20
        largeur, hauteur = _entier(image.get("width")), _entier(image.get("height"))
        if largeur and hauteur:
            if largeur > 1200 or hauteur > 1200 or largeur / max(hauteur, 1) > 6:
                score -= 25   # bannière plein écran
            elif 50 <= largeur <= 900 and 30 <= hauteur <= 600:
                score += 10
        proposer(source, score, origine)

    # 3. Icônes déclarées dans l'en-tête du document.
    for lien in soupe.find_all("link", rel=True):
        rel = " ".join(lien.get("rel")).lower()
        href = lien.get("href")
        if "apple-touch-icon" in rel:
            proposer(href, 55, "apple-icon")
        elif "icon" in rel and "mask" not in rel:
            taille = max((_entier(t) for t in (lien.get("sizes") or "").split("x")), default=0)
            proposer(href, 45 if taille >= 96 else 30, "favicon")

    # 4. Images de partage social : souvent une photo, parfois le logo.
    for meta in soupe.find_all("meta"):
        propriete = (meta.get("property") or meta.get("name") or "").lower()
        if propriete in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
            proposer(meta.get("content"), 40, "og:image")
        elif propriete in {"og:logo", "vk:image"}:
            proposer(meta.get("content"), 70, "og:logo")

    # 5. Dernier recours : la favicone à l'emplacement historique.
    proposer("/favicon.ico", 10, "favicon.ico")

    return sorted(trouves.values(), key=lambda c: (-c.score, len(c.url)))


def _rogner_bordure(image: Image.Image) -> Image.Image:
    """Supprime la marge uniforme (blanche ou transparente) autour du logo."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    alpha = image.getchannel("A")
    boite = alpha.getbbox() if alpha.getextrema()[0] < 255 else None
    if boite is None:
        fond = Image.new("RGB", image.size, image.convert("RGB").getpixel((0, 0)))
        difference = ImageChops.difference(image.convert("RGB"), fond)
        boite = difference.getbbox()
    if boite and (boite[2] - boite[0]) > 8 and (boite[3] - boite[1]) > 8:
        image = image.crop(boite)
    return image


def _couleurs_dominantes(image: Image.Image, maximum: int = 4) -> list[str]:
    """Couleurs marquantes du logo, utilisées pour filtrer la galerie par couleur."""
    reduite = image.convert("RGBA").resize((64, 64))
    compteur: dict[tuple[int, int, int], int] = {}
    for rouge, vert, bleu, alpha in reduite.getdata():
        if alpha < 128:
            continue
        clair = rouge > 235 and vert > 235 and bleu > 235
        sombre = rouge < 25 and vert < 25 and bleu < 25
        if clair or sombre:
            continue
        cle = (rouge // 32 * 32 + 16, vert // 32 * 32 + 16, bleu // 32 * 32 + 16)
        compteur[cle] = compteur.get(cle, 0) + 1
    ordonnees = sorted(compteur.items(), key=lambda item: -item[1])
    return ["#%02x%02x%02x" % couleur for couleur, _ in ordonnees[:maximum]]


def _fond_conseille(image: Image.Image) -> str:
    """« sombre » si le logo est presque entièrement clair (logo blanc détouré)."""
    reduite = image.convert("RGBA").resize((48, 48))
    lumineux = total = 0
    for rouge, vert, bleu, alpha in reduite.getdata():
        if alpha < 128:
            continue
        total += 1
        if (0.2126 * rouge + 0.7152 * vert + 0.0722 * bleu) > 210:
            lumineux += 1
    return "sombre" if total and lumineux / total > 0.85 else "clair"


@dataclass
class Visuel:
    octets: bytes
    extension: str
    couleurs: list[str]
    fond: str
    largeur: int = 0
    hauteur: int = 0


def normaliser(octets: bytes, type_mime: str = "") -> Visuel | None:
    """Valide une image téléchargée et la convertit au format servi par le site."""
    if not octets or len(octets) < 60:
        return None
    entete = octets[:400].lstrip()
    if entete.startswith(b"<svg") or b"<svg" in entete or "svg" in type_mime:
        if len(octets) > POIDS_MAX_SVG:
            return None
        texte = octets.decode("utf-8", "ignore")
        if "<svg" not in texte:
            return None
        texte = re.sub(r"<script.*?</script>", "", texte, flags=re.S | re.I)
        texte = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", texte, flags=re.I)
        couleurs = []
        for couleur in re.findall(r"#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}", texte):
            couleur = couleur.lower()
            if len(couleur) == 4:
                couleur = "#" + "".join(c * 2 for c in couleur[1:])
            if couleur not in couleurs and couleur not in {"#ffffff", "#000000"}:
                couleurs.append(couleur)
        return Visuel(texte.encode("utf-8"), ".svg", couleurs[:4], "clair")

    if len(octets) < 100:
        return None
    try:
        image = Image.open(io.BytesIO(octets))
        image.load()
    except Exception:  # noqa: BLE001 - Pillow lève des exceptions très variées
        return None
    if image.format == "ICO" and getattr(image, "ico", None):
        # Un fichier .ico contient plusieurs tailles : on prend la plus grande.
        image = image.ico.getimage(max(image.ico.sizes()))
    largeur, hauteur = image.size
    if min(largeur, hauteur) < TAILLE_MIN or largeur * hauteur < TAILLE_MIN ** 2:
        return None
    if max(largeur, hauteur) / min(largeur, hauteur) > 8:
        return None

    image = _rogner_bordure(image)
    if min(image.size) < 16:
        return None
    if max(image.size) > TAILLE_MAX:
        ratio = TAILLE_MAX / max(image.size)
        image = image.resize(
            (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
            Image.LANCZOS,
        )
    couleurs = _couleurs_dominantes(image)
    if not couleurs and image.convert("RGBA").getchannel("A").getextrema()[1] == 0:
        return None  # image entièrement transparente
    sortie = io.BytesIO()
    image.save(sortie, format="WEBP", quality=88, method=6)
    return Visuel(
        sortie.getvalue(), ".webp", couleurs, _fond_conseille(image), image.width, image.height
    )


def _telecharger(client: Client, url: str) -> tuple[bytes, str]:
    if url.startswith("data:image/"):
        entete, _, charge = url.partition(",")
        try:
            octets = base64.b64decode(charge) if ";base64" in entete else charge.encode()
        except (binascii.Error, ValueError):
            return b"", ""
        return octets, entete[5:].split(";")[0]
    reponse = client.get(url, taille_max=4_000_000)
    if reponse is None:
        return b"", ""
    return reponse.content, (reponse.headers.get("Content-Type") or "").split(";")[0].lower()


def page_accueil(client: Client, site: str) -> tuple[str, str]:
    """Charge la page d'accueil du club ; renvoie (html, url finale)."""
    for url in _variantes(site):
        reponse = client.get(url)
        if reponse is not None and "html" in (reponse.headers.get("Content-Type") or "text/html"):
            return decoder(reponse), reponse.url
    return "", ""


def _variantes(site: str) -> list[str]:
    """Essaie l'URL telle quelle, puis la version HTTPS, puis le domaine racine."""
    site = catalogue.normaliser_url(site)
    if not site:
        return []
    morceaux = urlparse(site)
    variantes = [site]
    if morceaux.scheme == "http":
        variantes.insert(0, site.replace("http://", "https://", 1))
    racine = f"https://{morceaux.netloc}/"
    if racine not in variantes:
        variantes.append(racine)
    return variantes


def recuperer_logo(
    club: Club, client: Client, dossier_logos: Path, essais_max: int = 4
) -> Club:
    """Complète le club avec son logo : télécharge le meilleur candidat trouvé."""
    if not club.site_web:
        club.logo_statut = catalogue.SITE_ABSENT
        return club

    html, url_finale = page_accueil(client, club.site_web)
    if not html:
        club.logo_statut = catalogue.LOGO_ABSENT
        club.maj = catalogue.aujourdhui()
        return club
    club.site_web = url_finale or club.site_web

    liste = candidats(html, club.site_web, club.nom)
    for candidat in liste[:essais_max]:
        octets, type_mime = _telecharger(client, candidat.url)
        visuel = normaliser(octets, type_mime)
        if visuel is None:
            continue
        chemin_relatif = Path("logos") / club.dep / f"{club.cle_fichier()}{visuel.extension}"
        destination = dossier_logos.parent / chemin_relatif
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(visuel.octets)
        club.logo_fichier = chemin_relatif.as_posix()
        club.logo_source = candidat.url if not candidat.url.startswith("data:") else club.site_web
        club.logo_statut = (
            catalogue.LOGO_FAVICON if candidat.origine.startswith("favicon") else catalogue.LOGO_RECUPERE
        )
        club.couleurs = " ".join(visuel.couleurs)
        club.fond = visuel.fond
        club.maj = catalogue.aujourdhui()
        return club

    club.logo_statut = catalogue.LOGO_ABSENT
    club.maj = catalogue.aujourdhui()
    return club
