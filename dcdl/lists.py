from pathlib import Path
import random
import re

from .parser import parse_manual, parse_rajouts


# ============================================================
# DOSSIERS CONNUS
# ============================================================

STANDARD_DIR = "Listes standards"
PRIORITY_DIR = "Prioritaires"
FREQUENT_DIR = "Socle fréquent"
THEMATIC_DIR = "Listes thématiques"
ENTRIES_DIR = "Entrées"
OLD_DIR = "Anciennes listes"
HIDDEN_WORDS_DIR = "Mots dissimulés"
DRAWS_DIR = "Tirages"
RAJOUTS_DIR = "Rajouts"


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def natural_key(value):
    """
    Tri naturel :
    L2 avant L10, E2025 avant E2026, etc.
    """
    text = str(value)

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


def list_files(root: Path):
    """
    Compatibilité avec l'ancien fonctionnement.
    Liste récursivement tous les .txt.
    """
    root = Path(root)

    if not root.exists():
        return []

    return sorted(
        [
            path
            for path in root.rglob("*.txt")
            if path.is_file()
        ],
        key=lambda path: natural_key(str(path)),
    )


def files_in_directory(root: Path, directory_name: str):
    """
    Retourne les fichiers .txt directement contenus
    dans une catégorie.
    """
    directory = Path(root) / directory_name

    if not directory.exists():
        return []

    return sorted(
        [
            path
            for path in directory.glob("*.txt")
            if path.is_file()
        ],
        key=lambda path: natural_key(path.name),
    )


def load_file(path: Path, rajouts=False):
    """
    Charge un fichier de tirages/mots.
    """
    path = Path(path)

    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    return (
        parse_rajouts(text)
        if rajouts
        else parse_manual(text)
    )


def sample_draws(draws, n, seed=None):
    """
    Extrait n éléments sans remise.
    """
    if n >= len(draws):
        return draws.copy()

    return random.Random(seed).sample(
        draws,
        n,
    )


# ============================================================
# CATÉGORIES DE MOTS
# ============================================================

def word_categories(root: Path):
    """
    Catégories proposées dans le mode Liste précise.

    Les dossiers techniques (Rajouts, Tirages, etc.)
    n'apparaissent pas ici.
    """
    categories = [
        ("Listes standards", STANDARD_DIR),
        ("Prioritaires", PRIORITY_DIR),
        ("Socle fréquent", FREQUENT_DIR),
        ("Entrées", ENTRIES_DIR),
        ("Listes thématiques", THEMATIC_DIR),
        ("Anciennes listes", OLD_DIR),
    ]

    result = []

    for label, directory in categories:
        files = files_in_directory(
            root,
            directory,
        )

        if files:
            result.append(
                {
                    "label": label,
                    "directory": directory,
                    "files": files,
                }
            )

    return result


def draw_files(root: Path):
    """
    Retourne tous les fichiers contenant des tirages
    déjà constitués.

    Cela comprend :
    - Tirages
    - Mots dissimulés

    Les mots dissimulés sont déjà transformés en tirages
    de 10 lettres avec lettres parasites : ils doivent donc
    être utilisés tels quels et ne pas être remélangés.
    """
    files = []

    files.extend(
        files_in_directory(
            root,
            DRAWS_DIR,
        )
    )

    files.extend(
        files_in_directory(
            root,
            HIDDEN_WORDS_DIR,
        )
    )

    return sorted(
        files,
        key=lambda path: natural_key(
            str(path.relative_to(root))
        ),
    )

def rajouts_files(root: Path):
    return files_in_directory(
        root,
        RAJOUTS_DIR,
    )


# ============================================================
# RÉVISION ALÉATOIRE INTELLIGENTE
# ============================================================

def _draw_key(draw):
    """
    Produit une clé stable pour éviter de sortir deux fois
    exactement le même élément.

    On évite de dépendre de la structure interne précise
    de Draw.
    """
    return repr(draw)


def weighted_revision(
    root: Path,
    n: int,
    seed=None,
    include_standard=True,
    include_priority=True,
    include_frequent=True,
    include_entries=False,
    include_thematic=False,
    include_old=False,
    priority_weight=4,
    standard_weight=1,
    frequent_weight=1,
):
    """
    Fabrique une séance aléatoire pondérée.

    Un même mot présent dans plusieurs sources voit son poids
    augmenter, mais il ne peut apparaître qu'une seule fois
    dans la séance finale.
    """

    rng = random.Random(seed)

    weighted = {}

    def add_directory(directory_name, weight):
        files = files_in_directory(
            root,
            directory_name,
        )

        for path in files:
            draws = load_file(path)

            for draw in draws:
                key = _draw_key(draw)

                if key not in weighted:
                    weighted[key] = {
                        "draw": draw,
                        "weight": 0,
                    }

                weighted[key]["weight"] += weight

    # Base de travail
    if include_standard:
        add_directory(
            STANDARD_DIR,
            standard_weight,
        )

    # Très important : les inratables reviennent davantage
    if include_priority:
        add_directory(
            PRIORITY_DIR,
            priority_weight,
        )

    # Entretien régulier
    if include_frequent:
        add_directory(
            FREQUENT_DIR,
            frequent_weight,
        )

    # Sources facultatives
    if include_entries:
        add_directory(
            ENTRIES_DIR,
            1,
        )

    if include_thematic:
        add_directory(
            THEMATIC_DIR,
            1,
        )

    if include_old:
        add_directory(
            OLD_DIR,
            1,
        )

    pool = list(weighted.values())

    if not pool:
        return []

    wanted = min(
        int(n),
        len(pool),
    )

    selected = []

    # Tirage pondéré sans remise.
    for _ in range(wanted):

        total_weight = sum(
            item["weight"]
            for item in pool
        )

        position = rng.uniform(
            0,
            total_weight,
        )

        cumulative = 0
        selected_index = 0

        for index, item in enumerate(pool):

            cumulative += item["weight"]

            if position <= cumulative:
                selected_index = index
                break

        selected.append(
            pool.pop(selected_index)["draw"]
        )

    rng.shuffle(selected)

    return selected

