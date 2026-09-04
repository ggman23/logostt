"""Tests hors ligne du pipeline : référentiel, catalogue, extraction de logos, génération du site."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from PIL import Image, ImageDraw  # noqa: E402

from ttlogos import (  # noqa: E402
    angleterre, belgique, carte, catalogue, clicktt, logos, referentiel, site,
)


def image_png(taille=(400, 200), couleur=(20, 70, 190)) -> bytes:
    image = Image.new("RGB", taille, "white")
    ImageDraw.Draw(image).ellipse(
        (taille[0] // 4, taille[1] // 6, taille[0] * 3 // 4, taille[1] * 5 // 6), fill=couleur
    )
    tampon = io.BytesIO()
    image.save(tampon, "PNG")
    return tampon.getvalue()


class TestReferentiel(unittest.TestCase):
    def test_couverture_de_la_france(self):
        deps = referentiel.departements()
        self.assertEqual(len(deps), 103)
        metropole = [d for d in deps.values() if d.zone == "metropole"]
        self.assertEqual(len(metropole), 96)  # 94 + Corse (2A/2B) + Paris
        self.assertEqual(deps["75"].ligue_code, "IDF")
        self.assertEqual(deps["974"].ligue_nom, "La Réunion")

    def test_selection_par_ligue_ou_departement(self):
        self.assertEqual(len(referentiel.codes_departements("BRE")), 4)
        # l'ordre suit le référentiel (Île-de-France avant Pays de la Loire)
        self.assertEqual(referentiel.codes_departements("75,44"), ["75", "44"])
        self.assertEqual(len(referentiel.codes_departements("tous")), 103)
        with self.assertRaises(SystemExit):
            referentiel.codes_departements("ZZ")

    def test_departement_depuis_code_postal(self):
        self.assertEqual(referentiel.dep_depuis_code_postal("75012"), "75")
        self.assertEqual(referentiel.dep_depuis_code_postal("20000"), "2A")
        self.assertEqual(referentiel.dep_depuis_code_postal("20600"), "2B")
        self.assertEqual(referentiel.dep_depuis_code_postal("97490"), "974")
        self.assertEqual(referentiel.dep_depuis_code_postal(""), "")


class TestCatalogue(unittest.TestCase):
    def test_aller_retour_csv(self):
        club = catalogue.Club(numero="07750001", nom="Ping Test", code_postal="75011", ville="Paris")
        club.completer_geographie()
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "clubs.csv"
            catalogue.enregistrer([club], chemin)
            relus = catalogue.charger(chemin)
        self.assertEqual(len(relus), 1)
        self.assertEqual(relus[0].ligue_code, "IDF")
        self.assertEqual(relus[0].dep_nom, "Paris")

    def test_normalisation_des_urls(self):
        self.assertEqual(catalogue.normaliser_url("www.club.fr"), "http://www.club.fr")
        self.assertEqual(catalogue.normaliser_url("https://club.fr/ping"), "https://club.fr/ping")
        self.assertEqual(catalogue.normaliser_url("contact@club.fr"), "")
        self.assertEqual(catalogue.normaliser_url("néant"), "")

    def test_fusion_conserve_le_travail_sur_les_logos(self):
        ancien = catalogue.Club(numero="1", nom="Club A", dep="75", site_web="https://a.fr",
                                logo_fichier="logos/75/1-a.webp", logo_statut=catalogue.LOGO_RECUPERE)
        identique = catalogue.Club(numero="1", nom="Club A", dep="75", site_web="https://a.fr")
        fusion = catalogue.fusionner([ancien], [identique], {"75"})
        self.assertEqual(fusion[0].logo_fichier, "logos/75/1-a.webp")

        demenage = catalogue.Club(numero="1", nom="Club A", dep="75", site_web="https://nouveau.fr")
        fusion = catalogue.fusionner([ancien], [demenage], {"75"})
        self.assertEqual(fusion[0].logo_fichier, "")
        self.assertEqual(fusion[0].logo_statut, catalogue.SITE_ABSENT)

    def test_fusion_supprime_les_clubs_disparus_du_departement(self):
        ancien = catalogue.Club(numero="1", nom="Disparu", dep="75")
        autre = catalogue.Club(numero="2", nom="Ailleurs", dep="44")
        fusion = catalogue.fusionner([ancien, autre], [], {"75"})
        self.assertEqual([c.numero for c in fusion], ["2"])

    def test_corrections_manuelles(self):
        clubs = [catalogue.Club(numero="1", nom="A", site_web="https://ancien.fr",
                                logo_fichier="x.webp", logo_statut=catalogue.LOGO_RECUPERE),
                 catalogue.Club(numero="2", nom="B")]
        corrections = {
            "1": catalogue.Correction(numero="1", site_web="https://vrai-site.fr"),
            "2": catalogue.Correction(numero="2", exclure="oui"),
        }
        resultat = catalogue.appliquer_corrections(clubs, corrections)
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0].site_web, "https://vrai-site.fr")
        self.assertEqual(resultat[0].logo_fichier, "")


class TestExtractionLogo(unittest.TestCase):
    PAGE = """
    <html><head>
      <link rel="apple-touch-icon" href="/apple.png">
      <meta property="og:image" content="/img/photo-salle.jpg">
    </head><body>
      <header><img src="/img/logo-astt.png" alt="Logo ASTT" width="200" height="80"></header>
      <div class="slider"><img src="/img/banniere.jpg" width="1900" height="500"></div>
      <footer><img src="/img/sponsors/banque.png" alt="sponsor"><img src="/img/logo-fftt.png" alt="FFTT"></footer>
    </body></html>
    """

    def test_le_logo_du_club_arrive_en_tete(self):
        classement = logos.candidats(self.PAGE, "https://astt.fr/", "ASTT")
        self.assertEqual(classement[0].url, "https://astt.fr/img/logo-astt.png")
        urls = [c.url for c in classement]
        self.assertNotIn("https://astt.fr/img/sponsors/banque.png", urls)
        self.assertNotIn("https://astt.fr/img/banniere.jpg", urls)
        self.assertNotIn("https://astt.fr/img/logo-fftt.png", urls)  # logo fédéral, rejeté

    def test_donnee_structuree_prioritaire(self):
        page = '<script type="application/ld+json">{"logo":"/logo.svg"}</script><img src="/autre.png">'
        classement = logos.candidats(page, "https://c.fr/")
        self.assertEqual(classement[0].url, "https://c.fr/logo.svg")


    def test_faux_positifs_rencontres_en_production(self):
        """Cas réels relevés lors de la collecte du Cher : l'icône de la plateforme
        d'hébergement, le bouton Google+ et le logo du conseil départemental ne
        doivent jamais être pris pour le logo du club."""
        cas = [
            ("https://aubignytt.sportsregions.fr/",
             '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
             '<img class="logo" src="/media/uploaded/sites/1/association/logo-aubigny.png">',
             "https://aubignytt.sportsregions.fr/media/uploaded/sites/1/association/logo-aubigny.png"),
            ("https://ententepongiste.gracay.info/",
             '<img src="/google_logo.png"><img class="logo" src="/img/logo-club.png">',
             "https://ententepongiste.gracay.info/img/logo-club.png"),
            ("https://vierzonping.wordpress.com/",
             '<img src="/wp-content/uploads/logo_cher.png">'
             '<img class="logo" src="/wp-content/uploads/entete-vierzon.png">',
             "https://vierzonping.wordpress.com/wp-content/uploads/entete-vierzon.png"),
        ]
        for page, html, attendu in cas:
            with self.subTest(page=page):
                classement = logos.candidats(html, page, "Club")
                self.assertEqual(classement[0].url, attendu)

    def test_habillage_et_logo_de_commune_ecartes(self):
        """Autres faux positifs relevés sur le terrain : l'icône « app mobile » d'une
        plateforme, un pictogramme de contact, et le logo de la commune."""
        cas = [
            ("https://aubignytt.sportsregions.fr/", "TT AUBIGNY", "",
             '<img src="/images/common/mobile-app.png">'
             '<img class="logo" src="/media/uploaded/blason.png">',
             "blason.png"),
            ("https://ententepongiste.gracay.info/", "E.P. GRACAY", "",
             '<img src="/contact_logo.png"><img class="logo" src="/entente.png">',
             "entente.png"),
            ("https://vierzonping.wordpress.com/", "VIERZON PING", "Vierzon",
             '<img src="/uploads/logo-vierzon.png">'
             '<img class="logo" src="/uploads/logo-vierzon-ping.png">',
             "logo-vierzon-ping.png"),
        ]
        for page, nom, ville, html, attendu in cas:
            with self.subTest(page=page):
                classement = logos.candidats(html, page, nom, ville)
                self.assertTrue(classement[0].url.endswith(attendu), classement[0].url)

    def test_le_vrai_logo_reste_trouvable_sur_une_plateforme_mutualisee(self):
        """Écarter l'icône d'une plateforme ne doit pas écarter les images qu'elle sert."""
        classement = logos.candidats(
            '<img class="logo" src="/media/uploaded/logo-du-club.png">',
            "https://monclub.clubeo.com/", "Mon Club")
        self.assertTrue(classement)
        self.assertIn("logo-du-club.png", classement[0].url)

    def test_normalisation_des_images(self):
        visuel = logos.normaliser(image_png(), "image/png")
        self.assertEqual(visuel.extension, ".webp")
        self.assertTrue(visuel.couleurs)
        self.assertEqual(visuel.fond, "clair")
        self.assertIsNone(logos.normaliser(image_png((20, 20)), "image/png"))
        self.assertIsNone(logos.normaliser(b"pas une image", "image/png"))

    def test_svg_nettoye(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect fill="#1A4FBE"/></svg>'
        visuel = logos.normaliser(svg, "image/svg+xml")
        self.assertEqual(visuel.extension, ".svg")
        self.assertNotIn(b"script", visuel.octets)
        self.assertEqual(visuel.couleurs, ["#1a4fbe"])


    def test_le_logo_de_la_federation_est_rejete(self):
        classement = logos.candidats(
            '<img class="logo" src="/wp-content/uploads/logo-fftt.png">', "https://club.fr/", "Club")
        self.assertNotIn("logo-fftt.png", " ".join(c.url for c in classement))

    def test_une_image_partagee_par_deux_clubs_est_ecartee(self):
        """Favicone d'hébergeur, logo de thème ou de partenaire : si deux clubs
        aboutissent au même fichier, ce n'est le logo d'aucun des deux."""
        with tempfile.TemporaryDirectory() as dossier:
            site_ = Path(dossier)
            (site_ / "logos" / "35").mkdir(parents=True)
            (site_ / "logos" / "67").mkdir(parents=True)
            commun = image_png()
            (site_ / "logos" / "35" / "a.webp").write_bytes(commun)
            (site_ / "logos" / "67" / "b.webp").write_bytes(commun)
            (site_ / "logos" / "35" / "propre.webp").write_bytes(image_png(couleur=(200, 30, 30)))
            (site_ / "logos" / "35" / "oublie.webp").write_bytes(b"orphelin")
            clubs = [
                catalogue.Club(numero="1", dep="35", logo_fichier="logos/35/a.webp",
                               logo_statut=catalogue.LOGO_RECUPERE, couleurs="#111111"),
                catalogue.Club(numero="2", dep="67", logo_fichier="logos/67/b.webp",
                               logo_statut=catalogue.LOGO_RECUPERE),
                catalogue.Club(numero="3", dep="35", logo_fichier="logos/35/propre.webp",
                               logo_statut=catalogue.LOGO_RECUPERE),
            ]
            self.assertEqual(logos.dedoublonner(clubs, site_), 2)
            self.assertEqual([c.logo_statut for c in clubs],
                             [catalogue.LOGO_ABSENT, catalogue.LOGO_ABSENT, catalogue.LOGO_RECUPERE])
            self.assertEqual(clubs[0].couleurs, "")
            self.assertFalse((site_ / "logos" / "35" / "a.webp").exists())
            self.assertEqual(logos.supprimer_les_orphelins(clubs, site_), 1)
            self.assertTrue((site_ / "logos" / "35" / "propre.webp").exists())


    def test_une_photographie_est_distinguee_d_un_logo(self):
        """Une photo de salle ne doit pas finir en logo de club."""
        import random
        random.seed(4)
        photo = Image.new("RGB", (64, 64))
        photo.putdata([(random.randrange(256), random.randrange(256), random.randrange(256))
                       for _ in range(64 * 64)])
        self.assertTrue(logos._est_photographie(photo))

        logo = Image.new("RGB", (300, 200), "white")
        ImageDraw.Draw(logo).ellipse((40, 20, 260, 180), fill=(20, 70, 190))
        self.assertFalse(logos._est_photographie(logo))


    def test_marques_de_plateformes_et_boutons_ecartes(self):
        """Logo Google, badge « propulsé par », bouton de planning : pas des logos de club."""
        classement = logos.candidats(
            '<img src="/img/googlelogo_color_272x92dp.png">'
            '<img src="/img/assoconnect.svg">'
            '<img src="/img/bouton-planning-entrainements.png">'
            '<img class="logo" src="/img/logo-du-club.png">',
            "https://club.fr/", "Club")
        self.assertEqual(classement[0].url, "https://club.fr/img/logo-du-club.png")
        retenus = " ".join(c.url for c in classement)
        for indesirable in ("googlelogo", "assoconnect", "planning"):
            self.assertNotIn(indesirable, retenus)


    def test_sponsors_allemands_ecartes(self):
        """Faux positifs relevés sur les sites allemands : entreprises partenaires,
        banques et enceintes sponsorisées, très présentes en pied de page."""
        classement = logos.candidats(
            '<img src="/img/pj-bauelemente.png">'
            '<img src="/img/elektromaschinenbau-broeking.jpg">'
            '<img src="/img/reiner-meutsch-arena.jpg">'
            '<img src="/img/sparkasse.png">'
            '<img class="logo" src="/img/tsv-vordorf-wappen.png">',
            "https://tsv-vordorf.de/", "TSV Vordorf")
        self.assertEqual(classement[0].url, "https://tsv-vordorf.de/img/tsv-vordorf-wappen.png")
        retenus = " ".join(c.url for c in classement)
        for indesirable in ("bauelemente", "maschinenbau", "arena", "sparkasse"):
            self.assertNotIn(indesirable, retenus)

    def test_variantes_d_url(self):
        self.assertEqual(
            logos._variantes("http://club.fr/ping"),
            ["https://club.fr/ping", "http://club.fr/ping", "https://club.fr/"],
        )


class TestGenerationDuSite(unittest.TestCase):
    def test_donnees_du_site(self):
        clubs = [
            catalogue.Club(numero="1", nom="A", dep="75", ville="Paris", site_web="https://a.fr",
                           logo_fichier="logos/75/1-a.webp", logo_statut=catalogue.LOGO_RECUPERE,
                           couleurs="#1a4fbe #d64545"),
            catalogue.Club(numero="2", nom="B", dep="44", ville="Nantes"),
        ]
        for club in clubs:
            club.completer_geographie()
        with tempfile.TemporaryDirectory() as dossier:
            stats = site.construire(clubs, Path(dossier))
            donnees = json.loads((Path(dossier) / "data" / "clubs.json").read_text(encoding="utf-8"))
        self.assertEqual(stats["clubs"], 2)
        self.assertEqual(stats["logos"], 1)
        self.assertEqual(stats["sites"], 1)
        idf = next(l for l in stats["ligues"] if l["code"] == "IDF")
        self.assertEqual(idf["clubs"], 1)
        premier = next(c for c in donnees["clubs"] if c["id"] == "1")
        self.assertEqual(premier["familles"], ["bleu", "rouge"])
        self.assertEqual(premier["ligueNom"], "Île-de-France")

    def test_familles_de_couleurs(self):
        self.assertEqual(site.famille_couleur("#1971c2"), "bleu")
        self.assertEqual(site.famille_couleur("#e03131"), "rouge")
        self.assertEqual(site.famille_couleur("#2f9e44"), "vert")
        self.assertEqual(site.famille_couleur("#f1f3f5"), "neutre")
        self.assertEqual(site.famille_couleur("zzz"), "")



class TestBoutABout(unittest.TestCase):
    """Vérifie la chaîne complète (HTTP → analyse → fichier) sur un site servi localement."""

    @classmethod
    def setUpClass(cls):
        import http.server
        import threading

        cls.dossier = tempfile.TemporaryDirectory()
        racine = Path(cls.dossier.name)
        (racine / "img").mkdir()
        (racine / "img" / "logo-club.png").write_bytes(image_png())
        (racine / "img" / "banniere.jpg").write_bytes(image_png((1600, 300), (200, 200, 200)))
        (racine / "index.html").write_text(
            '<html><head><title>ASTT</title></head><body>'
            '<header><img src="/img/logo-club.png" alt="Logo ASTT"></header>'
            '<div class="slider"><img src="/img/banniere.jpg"></div>'
            "</body></html>",
            encoding="utf-8",
        )
        cls.club_xml = (
            '<?xml version="1.0" encoding="ISO-8859-1"?><liste>'
            "<club><numero>07750123</numero><nom>PING TEST</nom></club></liste>"
        )
        (racine / "xml_club_dep2.php").write_text(cls.club_xml, encoding="utf-8")

        classe = http.server.SimpleHTTPRequestHandler
        classe.log_message = lambda *args, **kwargs: None
        cls.serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), classe)
        cls.serveur.RequestHandlerClass.directory = str(racine)
        cls.serveur.RequestHandlerClass = type(
            "Handler", (classe,), {"__init__": lambda self, *a, **k: classe.__init__(self, *a, directory=str(racine), **k)}
        )
        cls.base = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.dossier.cleanup()

    def test_recuperation_du_logo_sur_un_site(self):
        from ttlogos.reseau import Client

        club = catalogue.Club(numero="07750123", nom="ASTT", dep="75", site_web=self.base)
        with tempfile.TemporaryDirectory() as sortie:
            dossier_site = Path(sortie) / "site"
            logos.recuperer_logo(club, Client(delai=0), dossier_site / "logos")
            self.assertEqual(club.logo_statut, catalogue.LOGO_RECUPERE)
            self.assertTrue(club.logo_fichier.startswith("logos/75/"))
            fichier = dossier_site / club.logo_fichier
            self.assertTrue(fichier.exists())
            self.assertGreater(fichier.stat().st_size, 200)
        self.assertIn("logo-club.png", club.logo_source)
        self.assertTrue(club.couleurs)

    def test_lecture_du_xml_fftt(self):
        from ttlogos import fftt
        from ttlogos.reseau import Client

        api = fftt.ApiFFTT(Client(delai=0), "", "")
        fftt.BASE_OUVERTE = self.base
        try:
            clubs = api.clubs_du_departement("75")
        finally:
            fftt.BASE_OUVERTE = "https://www.fftt.com/mobile/pxml"
        self.assertEqual(clubs, [{"numero": "07750123", "nom": "PING TEST"}])

    def test_club_construit_depuis_une_fiche(self):
        from ttlogos import fftt

        club = fftt.club_depuis_fiche(
            "35",
            {"numero": "08350045", "nom": "TT RENNAIS"},
            {"nom": "TT RENNAIS", "villesalle": "RENNES", "codepsalle": "35000",
             "web": "www.ttrennais.fr", "latitude": "48.11", "longitude": "-1.68"},
        )
        self.assertEqual(club.site_web, "http://www.ttrennais.fr")
        self.assertEqual(club.ville, "Rennes")
        self.assertEqual(club.ligue_code, "BRE")
        self.assertEqual(club.logo_statut, catalogue.LOGO_ABSENT)

