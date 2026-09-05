# Les logos des clubs de tennis de table

Galerie des logos des clubs de tennis de table européens, **pays par pays, ligue par
ligue et département par département**, avec le lien vers le site internet de chaque
club. Le but : parcourir visuellement ce qui se fait ailleurs pour s'en inspirer, et
aller voir les bonnes idées sur les sites des clubs qui vous plaisent.

| Pays | Clubs | Avec un site | Avec un logo |
| --- | ---: | ---: | ---: |
| 🇩🇪 Allemagne (DTTB) | 7 167 | 3 163 | 3 771 |
| 🇫🇷 France (FFTT) | 3 064 | 1 220 | 880 |
| 🇦🇹 Autriche (ÖTTV) | 525 | 274 | 146 |
| 🇧🇪 Belgique (FRBTT) | 516 | 113 | 81 |
| 🇵🇱 Pologne (PZTS) | 486 | — | — |
| 🇨🇭 Suisse (STT) | 255 | 223 | 136 |

L'Angleterre est prête à être collectée mais sa fédération a suspendu son flux ouvert
(voir plus bas). Trois autres pays ont été cherchés sans succès : la section
« Fédérations sans annuaire public » explique pourquoi.

Le dépôt contient deux choses :

1. **le site** (`site/`) — une galerie statique, sans serveur ni base de données ;
2. **le pipeline de collecte** (`scripts/`) — qui construit le catalogue des clubs puis
   va chercher le logo sur le site de chacun.

## Ce que fait le site

- filtres **pays → ligue → département**, recherche par club ou par ville ;
- filtre **par couleur dominante** du logo (extraite automatiquement) et par état
  (« avec logo », « sans logo ») ;
- **favoris** enregistrés dans le navigateur : mettez une étoile sur les logos qui vous
  plaisent, puis affichez uniquement votre sélection avec le filtre ★ ;
- clic sur un logo : agrandissement, palette de couleurs (codes hexadécimaux réutilisables),
  lien vers le site du club et vers le fichier d'origine du logo ;
- l'adresse de la page reflète les filtres : `#ligue=BRE&dep=35` est partageable.

## Lancer la collecte

> ⚠️ La collecte visite des milliers de sites : elle est faite pour tourner sur GitHub
> Actions ou sur votre machine, pas dans un navigateur.

### D'où viennent les données

**Aucun identifiant n'est nécessaire, dans aucun des pays.** Chaque fédération publie
son annuaire quelque part ; le travail a consisté à trouver où.

Aucune des pages visitées ne laisse de coordonnées personnelles entrer dans le
catalogue : plusieurs fiches affichent le nom, le téléphone et le courriel d'un
correspondant, et des tests du dépôt vérifient qu'ils ne sont jamais enregistrés.

### France — FFTT

La FFTT publie deux pages qui suffisent :

| Page | Ce qu'on y prend |
| --- | --- |
| `carte.fftt.com/organismes` | la liste de tous les clubs affiliés (numéro + nom), en une seule requête |
| `inscriptionenligne.fftt.com/club/<numéro>` | la fiche publique du club : ligue, comité, salle, ville et **le lien vers son site internet** |

Ces fiches affichent aussi les coordonnées d'un correspondant : ces données personnelles
ne sont ni extraites ni enregistrées (un test du dépôt le vérifie).

### Allemagne — DTTB (click-TT)

| Page | Ce qu'on y prend |
| --- | --- |
| `clubSearch` (POST, champ `searchFor`) | tous les clubs dont le nom contient le terme cherché, sans pagination ; l'union de quelques lettres couvre les ~9 000 clubs |
| `clubInfoDisplay?club=<id>` | Landesverband, numéro d'affiliation, salle, ville, site internet **et le logo officiel hébergé par click-TT** |

En Allemagne le logo vient donc directement de la fédération : pas de tri à faire, pas de
faux positif possible. Les clubs sans logo déposé passent par l'extraction depuis leur
site, comme en France. L'adresse de contact d'une personne n'est jamais reprise.

```bash
python3 scripts/collecte_clubs.py --source clicktt                  # Allemagne
python3 scripts/collecte_clubs.py --source clicktt --federation CH  # Suisse
```

### Suisse — Swiss Table Tennis (click-TT)

Swiss Table Tennis tourne sur le même moteur que la fédération allemande : le module
`clicktt.py` sert donc les deux, une classe `Federation` portant ce qui les distingue
(hôte, code de fédération, longueur du code postal).

Une particularité : click-TT n'affiche qu'une seule fédération pour tout le pays.
L'appartenance régionale se lit en fait dans le **numéro d'affiliation**, dont la dizaine
de milliers désigne l'association (10 000 = Genève, 20 000 = Neuchâtel-Jura, 30 000 =
Tessin…). Les entrées dont le numéro est un multiple exact de 10 000, ou inférieur, sont
les associations elles-mêmes : elles sont écartées.

