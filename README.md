# Les logos des clubs de tennis de table — France

Galerie des logos des clubs affiliés à la FFTT, **ligue par ligue et département par
département**, avec le lien vers le site internet de chaque club. Le but : parcourir
visuellement ce qui se fait ailleurs pour s'en inspirer, et aller voir les bonnes idées
sur les sites des clubs qui vous plaisent.

Le dépôt contient deux choses :

1. **le site** (`site/`) — une galerie statique, sans serveur ni base de données ;
2. **le pipeline de collecte** (`scripts/`) — qui construit le catalogue des clubs puis
   va chercher le logo sur le site de chacun.

## Ce que fait le site

- filtres **ligue → département**, recherche par club ou par ville ;
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

### 1. Depuis GitHub (le plus simple)

Onglet **Actions → « Collecte des clubs et des logos » → Run workflow**. Choisissez le
périmètre (`tous`, une ligue comme `IDF`, ou un département comme `75`). Le résultat est
commité automatiquement dans `data/clubs.csv`, `site/data/` et `site/logos/`.

Pensez à renseigner au préalable les deux secrets du dépôt (Settings → Secrets and
variables → Actions) :

| Secret | Rôle |
| --- | --- |
| `FFTT_API_ID` | identifiant de l'API SmartPing |
| `FFTT_API_KEY` | clé associée |

Ces identifiants sont délivrés gratuitement par la FFTT sur simple demande
(<https://www.fftt.com/api/>) : ce sont eux qui donnent la liste officielle des clubs
affiliés **avec leur site internet**, département par département. Sans identifiants, le
script tente les anciens points d'entrée ouverts, qui peuvent avoir été fermés ; à défaut,
`--source opendata` récupère une liste de clubs (sans site web) depuis
data.sports.gouv.fr.

### 2. En local

```bash
pip install -r requirements.txt

export FFTT_API_ID=...  FFTT_API_KEY=...

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
scripts/collecte_clubs.py liste des clubs (API FFTT SmartPing ou open data)
scripts/collecte_logos.py visite des sites et extraction des logos
scripts/construire_site.py génère site/data/clubs.json et stats.json
scripts/ttlogos/          les modules (référentiel, catalogue, réseau, logos, site)
site/                     la galerie (HTML/CSS/JS, aucune dépendance externe)
tests/test_pipeline.py    tests hors ligne (python3 tests/test_pipeline.py)
```

## À propos des logos

Chaque logo appartient à son club et n'est repris ici qu'à titre d'illustration, avec le
lien vers le site d'origine. Le collecteur s'annonce dans son `User-Agent`, espace ses
requêtes et se limite à la page d'accueil de chaque site. Si un club demande le retrait de
son logo, ajoutez-le dans `data/corrections.csv` avec `exclure=oui`.