class TestAnnuairePublic(unittest.TestCase):
    """Extraction depuis l'annuaire public de la FFTT (balisage réel, capturé en ligne)."""

    ECHANTILLONS = Path(__file__).resolve().parent / "echantillons"

    def test_liste_des_clubs(self):
        html = (self.ECHANTILLONS / "annuaire_organismes.html").read_text(encoding="utf-8")

        class ClientFictif:
            def texte(self, *args, **kwargs):
                return html

        clubs = carte.liste_des_clubs(ClientFictif())
        self.assertEqual(len(clubs), 3)
        self.assertIn({"numero": "04180613", "nom": "CJM BOURGES TT"}, clubs)

    def test_fiche_club(self):
        html = (self.ECHANTILLONS / "fiche_club.html").read_text(encoding="utf-8")
        club = carte.club_depuis_fiche("04180613", html)
        self.assertEqual(club.nom, "CJM BOURGES TT")
        self.assertEqual(club.site_web, "http://cjmbourgestt.e-monsite.com/")
        self.assertEqual((club.code_postal, club.ville), ("18000", "Bourges"))
        self.assertEqual((club.dep, club.ligue_code), ("18", "CVL"))
        self.assertIn("YVES DU MANOIR", club.salle)
        self.assertEqual(club.logo_statut, catalogue.LOGO_ABSENT)

    def test_les_donnees_personnelles_ne_sont_pas_reprises(self):
        """La fiche affiche un correspondant : rien de tout cela ne doit être enregistré."""
        html = (self.ECHANTILLONS / "fiche_club.html").read_text(encoding="utf-8")
        club = carte.club_depuis_fiche("04180613", html)
        enregistre = " ".join(str(valeur) for valeur in vars(club).values())
        for donnee in ("BRUNET", "Jean-Paul", "06 07 19 12 38", "remyliam1@yahoo.fr"):
            self.assertNotIn(donnee, enregistre)

    def test_les_liens_federaux_ne_sont_pas_pris_pour_le_site_du_club(self):
        html = (self.ECHANTILLONS / "fiche_club.html").read_text(encoding="utf-8")
        sans_site = html.replace('<a href="http://cjmbourgestt.e-monsite.com/" target="_blank">'
                                 'http://cjmbourgestt.e-monsite.com/</a>', "")
        club = carte.club_depuis_fiche("04180613", sans_site)
        self.assertEqual(club.site_web, "")
        self.assertEqual(club.logo_statut, catalogue.SITE_ABSENT)

    def test_fiche_vide_si_le_club_n_existe_pas(self):
        self.assertIsNone(carte.club_depuis_fiche("07750123", "<html><body></body></html>"))

    def test_departement_deduit_du_numero(self):
        self.assertEqual(carte.dep_probable("04180613"), "18")
        self.assertEqual(carte.dep_probable("07750045"), "75")
        self.assertEqual(carte.dep_probable(""), "")