# ============================================================
# RAJOUTS — RÉVISION DE MASSE
# ============================================================

from dataclasses import dataclass


@dataclass
class Addition:
    base: str
    letter: str
    answer: str


def parse_additions_file(path: Path):
    """
    Lit un fichier de rajouts au format :

        GITANE + A = ANTIÂGE
        FADÉES + I = DÉFAISÉ

    Retourne une liste d'Addition.
    """
    text = Path(path).read_text(
        encoding="utf-8",
        errors="ignore",
    )

    additions = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        match = re.match(
            r"^\s*(.+?)\s*\+\s*(.+?)\s*=\s*(.+?)\s*$",
            line,
        )

        if not match:
            continue

        additions.append(
            Addition(
                base=match.group(1).strip().upper(),
                letter=match.group(2).strip().upper(),
                answer=match.group(3).strip().upper(),
            )
        )

    return additions


def addition_categories(root: Path):
    """
    Recherche les catégories présentes dans data/listes/Rajouts.

    Exemple :
        Rajouts/
            Standards/
            Prioritaires/

    Si des fichiers .txt sont directement dans Rajouts/,
    ils apparaissent dans une catégorie "Rajouts".
    """
    rajouts_root = Path(root) / RAJOUTS_DIR

    if not rajouts_root.exists():
        return []

    categories = []

    # Fichiers directement dans Rajouts/
    root_files = sorted(
        [
            path
            for path in rajouts_root.glob("*.txt")
            if path.is_file()
        ],
        key=lambda path: natural_key(path.name),
    )

    if root_files:
        categories.append(
            {
                "label": "Rajouts",
                "directory": rajouts_root,
                "files": root_files,
                "priority": False,
            }
        )

    # Sous-répertoires
    directories = sorted(
        [
            path
            for path in rajouts_root.iterdir()
            if path.is_dir()
        ],
        key=lambda path: natural_key(path.name),
    )

    for directory in directories:

        files = sorted(
            [
                path
                for path in directory.rglob("*.txt")
                if path.is_file()
            ],
            key=lambda path: natural_key(path.name),
        )

        if not files:
            continue

        is_priority = (
            "prior" in directory.name.lower()
            or "inratable" in directory.name.lower()
        )

        categories.append(
            {
                "label": directory.name,
                "directory": directory,
                "files": files,
                "priority": is_priority,
            }
        )

    return categories


def sample_additions(
    additions,
    n=100,
    seed=None,
):
    """
    Sélection aléatoire simple sans doublon.
    """
    rng = random.Random(seed)

    if n >= len(additions):
        result = additions.copy()
        rng.shuffle(result)
        return result

    return rng.sample(
        additions,
        n,
    )


def weighted_additions_revision(
    root: Path,
    n=100,
    seed=None,
    priority_weight=4,
):
    """
    Construit une séance de rajouts à partir de toutes
    les catégories.

    Les dossiers dont le nom contient 'prior' ou
    'inratable' ont un poids supérieur.

    Un même rajout n'apparaît qu'une fois dans une séance.
    """
    rng = random.Random(seed)

    categories = addition_categories(root)

    weighted = {}

    for category in categories:

        weight = (
            priority_weight
            if category["priority"]
            else 1
        )

        for path in category["files"]:

            additions = parse_additions_file(path)

            for addition in additions:

                key = (
                    addition.base,
                    addition.letter,
                    addition.answer,
                )

                if key not in weighted:
                    weighted[key] = {
                        "addition": addition,
                        "weight": 0,
                    }

                weighted[key]["weight"] += weight

    pool = list(weighted.values())

    if not pool:
        return []

    wanted = min(
        int(n),
        len(pool),
    )

    selected = []

    # Sélection pondérée sans remise
    for _ in range(wanted):

        total_weight = sum(
            item["weight"]
            for item in pool
        )

        position = rng.uniform(
            0,
            total_weight,
        )

        cumulative = 0

        for index, item in enumerate(pool):

            cumulative += item["weight"]

            if position <= cumulative:

                selected.append(
                    pool.pop(index)["addition"]
                )

                break

    # On remélange la séance finale
    rng.shuffle(selected)

    return selected