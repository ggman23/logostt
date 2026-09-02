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

from ttlogos import carte, catalogue, logos, referentiel, site  # noqa: E402


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