class TestAnnuaireAllemand(unittest.TestCase):
    """Extraction depuis click-TT, l'annuaire public du DTTB (balisage réel)."""

    ECHANTILLONS = Path(__file__).resolve().parent / "echantillons"

    def fiche(self):
        return (self.ECHANTILLONS / "fiche_clicktt.html").read_text(encoding="utf-8")

    def test_liste_des_clubs(self):
        html = (self.ECHANTILLONS / "recherche_clicktt.html").read_text(encoding="utf-8")
        resultats = clicktt._lire_resultats(html)
        self.assertEqual(len(resultats), 3)
        self.assertEqual(resultats[0], {"id": "3983", "nom": "TGV Eintracht Abstatt",
                                        "numero": "2053001"})

    def test_fiche_club(self):
        club = clicktt.club_depuis_fiche("3983", self.fiche())
        self.assertEqual(club.pays, "DE")
        self.assertEqual(club.nom, "TGV Eintracht Abstatt")
        self.assertEqual(club.ligue_nom, "Tischtennis Baden-Württemberg e.V.")
        self.assertEqual(club.site_web, "http://www.tgv-abstatt-tt.de/")
        self.assertEqual((club.code_postal, club.ville), ("74232", "Abstatt"))
        self.assertEqual((club.dep, club.dep_nom), ("D74", "PLZ 74"))
        self.assertIn("2053001", club.source_donnees)

    def test_les_donnees_personnelles_ne_sont_pas_reprises(self):
        club = clicktt.club_depuis_fiche("3983", self.fiche())
        enregistre = " ".join(str(valeur) for valeur in vars(club).values())
        for donnee in ("Kucher", "Alexander", "07062/9039405"):
            self.assertNotIn(donnee, enregistre)

    def test_logo_officiel_repere(self):
        from bs4 import BeautifulSoup
        url = clicktt.logo_heberge(BeautifulSoup(self.fiche(), "html.parser"))
        self.assertTrue(url.startswith("https://dttb.click-tt.de/"))
        self.assertIn("wodata=", url)


    def test_fiche_suisse(self):
        """Le même extracteur sert pour la Suisse : seuls l'hôte, le code fédération
        et la longueur du code postal (4 chiffres) changent."""
        html = self.fiche().replace(
            "Tischtennis Baden-Württemberg e.V.", "Swiss Table Tennis").replace(
            "TGV Eintracht Abstatt", "CTT Bernex").replace(
            "Sportplatzstraße 19, 74232 Abstatt, Deutschland", "Route de Soral 1, 1233 Bernex, Suisse").replace(
            "Goldschmiedstr. 14, 74232 Abstatt", "Route de Soral 1, 1233 Bernex").replace(
            "http://www.tgv-abstatt-tt.de/", "http://www.cttbernex.ch").replace(
            "VNr.: 2053001", "VNr.: 10001")
        club = clicktt.club_depuis_fiche("32984", html, federation=clicktt.SUISSE)
        self.assertEqual(club.pays, "CH")
        self.assertEqual(club.numero, "CH32984")
        self.assertEqual(club.nom, "CTT Bernex")
        self.assertEqual(club.site_web, "http://www.cttbernex.ch")
        self.assertEqual((club.code_postal, club.ville), ("1233", "Bernex"))
        self.assertEqual((club.dep, club.dep_nom), ("CH12", "NPA 12"))
        self.assertIn("STT", club.source_donnees)
        # 10 001 : premier club de l'association genevoise.
        self.assertEqual(club.ligue_code, "CH-GENEVE")
        self.assertEqual(club.ligue_nom, "Association Genevoise de Tennis de Table")

    def test_les_associations_suisses_ne_sont_pas_des_clubs(self):
        """click-TT liste aussi les associations et des comptes de service : le numéro
        d'affiliation (multiple exact de 10 000, ou inférieur) permet de les écarter."""
        self.assertIsNone(clicktt.association_suisse(999))     # TTC Clubdesk
        self.assertIsNone(clicktt.association_suisse(1000))    # AGTT elle-même
        self.assertIsNone(clicktt.association_suisse(10_000))  # Para T-Card
        self.assertEqual(clicktt.association_suisse(40_001)[0], "CH-VAUD-VALAIS-FRIBOURG")
        self.assertEqual(clicktt.association_suisse(70_006)[0], "CH-OST")
        html = self.fiche().replace("Tischtennis Baden-Württemberg e.V.", "Swiss Table Tennis")
        html = html.replace("VNr.: 2053001", "VNr.: 1000")
        self.assertIsNone(clicktt.club_depuis_fiche("1", html, federation=clicktt.SUISSE))

    def test_le_site_de_la_federation_suisse_est_ecarte(self):
        html = self.fiche().replace("http://www.tgv-abstatt-tt.de/",
                                    "https://www.swisstabletennis.ch/fr/")
        club = clicktt.club_depuis_fiche("32984", html, federation=clicktt.SUISSE)
        self.assertEqual(club.site_web, "")

    def test_logo_heberge_suisse(self):
        from bs4 import BeautifulSoup
        url = clicktt.logo_heberge(BeautifulSoup(self.fiche(), "html.parser"), clicktt.SUISSE)
        self.assertTrue(url.startswith("https://www.click-tt.ch/"))

    def test_liens_de_service_ecartes(self):
        """mytischtennis, Google Maps et click-TT ne sont pas le site du club."""
        sans_site = self.fiche().replace(
            '<a href="http://www.tgv-abstatt-tt.de/" target="_blank">http://www.tgv-abstatt-tt.de/</a>', "")
        club = clicktt.club_depuis_fiche("3983", sans_site)
        self.assertEqual(club.site_web, "")
        self.assertEqual(club.logo_statut, catalogue.SITE_ABSENT)

    def test_codes_de_ligue_distincts(self):
        noms = ["Tischtennis Baden-Württemberg e.V.", "Badischer Tischtennis-Verband e.V.",
                "Bayerischer Tischtennis-Verband e.V.", "Tischtennisverband Sachsen-Anhalt e.V.",
                "Tischtennis-Verband Sachsen e.V.", "Pfälzischer TTV"]
        codes = [clicktt.code_ligue(n) for n in noms]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertTrue(all(c.startswith("DE-") for c in codes))

    def test_fusion_par_pays(self):
        """Collecter l'Allemagne ne doit jamais toucher aux clubs français."""
        france = catalogue.Club(pays="FR", numero="07750001", nom="Paris TT", dep="75")
        ancien = catalogue.Club(pays="DE", numero="DE1", nom="TTC Alt", dep="D10",
                                site_web="https://ttc.de", logo_fichier="logos/D10/x.webp",
                                logo_statut=catalogue.LOGO_RECUPERE)
        nouveau = catalogue.Club(pays="DE", numero="DE2", nom="TTC Neu", dep="D20")
        fusion = catalogue.fusionner_pays([france, ancien], [nouveau], "DE", remplacer=False)
        self.assertEqual({c.numero for c in fusion}, {"07750001", "DE1", "DE2"})
        complet = catalogue.fusionner_pays([france, ancien], [nouveau], "DE", remplacer=True)
        self.assertEqual({c.numero for c in complet}, {"07750001", "DE2"})

    def test_statistiques_par_pays(self):
        clubs = [catalogue.Club(pays="FR", numero="1", nom="A", dep="75", ville="Paris")]
        clubs[0].completer_geographie()
        clubs.append(clicktt.club_depuis_fiche("3983", self.fiche()))
        stats = site.statistiques(clubs)
        pays = {p["code"]: p for p in stats["pays"]}
        self.assertEqual(set(pays), {"FR", "DE"})
        self.assertEqual(pays["DE"]["clubs"], 1)
        self.assertEqual(pays["DE"]["ligues"][0]["departements"][0]["dep"], "D74")


