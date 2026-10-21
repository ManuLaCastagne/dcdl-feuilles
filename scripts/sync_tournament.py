from pathlib import Path
import argparse
import re
import sys
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
TOURNAMENTS = ROOT / "data" / "tournois"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154 Safari/537.36"
    )
}


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get_page(url: str) -> str:
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=(10, 30),
    )
    response.raise_for_status()
    return response.text


def find_txt_links(page_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for element in soup.find_all("a", href=True):
        href = urljoin(page_url, element["href"])

        if re.search(r"\.txt(?:\?|$)", href, re.IGNORECASE):
            links.append(href)

    return list(dict.fromkeys(links))


def download_txt(url: str) -> str:
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=(10, 30),
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "ISO-8859-1"
    )

    return response.text


def sync_tournament(
    city: str,
    year: str,
    month: int,
    url: str | None = None,
):
    slug = slugify(city)

    if not url:
        url = (
            "https://clubdcdl.over-blog.com/"
            f"{year}/{month:02d}/"
            f"{slug}-{year}.html"
        )

    print()
    print("Tournoi :", city)
    print("Article :", url)
    print()

    print("Récupération de l'article...")

    html = get_page(url)

    links = find_txt_links(url, html)

    if not links:
        raise RuntimeError(
            "Aucun fichier .txt trouvé dans l'article."
        )

    print(f"{len(links)} fichier(s) trouvé(s).")

    chunks = []

    for index, link in enumerate(links, start=1):
        print(
            f"Téléchargement {index}/{len(links)} : {link}"
        )
        chunks.append(download_txt(link))

    destination_dir = TOURNAMENTS / str(year)
    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = destination_dir / f"{slug}.txt"

    destination.write_text(
        "\n".join(chunks),
        encoding="utf-8",
    )

    print()
    print("✓ Tournoi enregistré :")
    print(destination)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Importe un tournoi Club DCDL "
            "dans la base locale."
        )
    )

    parser.add_argument(
        "city",
        help='Ville, par exemple "Le Touquet"',
    )

    parser.add_argument(
        "year",
        help="Année du tournoi",
    )

    parser.add_argument(
        "month",
        type=int,
        help="Mois du tournoi (1 à 12)",
    )

    parser.add_argument(
        "--url",
        help="URL Overblog explicite, facultative.",
    )

    args = parser.parse_args()

    try:
        sync_tournament(
            city=args.city,
            year=args.year,
            month=args.month,
            url=args.url,
        )

    except Exception as exc:
        print()
        print(
            f"ERREUR : {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()