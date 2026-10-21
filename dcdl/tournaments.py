import re
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .parser import parse_manual


BASE = "https://clubdcdl.over-blog.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    )
}


# ============================================================
# OUTILS
# ============================================================

def _slugify(text: str) -> str:
    """
    Transforme un nom de ville en slug Overblog.

    Exemples :
        Le Touquet -> le-touquet
        La Roche-sur-Yon -> la-roche-sur-yon
        Saint-Étienne -> saint-etienne
    """
    text = text.strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    text = re.sub(r"[^a-z0-9]+", "-", text)

    return text.strip("-")


def _session():
    """
    Session HTTP commune.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    return session


# ============================================================
# CONSTRUCTION DIRECTE DE L'URL
# ============================================================

def build_tournament_url(
    city: str,
    year: str,
    month: int,
) -> str:
    """
    Construit directement l'URL probable de l'article.

    Exemple :
        city  = "Vannes"
        year  = "2026"
        month = 3

    ->
        https://clubdcdl.over-blog.com/2026/03/vannes-2026.html
    """

    slug = _slugify(city)

    return urljoin(
        BASE,
        f"{year}/{int(month):02d}/{slug}-{year}.html",
    )


# ============================================================
# RÉCUPÉRATION D'UNE PAGE
# ============================================================

def _get_page(url: str) -> requests.Response:
    """
    Télécharge une page avec un timeout raisonnable.
    Pas de Selenium, pas de boucle.
    """

    session = _session()

    try:
        response = session.get(
            url,
            timeout=(8, 20),
        )

        response.raise_for_status()

        return response

    except requests.exceptions.ConnectTimeout as exc:
        raise RuntimeError(
            "Club DCDL ne répond pas depuis le serveur. "
            "Réessaie dans quelques instants."
        ) from exc

    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "Club DCDL met trop de temps à répondre."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"L'article Club DCDL est introuvable : {url}"
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Impossible d'accéder à Club DCDL : {exc}"
        ) from exc


# ============================================================
# TÉLÉCHARGEMENT TXT
# ============================================================

def _download_txt(url: str) -> str:
    """
    Télécharge un fichier de tirages .txt.
    """

    session = _session()

    try:
        response = session.get(
            url,
            timeout=(8, 20),
        )

        response.raise_for_status()

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "Impossible de télécharger le fichier de tirages : "
            f"{url}"
        ) from exc

    response.encoding = (
        response.apparent_encoding
        or "ISO-8859-1"
    )

    return response.text


# ============================================================
# TOURNOI
# ============================================================

def fetch_tournament(
    city: str,
    year: str,
    url: str = "",
    month: int | None = None,
):
    """
    Récupère les tirages d'un tournoi.

    Deux possibilités :

    1. URL fournie :
       -> on l'utilise directement.

    2. Pas d'URL :
       -> city + year + month permettent de construire
          directement l'URL Overblog.

    Il n'y a plus aucune recherche mois par mois.
    """

    # --------------------------------------------------------
    # DÉTERMINATION DE L'URL
    # --------------------------------------------------------

    if url.strip():

        page = url.strip()

        if not page.startswith("http"):
            page = urljoin(BASE, page)

    else:

        if month is None:
            raise ValueError(
                "Indique le mois du tournoi ou colle directement "
                "l'URL de l'article Club DCDL."
            )

        page = build_tournament_url(
            city,
            year,
            month,
        )

    # --------------------------------------------------------
    # ARTICLE
    # --------------------------------------------------------

    response = _get_page(page)

    html = response.text

    # Certaines pages Overblog peuvent renvoyer une page
    # d'erreur avec un statut HTTP 200.
    lower_html = html.lower()

    if (
        "erreur 404" in lower_html
        or "page introuvable" in lower_html
    ):
        raise ValueError(
            "L'article n'existe pas à cette adresse : "
            f"{page}\n\n"
            "Tu peux corriger le mois ou coller directement "
            "l'URL de l'article."
        )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # --------------------------------------------------------
    # RECHERCHE DES TXT
    # --------------------------------------------------------

    links = []

    for a in soup.find_all(
        "a",
        href=True,
    ):

        href = urljoin(
            page,
            a["href"],
        )

        if re.search(
            r"\.txt(?:\?|$)",
            href,
            re.IGNORECASE,
        ):
            links.append(href)

    # Suppression des doublons en conservant l'ordre.
    links = list(
        dict.fromkeys(links)
    )

    if not links:
        raise ValueError(
            "L'article a bien été trouvé mais aucun fichier "
            ".txt de tirages n'y est présent."
        )

    # --------------------------------------------------------
    # TÉLÉCHARGEMENT
    # --------------------------------------------------------

    chunks = []

    for link in links:

        text = _download_txt(link)

        chunks.append(text)

    # --------------------------------------------------------
    # PARSING
    # --------------------------------------------------------

    draws = parse_manual(
        "\n".join(chunks)
    )

    if not draws:
        raise ValueError(
            "Les fichiers .txt ont été téléchargés mais aucun "
            "tirage n'a pu être reconnu."
        )

    return draws, page