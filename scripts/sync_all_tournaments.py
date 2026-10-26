from pathlib import Path
import argparse
import json
import re
import sys
import time
import unicodedata
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://clubdcdl.over-blog.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

ROOT = Path(__file__).resolve().parents[1]
TOURNAMENTS_DIR = ROOT / "data" / "tournois"
INDEX_FILE = TOURNAMENTS_DIR / "_sync_index.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154 Safari/537.36"
    )
}

session = requests.Session()
session.headers.update(HEADERS)


# ---------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------

def slugify(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get(url: str) -> requests.Response:
    response = session.get(
        url,
        timeout=(10, 30),
    )
    response.raise_for_status()
    return response


# ---------------------------------------------------------
# Index local
# ---------------------------------------------------------

def load_index() -> dict:
    if not INDEX_FILE.exists():
        return {
            "articles": {}
        }

    try:
        return json.loads(
            INDEX_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {
            "articles": {}
        }


def save_index(index: dict):
    TOURNAMENTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    INDEX_FILE.write_text(
        json.dumps(
            index,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------
# Lecture des sitemaps
# ---------------------------------------------------------

def parse_xml_locations(xml_text: str) -> list[str]:
    """
    Extrait les URL contenues dans les balises <loc> d'un sitemap
    sans dépendre de xml.etree / pyexpat.
    """
    return [
        url.strip()
        for url in re.findall(
            r"<loc>\s*(.*?)\s*</loc>",
            xml_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if url.strip()
    ]

def discover_article_sitemaps() -> list[str]:
    """
    Lit sitemap.xml et récupère les sous-sitemaps
    susceptibles de contenir les articles.
    """

    print("Lecture du sitemap principal...")

    response = get(SITEMAP_URL)

    locations = parse_xml_locations(response.text)

    article_sitemaps = []

    for location in locations:
        filename = Path(
            urlparse(location).path
        ).name.lower()

        # sitemap1.xml, sitemap2.xml, sitemap3.xml...
        if re.fullmatch(
            r"sitemap\d+\.xml",
            filename,
        ):
            article_sitemaps.append(location)

    return article_sitemaps


def discover_articles(
    from_year: int | None = None,
    to_year: int | None = None,
) -> list[str]:

    sitemap_urls = discover_article_sitemaps()

    print(
        f"{len(sitemap_urls)} sitemap(s) "
        "d'articles trouvé(s)."
    )

    articles = set()

    article_pattern = re.compile(
        r"/(\d{4})/(\d{2})/[^/]+\.html$",
        re.IGNORECASE,
    )

    for sitemap_url in sitemap_urls:
        print(
            f"Lecture de "
            f"{Path(urlparse(sitemap_url).path).name}..."
        )

        try:
            response = get(sitemap_url)
        except Exception as exc:
            print(
                f"  ! Impossible de lire "
                f"{sitemap_url}: {exc}"
            )
            continue

        locations = parse_xml_locations(
            response.text
        )

        for location in locations:
            parsed = urlparse(location)

            match = article_pattern.search(
                parsed.path
            )

            if not match:
                continue

            year = int(match.group(1))

            if (
                from_year is not None
                and year < from_year
            ):
                continue

            if (
                to_year is not None
                and year > to_year
            ):
                continue

            clean_url = (
                f"{parsed.scheme}://"
                f"{parsed.netloc}"
                f"{parsed.path}"
            )

            articles.add(clean_url)

    return sorted(articles)


# ---------------------------------------------------------
# Analyse des articles
# ---------------------------------------------------------

def find_txt_links(
    article_url: str,
    html: str,
) -> list[str]:

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    links = []

    for element in soup.find_all(
        "a",
        href=True,
    ):
        href = urljoin(
            article_url,
            element["href"],
        )

        if re.search(
            r"\.txt(?:\?|$)",
            href,
            re.IGNORECASE,
        ):
            links.append(href)

    return list(dict.fromkeys(links))


def extract_title(html: str) -> str:
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    h1 = soup.find("h1")

    if h1:
        return h1.get_text(
            " ",
            strip=True,
        )

    if soup.title:
        return soup.title.get_text(
            " ",
            strip=True,
        )

    return "Tournoi"


def extract_year(article_url: str) -> int:
    match = re.search(
        r"/(\d{4})/\d{2}/",
        urlparse(article_url).path,
    )

    if not match:
        raise ValueError(
            f"Année introuvable : {article_url}"
        )

    return int(match.group(1))


def article_slug(article_url: str) -> str:
    stem = Path(
        urlparse(article_url).path
    ).stem

    # lyon-2026 -> lyon
    stem = re.sub(
        r"-20\d{2}$",
        "",
        stem,
    )

    return slugify(stem)


# ---------------------------------------------------------
# Téléchargement
# ---------------------------------------------------------

def download_txt(url: str) -> str:
    response = get(url)

    response.encoding = (
        response.apparent_encoding
        or "ISO-8859-1"
    )

    return response.text


def sync_article(
    article_url: str,
    index: dict,
    force: bool = False,
) -> str:

    articles_index = index.setdefault(
        "articles",
        {},
    )

    previous = articles_index.get(
        article_url
    )

    if previous and not force:
        return "already_checked"

    try:
        response = get(article_url)
    except Exception as exc:
        print(
            f"  ! Article inaccessible : {exc}"
        )

        # On ne le marque PAS comme traité :
        # une future synchro pourra réessayer.
        return "error"

    txt_links = find_txt_links(
        article_url,
        response.text,
    )

    title = extract_title(
        response.text
    )

    year = extract_year(
        article_url
    )

    if not txt_links:
        articles_index[article_url] = {
            "type": "no_txt",
            "title": title,
            "year": year,
        }

        return "no_txt"

    slug = article_slug(
        article_url
    )

    destination_dir = (
        TOURNAMENTS_DIR / str(year)
    )

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        destination_dir
        / f"{slug}.txt"
    )

    print()
    print(f"🏆 {title}")
    print(f"   {article_url}")
    print(
        f"   {len(txt_links)} fichier(s) TXT"
    )

    chunks = []

    downloaded_links = []

    for index_link, link in enumerate(
        txt_links,
        start=1,
    ):
        filename = Path(
            urlparse(link).path
        ).name

        print(
            f"   ↓ {index_link}/"
            f"{len(txt_links)} "
            f"{filename}"
        )

        try:
            text = download_txt(link)

            chunks.append(text)
            downloaded_links.append(link)

        except Exception as exc:
            print(
                f"     ! Échec : {exc}"
            )

        time.sleep(0.15)

    if not chunks:
        return "error"

    destination.write_text(
        "\n\n".join(chunks),
        encoding="utf-8",
    )

    articles_index[article_url] = {
        "type": "tournament",
        "title": title,
        "year": year,
        "file": str(
            destination.relative_to(ROOT)
        ),
        "txt_links": downloaded_links,
    }

    print(
        f"   ✓ {destination.relative_to(ROOT)}"
    )

    return "tournament"


# ---------------------------------------------------------
# Synchronisation globale
# ---------------------------------------------------------

def sync_all(
    from_year: int | None = None,
    to_year: int | None = None,
    force: bool = False,
):
    TOURNAMENTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    index = load_index()

    print()
    print("=" * 65)
    print("SYNCHRONISATION CLUB DCDL")
    print("=" * 65)

    articles = discover_articles(
        from_year=from_year,
        to_year=to_year,
    )

    print()
    print(
        f"{len(articles)} article(s) "
        "présent(s) dans les sitemaps."
    )
    print()

    counters = {
        "tournament": 0,
        "no_txt": 0,
        "already_checked": 0,
        "error": 0,
    }

    for number, article_url in enumerate(
        articles,
        start=1,
    ):
        print(
            f"[{number}/{len(articles)}] "
            f"{article_url}"
        )

        result = sync_article(
            article_url,
            index,
            force=force,
        )

        counters[result] += 1

        # Sauvegarde progressive :
        # si on interrompt le script, on ne perd pas
        # tout ce qui a déjà été analysé.
        save_index(index)

        time.sleep(0.2)

    print()
    print("=" * 65)
    print("SYNCHRONISATION TERMINÉE")
    print("=" * 65)

    print(
        f"Tournois importés : "
        f"{counters['tournament']}"
    )

    print(
        f"Articles sans TXT : "
        f"{counters['no_txt']}"
    )

    print(
        f"Déjà examinés : "
        f"{counters['already_checked']}"
    )

    print(
        f"Erreurs : "
        f"{counters['error']}"
    )

    print()

    print(
        f"Index : "
        f"{INDEX_FILE.relative_to(ROOT)}"
    )


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Synchronise les tournois du site "
            "Club DCDL à partir de ses sitemaps."
        )
    )

    parser.add_argument(
        "--from-year",
        type=int,
        help="Première année à analyser.",
    )

    parser.add_argument(
        "--to-year",
        type=int,
        help="Dernière année à analyser.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Réanalyse également les articles "
            "déjà présents dans l'index."
        ),
    )

    args = parser.parse_args()

    try:
        sync_all(
            from_year=args.from_year,
            to_year=args.to_year,
            force=args.force,
        )

    except KeyboardInterrupt:
        print()
        print("Synchronisation interrompue.")

    except Exception as exc:
        print(
            f"\nERREUR : {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()