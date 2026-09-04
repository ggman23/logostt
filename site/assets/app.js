/* Galerie des logos des clubs de tennis de table.
   Tout se passe côté navigateur : les données viennent de data/clubs.json. */

const ETAT = {
  clubs: [],
  stats: null,
  pays: "",
  ligue: "",
  dep: "",
  statut: "tous",
  couleur: "tous",
  recherche: "",
  tri: "departement",
  favoris: new Set(),
  visibles: [],
  affiches: 0,
};

const LOT = 120;                       // nombre de cartes ajoutées à chaque défilement
const CLE_FAVORIS = "logostt.favoris";
const COULEURS = [
  ["tous", ""],
  ["rouge", "#e03131"],
  ["orange", "#f08c00"],
  ["jaune", "#f2d024"],
  ["vert", "#2f9e44"],
  ["cyan", "#0ca678"],
  ["bleu", "#1971c2"],
  ["violet", "#6741d9"],
  ["rose", "#d6336c"],
  ["neutre", "#868e96"],
];

const $ = (selecteur) => document.querySelector(selecteur);
const sansAccent = (texte) =>
  (texte || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

/* ------------------------------------------------------------------ chargement */

async function demarrer() {
  chargerFavoris();
  try {
    const [clubs, stats] = await Promise.all([
      fetch("data/clubs.json").then((r) => r.json()),
      fetch("data/stats.json").then((r) => r.json()),
    ]);
    ETAT.clubs = clubs.clubs || [];
    ETAT.stats = stats;
    ETAT.clubs.forEach((club) => {
      club.pays = club.pays || "FR";
      club._recherche = sansAccent(`${club.nom} ${club.ville} ${club.dep} ${club.depNom} ${club.ligueNom}`);
    });
    $("#maj").textContent = `Catalogue mis à jour le ${formaterDate(clubs.maj)}.`;
  } catch (erreur) {
    $("#resume").textContent =
      "Le catalogue n'a pas encore été généré : lancez scripts/collecte_clubs.py puis scripts/construire_site.py.";
    console.error(erreur);
    return;
  }
  if (!ETAT.clubs.length) {
    catalogueVide();
    return;
  }
  lireAdresse();
  construireFiltres();
  resume();
  brancherEvenements();
  rafraichir();
}

function catalogueVide() {
  $("#resume").innerHTML =
    "Le catalogue est encore vide. Lancez la collecte depuis l'onglet " +
    "<strong>Actions</strong> du dépôt GitHub (« Collecte des clubs et des logos »), " +
    "ou en local : <code>python3 scripts/collecte_clubs.py --dep tous</code> puis " +
    "<code>python3 scripts/collecte_logos.py --dep tous</code>.";
  $("#barre").hidden = true;
  $("#vide").hidden = false;
  $("#vide").textContent = "Aucun club au catalogue pour l'instant.";
}

function formaterDate(iso) {
  if (!iso) return "—";
  const [a, m, j] = iso.split("-");
  return `${j}/${m}/${a}`;
}

function resume() {
  const s = ETAT.stats;
  if (!s) return;
  const detail = (s.pays || [])
    .map((p) => `${p.logos.toLocaleString("fr-FR")} en ${p.nom}`)
    .join(", ");
  $("#resume").innerHTML =
    `<strong>${s.logos.toLocaleString("fr-FR")} logos</strong> récupérés sur ` +
    `<strong>${s.clubs.toLocaleString("fr-FR")} clubs</strong> affiliés` +
    (detail ? ` (${detail})` : "") + " — " +
    `${s.sites.toLocaleString("fr-FR")} clubs ont un site internet référencé.`;
}

function paysDisponibles() {
  return (ETAT.stats.pays || []).filter((p) => p.clubs > 0);
}

function liguesAffichees() {
  const pays = paysDisponibles();
  const retenus = ETAT.pays ? pays.filter((p) => p.code === ETAT.pays) : pays;
  return retenus.flatMap((p) => p.ligues);
}

/* ------------------------------------------------------------------ filtres */

function construireFiltres() {
  const pays = paysDisponibles();
  const barrePays = $("#pays");
  barrePays.innerHTML = "";
  if (pays.length > 1) {
    barrePays.append(puce("Tous les pays", ETAT.stats.clubs, ETAT.pays === "", () => {
      ETAT.pays = ""; ETAT.ligue = ""; ETAT.dep = ""; construireFiltres(); rafraichir();
    }));
    pays.forEach((p) => {
      barrePays.append(puce(p.nom, p.clubs, ETAT.pays === p.code, () => {
        ETAT.pays = ETAT.pays === p.code ? "" : p.code;
        ETAT.ligue = ""; ETAT.dep = "";
        construireFiltres();
        rafraichir();
      }));
    });
  }

  const disponibles = liguesAffichees().filter((ligue) => ligue.clubs > 0);
  const ligues = $("#ligues");
  ligues.innerHTML = "";
  const total = disponibles.reduce((somme, l) => somme + l.clubs, 0);
  ligues.append(puce("Toutes les ligues", total, ETAT.ligue === "", () => {
    ETAT.ligue = ""; ETAT.dep = ""; construireFiltres(); rafraichir();
  }));
  disponibles.forEach((ligue) => {
    ligues.append(puce(ligue.nom, ligue.clubs, ETAT.ligue === ligue.code, () => {
      ETAT.ligue = ETAT.ligue === ligue.code ? "" : ligue.code;
      ETAT.dep = "";
      construireFiltres();
      rafraichir();
    }));
  });

  const deps = $("#departements");
  deps.innerHTML = "";
  const ligue = disponibles.find((l) => l.code === ETAT.ligue);
  if (ligue) {
    ligue.departements
      .filter((d) => d.clubs > 0)
      .forEach((departement) => {
        const bouton = puce(
          `${departement.dep} · ${departement.nom}`,
          departement.clubs,
          ETAT.dep === departement.dep,
          () => {
            ETAT.dep = ETAT.dep === departement.dep ? "" : departement.dep;
            construireFiltres();
            rafraichir();
          }
        );
        bouton.classList.add("secondaire");
        deps.append(bouton);
      });
  }

  const couleurs = $("#filtre-couleur");
  if (!couleurs.children.length) {
    COULEURS.forEach(([nom, teinte]) => {
      const bouton = document.createElement("button");
      bouton.className = "pastille" + (ETAT.couleur === nom ? " actif" : "");
      bouton.dataset.couleur = nom;
      bouton.title = nom === "tous" ? "Toutes les couleurs" : `Logos à dominante ${nom}`;
      if (teinte) bouton.style.background = teinte;
      bouton.addEventListener("click", () => {
        ETAT.couleur = ETAT.couleur === nom ? "tous" : nom;
        couleurs.querySelectorAll(".pastille").forEach((p) =>
          p.classList.toggle("actif", p.dataset.couleur === ETAT.couleur));
        rafraichir();
      });
      couleurs.append(bouton);
    });
  }
}

function puce(libelle, compteur, actif, action) {
  const bouton = document.createElement("button");
  bouton.className = "puce" + (actif ? " actif" : "");
  bouton.innerHTML = `${libelle}<span class="compteur">${compteur}</span>`;
  bouton.addEventListener("click", action);
  return bouton;
}

function brancherEvenements() {
  let minuteur;
  $("#recherche").addEventListener("input", (evenement) => {
    clearTimeout(minuteur);
    minuteur = setTimeout(() => {
      ETAT.recherche = sansAccent(evenement.target.value.trim());
      rafraichir();
    }, 160);
  });
  $("#tri").addEventListener("change", (evenement) => {
    ETAT.tri = evenement.target.value;
    rafraichir();
  });
  $("#filtre-statut").addEventListener("click", (evenement) => {
    const bouton = evenement.target.closest("button");
    if (!bouton) return;
    ETAT.statut = bouton.dataset.statut;
    $("#filtre-statut").querySelectorAll("button").forEach((b) =>
      b.classList.toggle("actif", b === bouton));
    rafraichir();
  });
  $("#fermer").addEventListener("click", () => $("#fiche").close());
  $("#precedent").addEventListener("click", () => deplacerFiche(-1));
  $("#suivant").addEventListener("click", () => deplacerFiche(1));
  document.addEventListener("keydown", (evenement) => {
    if (!$("#fiche").open) return;
    if (evenement.key === "ArrowLeft") deplacerFiche(-1);
    if (evenement.key === "ArrowRight") deplacerFiche(1);
  });
  new IntersectionObserver((entrees) => {
    if (entrees.some((e) => e.isIntersecting)) afficherLot();
  }, { rootMargin: "600px" }).observe($("#sentinelle"));
  window.addEventListener("hashchange", () => {
    lireAdresse();
    construireFiltres();
    rafraichir(false);
  });
}

/* ------------------------------------------------------------------ sélection */

function selectionner() {
  const { ligue, dep, statut, couleur, recherche } = ETAT;
  let liste = ETAT.clubs.filter((club) => {
    if (ETAT.pays && club.pays !== ETAT.pays) return false;
    if (ligue && club.ligue !== ligue) return false;
    if (dep && club.dep !== dep) return false;
    if (statut === "logo" && !club.logo) return false;
    if (statut === "sans" && club.logo) return false;
    if (statut === "officiel" && club.origine !== "officiel") return false;
    if (statut === "favoris" && !ETAT.favoris.has(club.id)) return false;
    if (couleur !== "tous" && !(club.familles || []).includes(couleur)) return false;
    if (recherche && !club._recherche.includes(recherche)) return false;
    return true;
  });
  const parNom = (a, b) => a.nom.localeCompare(b.nom, "fr");
  if (ETAT.tri === "nom") liste = liste.sort(parNom);
  else if (ETAT.tri === "ville")
    liste = liste.sort((a, b) => a.ville.localeCompare(b.ville, "fr") || parNom(a, b));
  else
    liste = liste.sort((a, b) => a.dep.localeCompare(b.dep, "fr") || a.ville.localeCompare(b.ville, "fr") || parNom(a, b));
  return liste;
}

function rafraichir(majAdresse = true) {
  ETAT.visibles = selectionner();
  ETAT.affiches = 0;
  $("#grille").innerHTML = "";
  const avecLogo = ETAT.visibles.filter((c) => c.logo).length;
  $("#compte").textContent = ETAT.visibles.length
    ? `${ETAT.visibles.length.toLocaleString("fr-FR")} club${ETAT.visibles.length > 1 ? "s" : ""} · ${avecLogo} logo${avecLogo > 1 ? "s" : ""} affiché${avecLogo > 1 ? "s" : ""}`
    : "";
  $("#vide").hidden = ETAT.visibles.length > 0;
  afficherLot();
  if (majAdresse) ecrireAdresse();
}

function afficherLot() {
  const grille = $("#grille");
  const fin = Math.min(ETAT.affiches + LOT, ETAT.visibles.length);
  const fragment = document.createDocumentFragment();
  for (let index = ETAT.affiches; index < fin; index += 1) {
    fragment.append(carte(ETAT.visibles[index], index));
  }
  grille.append(fragment);
  ETAT.affiches = fin;
}

/* ------------------------------------------------------------------ rendu */

function carte(club, index) {
  const element = document.createElement("article");
  element.className = "carte";

  const vignette = document.createElement("button");
  vignette.className = "vignette" + (club.fond === "sombre" ? " sombre" : "");
  vignette.type = "button";
  vignette.setAttribute("aria-label", `Agrandir le logo de ${club.nom}`);
  vignette.append(visuel(club));
  vignette.addEventListener("click", () => ouvrirFiche(index));

  const etoile = document.createElement("button");
  etoile.className = "etoile" + (ETAT.favoris.has(club.id) ? " actif" : "");
  etoile.type = "button";
  etoile.title = "Mettre ce logo en favori";
  etoile.textContent = ETAT.favoris.has(club.id) ? "★" : "☆";
  etoile.addEventListener("click", (evenement) => {
    evenement.stopPropagation();
    basculerFavori(club.id);
    etoile.classList.toggle("actif", ETAT.favoris.has(club.id));
    etoile.textContent = ETAT.favoris.has(club.id) ? "★" : "☆";
  });
  vignette.append(etoile);

  const infos = document.createElement("div");
  infos.className = "infos";
  const situation = [club.dep, club.depNom].filter(Boolean).join(" · ");
  const lieu = [club.ville, club.cp].filter(Boolean).join(" ");
  infos.innerHTML = `
    ${situation ? `<p class="lieu-court">${echapper(situation)}</p>` : ""}
    <p class="nom">${echapper(club.nom)}</p>
    ${lieu ? `<p class="ville">${echapper(lieu)}</p>` : ""}
    <span class="etiquette ${club.origine === "officiel" ? "officiel" : club.statut}">${libelleStatut(club.statut, club.origine)}</span>
    <p class="liens-carte">${
      club.site
        ? `<a href="${echapper(club.site)}" target="_blank" rel="noopener">site du club ↗</a>`
        : '<span class="absent">pas de site connu</span>'
    }</p>`;

  element.append(vignette, infos);
  return element;
}

function visuel(club) {
  if (club.logo) {
    const image = document.createElement("img");
    image.src = club.logo;
    image.alt = `Logo du club ${club.nom}`;
    image.loading = "lazy";
    image.decoding = "async";
    image.addEventListener("error", () => {
      image.replaceWith(monogramme(club));
    });
    return image;
  }
  return monogramme(club);
}

function monogramme(club) {
  const bloc = document.createElement("span");
  bloc.className = "monogramme";
  const initiales = club.nom
    .split(/[^A-Za-zÀ-ÿ0-9]+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((mot) => mot[0].toUpperCase())
    .join("");
  bloc.textContent = initiales || "?";
  let empreinte = 0;
  for (const caractere of club.id + club.nom) empreinte = (empreinte * 31 + caractere.charCodeAt(0)) % 360;
  bloc.style.background = `linear-gradient(140deg, hsl(${empreinte} 52% 46%), hsl(${(empreinte + 40) % 360} 55% 34%))`;
  return bloc;
}

function libelleStatut(statut, origine) {
  if (origine === "officiel") return "logo officiel";
  return {
    logo: "logo du site",
    favicon: "icône du site",
    aucun: "logo introuvable",
    "sans-site": "pas de site",
  }[statut] || statut;
}

function echapper(texte) {
  return String(texte ?? "").replace(/[&<>"']/g, (caractere) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[caractere]);
}

/* ------------------------------------------------------------------ fiche */

let ficheIndex = -1;

function ouvrirFiche(index) {
  ficheIndex = index;
  const club = ETAT.visibles[index];
  if (!club) return;
  const visuelFiche = $("#fiche-visuel");
  visuelFiche.className = "fiche-visuel" + (club.fond === "sombre" ? " sombre" : "");
  visuelFiche.innerHTML = "";
  visuelFiche.append(visuel(club));
  $("#fiche-nom").textContent = club.nom;
  $("#fiche-lieu").textContent = [
    [club.ville, club.cp && `(${club.cp})`].filter(Boolean).join(" "),
    [club.dep, club.depNom].filter(Boolean).join(" "),
    club.ligueNom,
  ].filter(Boolean).join(" · ");
  const palette = $("#fiche-couleurs");
  palette.innerHTML = (club.couleurs || [])
    .map((couleur) => `<span class="echantillon" style="background:${echapper(couleur)}">${echapper(couleur)}</span><code>${echapper(couleur)}</code>`)
    .join("");
  const site = $("#fiche-site");
  site.href = club.site || "#";
  site.hidden = !club.site;
  const source = $("#fiche-source");
  source.href = club.logoSource || "#";
  source.hidden = !club.logoSource;
  const favori = $("#fiche-favori");
  const majFavori = () => {
    const actif = ETAT.favoris.has(club.id);
    favori.className = "favori-bouton" + (actif ? " actif" : "");
    favori.textContent = actif ? "★ Dans vos favoris" : "☆ Mettre en favori";
  };
  favori.onclick = () => { basculerFavori(club.id); majFavori(); rafraichirEtoiles(club.id); };
  majFavori();
  if (!$("#fiche").open) $("#fiche").showModal();
}

function deplacerFiche(pas) {
  const suivant = ficheIndex + pas;
  if (suivant >= 0 && suivant < ETAT.visibles.length) ouvrirFiche(suivant);
}

/* ------------------------------------------------------------------ favoris */

function chargerFavoris() {
  try {
    ETAT.favoris = new Set(JSON.parse(localStorage.getItem(CLE_FAVORIS) || "[]"));
  } catch (erreur) {
    ETAT.favoris = new Set();
  }
}

function basculerFavori(id) {
  if (ETAT.favoris.has(id)) ETAT.favoris.delete(id);
  else ETAT.favoris.add(id);
  try {
    localStorage.setItem(CLE_FAVORIS, JSON.stringify([...ETAT.favoris]));
  } catch (erreur) {
    /* navigation privée : les favoris restent en mémoire pour la session */
  }
  if (ETAT.statut === "favoris") rafraichir();
}

function rafraichirEtoiles(id) {
  const index = ETAT.visibles.findIndex((club) => club.id === id);
  const carteVisible = $("#grille").children[index];
  if (!carteVisible) return;
  const etoile = carteVisible.querySelector(".etoile");
  const actif = ETAT.favoris.has(id);
  etoile.classList.toggle("actif", actif);
  etoile.textContent = actif ? "★" : "☆";
}

/* ------------------------------------------------------------------ adresse */

function lireAdresse() {
  const parametres = new URLSearchParams(location.hash.slice(1));
  ETAT.pays = parametres.get("pays") || "";
  ETAT.ligue = parametres.get("ligue") || "";
  ETAT.dep = parametres.get("dep") || "";
  ETAT.statut = parametres.get("statut") || "tous";
  ETAT.couleur = parametres.get("couleur") || "tous";
  ETAT.recherche = sansAccent(parametres.get("q") || "");
  if (ETAT.recherche) $("#recherche").value = parametres.get("q");
  $("#filtre-statut").querySelectorAll("button").forEach((bouton) =>
    bouton.classList.toggle("actif", bouton.dataset.statut === ETAT.statut));
}

function ecrireAdresse() {
  const parametres = new URLSearchParams();
  if (ETAT.pays) parametres.set("pays", ETAT.pays);
  if (ETAT.ligue) parametres.set("ligue", ETAT.ligue);
  if (ETAT.dep) parametres.set("dep", ETAT.dep);
  if (ETAT.statut !== "tous") parametres.set("statut", ETAT.statut);
  if (ETAT.couleur !== "tous") parametres.set("couleur", ETAT.couleur);
  if (ETAT.recherche) parametres.set("q", $("#recherche").value.trim());
  const adresse = parametres.toString();
  history.replaceState(null, "", adresse ? `#${adresse}` : location.pathname);
}

demarrer();
