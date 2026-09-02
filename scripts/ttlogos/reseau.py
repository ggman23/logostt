"""Accès HTTP : session polie, temporisation par domaine, journalisation."""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

AGENT = (
    "logostt/1.0 (collecte des logos des clubs de tennis de table ; "
    "contact via https://github.com/ggman23/logostt)"
)
DELAI_PAR_DOMAINE = 1.5  # secondes minimum entre deux requêtes vers le même domaine

journal = logging.getLogger("logostt")


class Client:
    """Petit client HTTP : réessais, délai entre requêtes, taille de réponse plafonnée."""

    def __init__(self, delai: float = DELAI_PAR_DOMAINE, timeout: float = 20.0) -> None:
        self.delai = delai
        self.timeout = timeout
        self._dernier_appel: dict[str, float] = defaultdict(float)
        self._verrou = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
        })
        reessais = Retry(
            total=2,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        adaptateur = HTTPAdapter(max_retries=reessais, pool_maxsize=32)
        self.session.mount("https://", adaptateur)
        self.session.mount("http://", adaptateur)

    def _patienter(self, domaine: str) -> None:
        with self._verrou:
            attente = self._dernier_appel[domaine] + self.delai - time.monotonic()
            self._dernier_appel[domaine] = time.monotonic() + max(attente, 0)
        if attente > 0:
            time.sleep(attente)

    def get(self, url: str, *, taille_max: int = 8_000_000, **kwargs) -> requests.Response | None:
        """GET tolérant : renvoie None au lieu de lever en cas d'échec réseau."""
        domaine = url.split("/")[2] if "://" in url else url
        self._patienter(domaine)
        try:
            reponse = self.session.get(
                url, timeout=self.timeout, stream=True, allow_redirects=True, **kwargs
            )
        except requests.RequestException as erreur:
            journal.debug("échec %s : %s", url, erreur)
            return None
        try:
            if reponse.status_code >= 400:
                journal.debug("HTTP %s sur %s", reponse.status_code, url)
                return None
            contenu = b""
            for bloc in reponse.iter_content(64 * 1024):
                contenu += bloc
                if len(contenu) > taille_max:
                    journal.debug("réponse tronquée (>%s octets) : %s", taille_max, url)
                    break
            reponse._content = contenu  # noqa: SLF001 - on force le contenu déjà lu
            return reponse
        except requests.RequestException as erreur:
            journal.debug("lecture interrompue %s : %s", url, erreur)
            return None
        finally:
            reponse.close()

    def texte(self, url: str, **kwargs) -> str:
        reponse = self.get(url, **kwargs)
        return decoder(reponse) if reponse is not None else ""


def decoder(reponse) -> str:
    """Texte d'une réponse, en corrigeant l'encodage deviné par défaut (souvent faux)."""
    if reponse.encoding is None or reponse.encoding.lower() == "iso-8859-1":
        reponse.encoding = reponse.apparent_encoding or "utf-8"
    return reponse.text