class TestAngleterre(unittest.TestCase):
    """Flux ouvert de Table Tennis England (OpenActive RPDE)."""

    @staticmethod
    def element(identifiant=4811, nom="Shoebury TTC", site="www.shoeburytt.co.uk"):
        return {
            "state": "updated", "kind": "club", "id": identifiant,
            "data": {
                "id": identifiant, "name": nom, "websiteUrl": site,
                "venue": [
                    {"id": 1, "name": "Salle secondaire", "address": "1 Other Road, Leeds",
                     "postcode": "LS1 1AA", "lat": "53.8", "lng": "-1.5",
                     "primaryVenue": "false"},
                    {"id": 2, "name": "Shoebury Leisure Centre",
                     "address": "33 Leitrim Avenue, Shoebury, Southend-on-Sea, Shoeburyness",
                     "postcode": "SS3 9HD", "lat": "0.0", "lng": "0.0",
                     "primaryVenue": "true"},
                ],
            },
        }

    def test_zone_postale(self):
        self.assertEqual(angleterre.zone_postale("SS3 9HD"),
                         ("SS", "Southend-on-Sea", "Est de l'Angleterre"))
        self.assertEqual(angleterre.zone_postale("m1 4bt")[0], "M")
        self.assertEqual(angleterre.zone_postale("XX9 1AA"), ("XX", "Autre", "Hors régions"))
        self.assertEqual(angleterre.zone_postale(""), ("", "", ""))

    def test_fiche_de_club(self):
        club = angleterre.club_depuis_element(self.element())
        self.assertEqual((club.pays, club.numero), ("EN", "EN4811"))
        self.assertEqual(club.nom, "Shoebury TTC")
        # L'adresse est donnée sans protocole dans le flux : elle doit rester cliquable.
        self.assertEqual(club.site_web, "http://www.shoeburytt.co.uk")
        self.assertEqual((club.dep, club.ligue_nom), ("SS", "Est de l'Angleterre"))
        # C'est la salle principale qui compte, pas la première venue.
        self.assertEqual(club.salle, "Shoebury Leisure Centre")
        self.assertEqual(club.ville, "Shoeburyness")
        # Des coordonnées nulles ne valent pas mieux qu'une absence de coordonnées.
        self.assertEqual((club.latitude, club.longitude), ("", ""))
        self.assertEqual(club.logo_statut, catalogue.LOGO_ABSENT)

    def test_club_sans_site(self):
        club = angleterre.club_depuis_element(self.element(site=None))
        self.assertEqual(club.site_web, "")
        self.assertEqual(club.logo_statut, catalogue.SITE_ABSENT)
        vide = angleterre.club_depuis_element({"id": 5, "data": {"id": 5, "name": ""}})
        self.assertIsNone(vide)

    def test_parcours_des_pages(self):
        """Le flux est paginé et rejoue les fiches modifiées : la dernière vue fait foi,
        et une fiche supprimée disparaît du résultat."""
        pages = [
            {"items": [self.element(1, "Alpha", None), self.element(2, "Beta", None)],
             "next": "?afterId=2"},
            {"items": [self.element(1, "Alpha renommé", None),
                       {"state": "deleted", "id": 2}],
             "next": "?afterId=3"},
            {"items": [], "next": "?afterId=3"},
        ]

        class ClientFactice:
            def __init__(self, code=200):
                self.appels = []
                self.code = code
                self.session = self

            def get(self, url, timeout=None):
                self.appels.append(url)
                page = pages[min(len(self.appels) - 1, len(pages) - 1)]
                code = self.code

                class Reponse:
                    status_code = code
                    text = '{"Code": 503, "Error": "Service Unavailable"}'

                    @staticmethod
                    def json():
                        return page
                return Reponse()

        client = ClientFactice()
        clubs = angleterre.liste_des_clubs(client)
        self.assertEqual([c.nom for c in clubs], ["Alpha renommé"])
        self.assertEqual(len(client.appels), 3)
        self.assertTrue(client.appels[1].endswith("?afterId=2"))

        # Une coupure annoncée par la fédération n'est pas une panne de notre côté :
        # elle doit être signalée telle quelle plutôt que rendre une liste vide.
        with self.assertRaises(angleterre.SourceEnMaintenance):
            angleterre.liste_des_clubs(ClientFactice(code=503))

    def test_statistiques_par_pays(self):
        clubs = [angleterre.club_depuis_element(self.element())]
        pays = {p["code"]: p for p in site.statistiques(clubs)["pays"]}
        self.assertEqual(pays["EN"]["nom"], "Angleterre")
        self.assertEqual(pays["EN"]["ligues"][0]["departements"][0]["dep"], "SS")


