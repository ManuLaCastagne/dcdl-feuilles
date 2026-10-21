import re
import shutil
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException, TimeoutException

from .parser import parse_manual


BASE = "https://clubdcdl.over-blog.com/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154 Safari/537.36"
    )
}


# ============================================================
# NAVIGATEUR SELENIUM
# ============================================================

def _build_driver():
    """
    Construit un navigateur Chrome/Chromium compatible
    avec le Mac local et Streamlit Cloud.
    """
    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    chromium = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
    )

    if chromium:
        options.binary_location = chromium

    driver_path = shutil.which("chromedriver")

    if driver_path:
        return webdriver.Chrome(
            service=Service(driver_path),
            options=options,
        )

    # En local, Selenium Manager trouvera Chrome
    # et téléchargera/utilisera le driver adapté.
    return webdriver.Chrome(options=options)


def _get_html_with_selenium(url: str) -> str:
    """
    Récupère une page HTML avec un vrai navigateur.
    Utilisé en fallback si requests n'arrive pas à
    joindre Overblog.
    """
    driver = _build_driver()

    try:
        driver.set_page_load_timeout(30)
        driver.get(url)
        return driver.page_source

    finally:
        driver.quit()


# ============================================================
# RÉCUPÉRATION HTTP
# ============================================================

def _get_html(url: str, timeout=10) -> str:
    """
    Essaie d'abord requests, beaucoup plus rapide.

    Si la connexion à Overblog échoue, utilise Chromium
    comme solution de secours.
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
        )

        response.raise_for_status()

        return response.text

    except requests.exceptions.RequestException:
        return _get_html_with_selenium(url)


def _page_exists(url: str) -> bool:
    """
    Vérifie qu'une URL correspond réellement à un article
    et non à une page 404 Overblog.
    """
    try:
        html = _get_html(url, timeout=5)

    except Exception:
        return False

    text = html.lower()

    if "erreur 404" in text:
        return False

    if "page introuvable" in text:
        return False

    if "404 not found" in text:
        return False

    return True


# ============================================================
# RECHERCHE AUTOMATIQUE DU TOURNOI
# ============================================================

def find_tournament_url(city: str, year: str) -> str:
    """
    Recherche l'article du tournoi dans les archives Overblog.

    Exemple :
        le-touquet + 2026

    teste :
        /2026/01/le-touquet-2026.html
        ...
        /2026/12/le-touquet-2026.html
        /2027/01/le-touquet-2026.html
        ...
    """
    slug = city.strip().lower()

    tournament_slug = f"{slug}-{year}"

    for page_year in (
        int(year),
        int(year) + 1,
    ):

        for month in range(1, 13):

            url = urljoin(
                BASE,
                (
                    f"{page_year}/"
                    f"{month:02d}/"
                    f"{tournament_slug}.html"
                ),
            )

            if _page_exists(url):
                return url

    raise ValueError(
        "Tournoi introuvable. "
        "Renseigne l’URL de l’article pour éviter "
        "la recherche automatique."
    )


# ============================================================
# TÉLÉCHARGEMENT DES FICHIERS TXT
# ============================================================

def _download_txt(url: str) -> str:
    """
    Télécharge un fichier texte lié depuis l'article.
    """
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "ISO-8859-1"
    )

    return response.text


# ============================================================
# RÉCUPÉRATION D'UN TOURNOI
# ============================================================

def fetch_tournament(
    city: str,
    year: str,
    url: str = "",
):
    """
    Récupère tous les fichiers .txt présents dans
    l'article du tournoi puis les transforme en tirages.
    """

    # --------------------------------------------------------
    # URL
    # --------------------------------------------------------

    page = (
        url.strip()
        or find_tournament_url(city, year)
    )

    if not page.startswith("http"):
        page = urljoin(BASE, page)

    # --------------------------------------------------------
    # ARTICLE OVERBLOG
    # --------------------------------------------------------

    try:
        html = _get_html(
            page,
            timeout=10,
        )

    except Exception as exc:
        raise RuntimeError(
            "Impossible d'accéder à l'article Club DCDL "
            "avec HTTP ou Chromium."
        ) from exc

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # --------------------------------------------------------
    # LIENS TXT
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
            re.I,
        ):
            links.append(href)

    # Suppression des doublons
    # en conservant l'ordre.
    links = list(
        dict.fromkeys(links)
    )

    if not links:
        raise ValueError(
            "Aucun fichier .txt trouvé "
            "dans l’article du tournoi."
        )

    # --------------------------------------------------------
    # TÉLÉCHARGEMENT DES TIRAGES
    # --------------------------------------------------------

    chunks = []

    for link in links:

        try:
            text = _download_txt(link)

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                "L'article du tournoi a été trouvé, "
                "mais un fichier de tirages .txt "
                "n'a pas pu être téléchargé : "
                f"{link}"
            ) from exc

        chunks.append(text)

    # --------------------------------------------------------
    # PARSING
    # --------------------------------------------------------

    draws = parse_manual(
        "\n".join(chunks)
    )

    return draws, page