### Belgique — FRBTT (API TabT + moteur de l'AFTT)

| Source | Ce qu'on y prend |
| --- | --- |
| `api.vttl.be/0.7/` (SOAP, `GetClubs`) | tous les clubs du pays, des deux ailes linguistiques : index, nom, province et salle — **mais aucune adresse de site** |
| moteur « trouver un club » de l'`aftt.be` | l'adresse du site, interrogée club par club à partir de l'index |

Les liens qui décorent toutes les pages du moteur sont relevés une fois, sur une
recherche vide, puis soustraits de chaque réponse : ce qui reste est le site du club.

**Limite connue** : ce moteur appartient à l'aile francophone et ne connaît qu'elle. Les
150 clubs flamands (VTTL) figurent donc au catalogue avec leur nom, leur province et leur
salle, mais sans site ni logo. La VTTL ne publie ni plan de site, ni page par club, ni
tableau exploitable, et son site de consultation des résultats est protégé par un
anti-robot.

```bash
python3 scripts/collecte_clubs.py --source belgique
```

### Angleterre — Table Tennis England (données ouvertes)

La fédération publie tout son annuaire au format [OpenActive
RPDE](https://github.com/TableTennis365/opendata), sans clé ni inscription : nom du club,
**adresse de son site**, salle et code postal. Les zones postales britanniques servent de
second niveau de navigation, rattachées aux neuf régions anglaises.

**Au moment d'écrire ces lignes le flux est éteint** : le serveur répond `503 — Sorry,
API is temporarily disabled or under maintenance`. Le module le reconnaît, le dit et
s'arrête sans rien changer au catalogue. Le workflow `angleterre.yml` relance la collecte
chaque jour : elle aboutira d'elle-même le jour où la fédération rallumera son flux.

```bash
python3 scripts/collecte_clubs.py --source angleterre
```

### Autriche — ÖTTV

| Page | Ce qu'on y prend |
| --- | --- |
| `oettv.org/organisation/vereine` | tous les clubs d'un coup : nom, sigle, Landesverband, salle, coordonnées géographiques et, pour la moitié, **l'adresse du site** |

C'est l'annuaire le plus économe du lot : une seule requête pour tout le pays.

Deux pièges y sont désamorcés. La page mêle les clubs et les « Spielgemeinschaften »,
ententes entre deux clubs pour aligner une équipe commune, qui n'ont ni salle ni logo
propre : chaque carte annonce son genre, seuls les clubs sont retenus. Et chaque carte
affiche, à côté de l'adresse de la salle, celle d'un correspondant et un numéro de
registre à neuf chiffres : l'adresse n'est donc cherchée que dans le bloc « Halle ».

```bash
python3 scripts/collecte_clubs.py --source autriche
```

### Pologne — PZTS

| Page | Ce qu'on y prend |
| --- | --- |
| `rozgrywki.pzts.pl/…/club_licenses` | tous les clubs licenciés : numéro, nom et voïvodie — **sans adresse de site** |
| `mzts.pl/kluby-czlonkowskie` | les sites des clubs de Mazovie, seule association régionale à les publier |

La fédération ne collecte pas les adresses de site de ses clubs. Sur les seize
associations régionales, une seule les publie ; les deux sources n'écrivant pas les
noms de la même façon, les clubs sont rapprochés sur leurs mots distinctifs, sigles de
forme juridique retirés.

**Limite connue** : les clubs des quinze autres voïvodies figurent au catalogue avec
leur nom et leur région, mais sans site ni logo.

```bash
python3 scripts/collecte_clubs.py --source pologne
```

### Fédérations sans annuaire public

Trois pays ont été cherchés sérieusement et abandonnés, faute de source :

| Pays | Ce qui bloque |
| --- | --- |
| 🇨🇿 Tchéquie | le système fédéral (STIS) répond `202` à un robot et sa page porte `<meta name="robots" content="none,noindex,nofollow">` : la fédération demande explicitement qu'on ne la parcoure pas. Son registre séparé exige une connexion. |
| 🇳🇱 Pays-Bas | le moteur « zoek een club » est en JavaScript et n'expose aucune donnée ; les sept divisions régionales n'ont que des rubriques d'actualité, pas d'annuaire. |
| 🇪🇸 Espagne | la fédération nationale ne gère pas les clubs — ce sont les dix-sept fédérations autonomes. Elle ne publie que la liste de ces fédérations, et son espace clubs est derrière une connexion. |

### Sources de secours

`--source fftt` (API SmartPing officielle,
qui demande un identifiant et une clé délivrés par la fédération, à renseigner dans
`FFTT_API_ID` / `FFTT_API_KEY`) et `--source opendata` (data.sports.gouv.fr, sans sites web).

### 1. Depuis GitHub (le plus simple)

Onglet **Actions → « Collecte des clubs et des logos » → Run workflow**. Choisissez le
périmètre (`tous`, une ligue comme `IDF`, ou un département comme `75`). Le résultat est
commité automatiquement dans `data/clubs.csv`, `site/data/` et `site/logos/`.

Variante sans passer par l'interface : écrivez le périmètre voulu dans
`.github/lancer-collecte.txt` et poussez le fichier — la collecte démarre. Écrire `DE`
en première ligne lance la collecte allemande.

### 2. En local

```bash
pip install -r requirements.txt

python3 scripts/collecte_clubs.py --dep tous      # liste des clubs + sites internet
python3 scripts/collecte_logos.py --dep tous      # visite des sites, extraction des logos
python3 scripts/construire_site.py                # génère site/data/*.json

python3 -m http.server -d site 8000               # http://localhost:8000
```

`--dep` accepte un département (`75`), une ligue (`IDF`, `BRE`, `PAC`…), `metropole`,
`outre-mer` ou `tous`. Vous pouvez donc avancer ligue par ligue :

```bash
for ligue in IDF BRE PDL NAQ OCC ARA PAC GES HDF NOR CVL BFC COR; do
  python3 scripts/collecte_clubs.py --dep $ligue && python3 scripts/collecte_logos.py --dep $ligue
done
```

### Aperçu sans réseau

```bash
python3 tests/apercu_demo.py apercu && python3 -m http.server -d apercu 8000
```

Génère une galerie de démonstration avec des **clubs fictifs**, pour voir la mise en page
avant d'avoir collecté quoi que ce soit.

## Comment le logo est choisi

Pour chaque club ayant un site, la page d'accueil est analysée et les images sont classées :

1. le logo déclaré en donnée structurée `schema.org` ;
2. les `<img>` dont le nom de fichier, la classe ou le texte alternatif contiennent
   « logo », « blason », « écusson »… surtout dans l'en-tête du site ;
3. l'icône `apple-touch-icon`, puis l'image de partage `og:image` ;
4. en dernier recours la favicone (le club est alors marqué « icône du site »).

Sont écartés d'office : bannières de diaporama, logos de sponsors, boutons de réseaux
sociaux, logos de la FFTT / de la ligue / du comité, images trop petites ou trop
allongées. L'image retenue est rognée de ses marges, ramenée à 512 px maximum, convertie
en WebP (les SVG sont conservés tels quels, débarrassés de leurs scripts), et ses couleurs
dominantes sont extraites pour alimenter le filtre par couleur.

Le résultat de ce tri automatique est bon mais pas parfait : voir ci-dessous pour corriger.

## Corriger à la main

`data/corrections.csv` est relu après chaque collecte et gagne toujours :

```csv
numero,site_web,logo_url,exclure,commentaire
07750123,https://le-vrai-site-du-club.fr,,,site changé
08350045,,,oui,club en sommeil
```

- `site_web` : impose l'adresse du site (le logo sera re-cherché) ;
- `exclure` : retire le club de la galerie ;
- `logo_url` : à renseigner si vous voulez forcer un fichier précis (repassez ensuite
  `collecte_logos.py --forcer`).

Vous pouvez aussi déposer un logo à la main dans `site/logos/<dep>/` et renseigner la
colonne `logo_fichier` de `data/clubs.csv`.

## Publier

- **GitHub Pages** : le workflow `.github/workflows/pages.yml` publie le dossier `site/`
  à chaque poussée sur `main` (activez Pages avec la source « GitHub Actions »).
- **Netlify** : `netlify.toml` est déjà configuré (dossier publié : `site`, pas de build).

## Structure

```
referentiel/ligues.json   les 20 ligues et leurs 103 départements
data/clubs.csv            le catalogue (une ligne par club)
data/corrections.csv      vos corrections manuelles
scripts/collecte_clubs.py liste des clubs (annuaires publics de chaque fédération)
scripts/reconnaissance.py sonde les sources publiques (diagnostic, ne collecte rien)
scripts/collecte_logos.py visite des sites et extraction des logos
scripts/construire_site.py génère site/data/clubs.json et stats.json
scripts/ttlogos/          les modules (référentiel, catalogue, réseau, carte, clicktt, logos, site)
site/                     la galerie (HTML/CSS/JS, aucune dépendance externe)
tests/test_pipeline.py    tests hors ligne (python3 tests/test_pipeline.py)
tests/echantillons/       pages réelles de la FFTT servant de référence aux tests
```

## À propos des logos

Chaque logo appartient à son club et n'est repris ici qu'à titre d'illustration, avec le
lien vers le site d'origine. Le collecteur s'annonce dans son `User-Agent`, espace ses
requêtes et se limite à la page d'accueil de chaque site. Si un club demande le retrait de
son logo, ajoutez-le dans `data/corrections.csv` avec `exclure=oui`.