class TestBelgique(unittest.TestCase):
    """API TabT (annuaire) et moteur de recherche de l'AFTT (adresses de sites)."""

    FICHE = (
        "<ns1:UniqueIndex>A003</ns1:UniqueIndex><ns1:Name>Salamander</ns1:Name>"
        "<ns1:LongName>KTTC Salamander Mechelen</ns1:LongName>"
        "<ns1:CategoryName>Antwerpen</ns1:CategoryName>"
        "<ns1:VenueEntries><ns1:Id>6</ns1:Id><ns1:Name>De Sportschuur</ns1:Name>"
        "<ns1:Street>Donkerlei, 72</ns1:Street><ns1:Town>2800 Mechelen</ns1:Town>"
        "<ns1:Phone>0476 32 18 70</ns1:Phone></ns1:VenueEntries>"
    )

    def test_fiche_de_club(self):
        club = belgique.club_depuis_fiche(self.FICHE)
        self.assertEqual((club.pays, club.numero), ("BE", "BEA003"))
        self.assertEqual(club.nom, "KTTC Salamander Mechelen")
        self.assertEqual((club.ligue_code, club.ligue_nom), ("BE-ANTWERPEN", "Anvers"))
        self.assertEqual((club.code_postal, club.ville), ("2800", "Mechelen"))
        self.assertEqual((club.dep, club.salle), ("BE28", "De Sportschuur"))
        # Le numéro de téléphone de la salle ne doit jamais entrer dans le catalogue.
        self.assertNotIn("0476", " ".join(str(v) for v in vars(club).values()))

    def test_les_entrees_administratives_sont_ecartees(self):
        """L'API liste aussi les fédérations elles-mêmes sous une catégorie de service."""
        for categorie in ("VTTL", "AFTT", ""):
            fiche = (f"<ns1:UniqueIndex>{categorie or 'FR'}</ns1:UniqueIndex>"
                     f"<ns1:CategoryName>{categorie}</ns1:CategoryName>")
            self.assertIsNone(belgique.club_depuis_fiche(fiche))

    def test_entites_html_decodees(self):
        """L'API renvoie « Li&amp;egrave;ge » : la province doit être reconnue quand même."""
        fiche = ("<ns1:UniqueIndex>L001</ns1:UniqueIndex><ns1:Name>X</ns1:Name>"
                 "<ns1:CategoryName>Li&amp;egrave;ge</ns1:CategoryName>")
        club = belgique.club_depuis_fiche(fiche)
        self.assertEqual(club.ligue_code, "BE-LIEGE")

    def test_site_du_club(self):
        """Le moteur affiche en permanence des liens de décor : seuls comptent ceux
        qui apparaissent en plus quand la recherche a trouvé le club."""
        decor = ('<a href="https://vttl.be/">VTTL</a>'
                 '<a href="https://www.ittf.com/">ITTF</a>')
        trouve = decor + ('<p>BBW205 - TT ZENITH BRUSSELS</p>'
                          '<a href="https://www.ttzenithbrussels.be">site</a>')

        class ClientFactice:
            def __init__(self, reponse):
                self.reponse = reponse
                self.session = self

            def post(self, url, data=None, timeout=0):
                corps = self.reponse

                class Reponse:
                    status_code = 200
                    text = corps
                return Reponse()

        meubles = belgique._liens_externes(decor)
        self.assertEqual(meubles, set())  # vttl.be et ittf.com sont du décor connu
        client = ClientFactice(trouve)
        self.assertEqual(belgique.site_du_club("BBW205", client, meubles),
                         "https://www.ttzenithbrussels.be")
        # Un club que le moteur ne connaît pas : son index n'apparaît pas dans la page.
        client = ClientFactice(decor)
        self.assertEqual(belgique.site_du_club("A003", client, meubles), "")

    def test_statistiques_par_pays(self):
        clubs = [belgique.club_depuis_fiche(self.FICHE)]
        pays = {p["code"]: p for p in site.statistiques(clubs)["pays"]}
        self.assertEqual(pays["BE"]["nom"], "Belgique")
        self.assertEqual(pays["BE"]["ligues"][0]["nom"], "Anvers")


if __name__ == "__main__":
    unittest.main(verbosity=2)
