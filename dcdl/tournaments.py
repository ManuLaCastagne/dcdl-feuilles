from pathlib import Path
import re

from .parser import parse_manual


# ============================================================
# CATALOGUE LOCAL DES TOURNOIS
# ============================================================

def list_tournaments(root: Path) -> list[dict]:
    """
    Retourne tous les tournois présents dans data/tournois.

    Structure attendue :

        data/tournois/
            2026/
                le-touquet.txt
                narbonne.txt
                vannes.txt
    """

    root = Path(root)

    if not root.exists():
        return []

    tournaments = []

    for path in sorted(root.rglob("*.txt")):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue

        if len(relative.parts) < 2:
            continue

        year = relative.parts[0]
        stem = path.stem

        # Affichage plus agréable :
        # le-touquet -> Le Touquet
        name = re.sub(
            r"[-_]+",
            " ",
            stem,
        ).strip().title()

        tournaments.append({
            "name": name,
            "year": year,
            "path": path,
            "relative_path": str(relative),
        })

    return tournaments


def tournament_years(root: Path) -> list[str]:
    """
    Liste les années disponibles, de la plus récente
    à la plus ancienne.
    """

    tournaments = list_tournaments(root)

    years = {
        tournament["year"]
        for tournament in tournaments
    }

    def sort_key(value):
        try:
            return int(value)
        except ValueError:
            return 0

    return sorted(
        years,
        key=sort_key,
        reverse=True,
    )


def tournaments_for_year(
    root: Path,
    year: str,
) -> list[dict]:
    """
    Retourne les tournois d'une année.
    """

    return [
        tournament
        for tournament in list_tournaments(root)
        if tournament["year"] == str(year)
    ]


def load_tournament(path: Path):
    """
    Charge les tirages d'un tournoi local.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Tournoi introuvable : {path}"
        )

    # On essaie plusieurs encodages car les anciens
    # fichiers DCDL ne sont pas toujours en UTF-8.
    text = None

    for encoding in (
        "utf-8",
        "utf-8-sig",
        "cp1252",
        "iso-8859-1",
    ):
        try:
            text = path.read_text(
                encoding=encoding,
            )
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ValueError(
            f"Impossible de lire le fichier : {path.name}"
        )

    draws = parse_manual(text)

    if not draws:
        raise ValueError(
            "Le fichier a été lu mais aucun tirage "
            "n'a été reconnu."
        )

    return draws