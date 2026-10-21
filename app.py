from pathlib import Path
import re
import unicodedata

import streamlit as st

from dcdl.models import SheetOptions
from dcdl.parser import parse_manual, draws_to_text
from dcdl.randomizer import generate_random
from dcdl.lists import list_files, load_file, sample_draws
from dcdl.tournaments import fetch_tournament
from dcdl.pdf_generator import generate_pdf
from dcdl.solver import solve_draws


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
LISTS = ROOT / "data" / "listes"

st.set_page_config(
    page_title="DCDL — Feuilles de jeu",
    page_icon="🎲",
    layout="wide",
)

st.title("🎲 DCDL — Générateur de feuilles de jeu")
st.caption(
    "Créer une feuille d'entraînement depuis des tirages saisis, "
    "un tournoi, une liste ou une génération aléatoire."
)


# ============================================================
# NOM AUTOMATIQUE DU PDF
# ============================================================

def safe_filename(text):
    """
    Nettoie une chaîne pour qu'elle puisse être utilisée
    sans problème comme nom de fichier.
    """
    text = str(text)

    # Supprime les accents : caché -> cache
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    # Remplace les caractères gênants par _
    text = re.sub(r"[^\w.-]+", "_", text)

    # Évite les suites de _
    text = re.sub(r"_+", "_", text)

    return text.strip("_.-")


def build_filename():
    """
    Construit automatiquement le nom du PDF
    à partir des critères utilisés dans l'IHM.
    """
    info = st.session_state.get("filename_info", {})
    source_type = info.get("source", "Feuille")

    # --------------------------------------------------------
    # MANUEL
    # --------------------------------------------------------
    if source_type == "Manuel":
        count = len(st.session_state.draws)

        return safe_filename(
            f"Manuel_{count}_tirages"
        ) + ".pdf"

    # --------------------------------------------------------
    # TOURNOI
    # --------------------------------------------------------
    if source_type == "Tournoi":
        city = info.get("city", "tournoi")
        year = info.get("year", "")

        name = f"Tournoi_{city}"

        if year:
            name += f"_{year}"

        return safe_filename(name) + ".pdf"

    # --------------------------------------------------------
    # LISTE / RAJOUTS
    # --------------------------------------------------------
    if source_type in ("Liste", "Rajouts"):
        selected_file = info.get("file", "liste")

        # On retire le .txt
        stem = Path(selected_file).stem

        selection_mode = info.get(
            "mode",
            "Toute la liste",
        )

        name = f"{source_type}_{stem}"

        if selection_mode == "Sélection aléatoire":
            n = info.get("n")

            if n:
                name += f"_{n}_tirages"

            seed = info.get("seed")

            if seed:
                name += f"_seed{seed}"

        return safe_filename(name) + ".pdf"

    # --------------------------------------------------------
    # ALÉATOIRE
    # --------------------------------------------------------
    if source_type == "Aléatoire":
        n = info.get("n", "")
        ratio = info.get("ratio", 0)
        letters = info.get("letters", 10)
        required = info.get("required", "")
        seed = info.get("seed")

        percentage_numbers = round(ratio * 100)

        name = (
            f"Aleatoire_{n}_tirages_"
            f"{percentage_numbers}pct_chiffres_"
            f"{letters}L"
        )

        # Lettres obligatoires
        required_clean = "".join(
            char.upper()
            for char in str(required)
            if char.isalpha()
        )

        if required_clean:
            name += f"_{required_clean}"

        if seed:
            name += f"_seed{seed}"

        return safe_filename(name) + ".pdf"

    return "Feuille_DCDL.pdf"


# ============================================================
# SESSION STATE
# ============================================================

if "draws" not in st.session_state:
    st.session_state.draws = []

if "source_info" not in st.session_state:
    st.session_state.source_info = ""

if "filename_info" not in st.session_state:
    st.session_state.filename_info = {}


# ============================================================
# OPTIONS DE LA FEUILLE
# ============================================================

with st.sidebar:
    st.header("Feuille")

    sort_tiles = st.checkbox(
        "Trier les plaques",
        False,
    )

    show_solutions = st.checkbox(
        "Afficher les solutions",
        True,
    )

    max_solutions = st.number_input(
        "Nombre max. de solutions",
        1,
        100000,
        10000,
    )

    top_letters = st.text_input(
        "Filtrer sur un top lettres (facultatif)",
        placeholder="ex. 10L",
    )


# ============================================================
# CHOIX DE LA SOURCE
# ============================================================

source = st.segmented_control(
    "Source",
    [
        "✍️ Manuel",
        "🏆 Tournoi",
        "📚 Liste",
        "➕ Rajouts",
        "🎲 Aléatoire",
    ],
    default="✍️ Manuel",
)


# ============================================================
# MANUEL
# ============================================================

if source == "✍️ Manuel":

    text = st.text_area(
        "Un tirage par ligne",
        height=260,
        placeholder=(
            "SAPEKDUSOD\n"
            "1 10 8 7 9 25 / 203"
        ),
    )

    if st.button(
        "Charger les tirages",
        type="primary",
    ):
        st.session_state.draws = parse_manual(text)

        st.session_state.source_info = "Saisie manuelle"

        st.session_state.filename_info = {
            "source": "Manuel",
        }


# ============================================================
# TOURNOI
# ============================================================

elif source == "🏆 Tournoi":

    c1, c2, c3 = st.columns(3)

    city = c1.text_input(
        "Ville",
        "le-touquet",
    )

    year = c2.text_input(
        "Année",
        "2026",
    )

    month = c3.selectbox(
        "Mois",
        range(1, 13),
        index=0,
        format_func=lambda m: [
            "Janvier",
            "Février",
            "Mars",
            "Avril",
            "Mai",
            "Juin",
            "Juillet",
            "Août",
            "Septembre",
            "Octobre",
            "Novembre",
            "Décembre",
        ][m - 1],
    )

    url = st.text_input(
        "URL de l'article (facultatif)",
        placeholder=(
            "https://clubdcdl.over-blog.com/"
            "2026/09/..."
        ),
    )

    if st.button(
        "Récupérer le tournoi",
        type="primary",
    ):
        try:
            with st.spinner(
                "Récupération des fichiers de tirages…"
            ):
                st.session_state.draws, page = (
                    fetch_tournament(
                        city,
                        year,
                        url,
                        month,
                    )
                )

                st.session_state.source_info = page

                st.session_state.filename_info = {
                    "source": "Tournoi",
                    "city": city,
                    "year": year,
                }

        except Exception as e:
            st.error(str(e))


# ============================================================
# LISTE / RAJOUTS
# ============================================================

elif source in ("📚 Liste", "➕ Rajouts"):

    files = list_files(LISTS)

    rel = [
        str(path.relative_to(LISTS))
        for path in files
    ]

    selected = st.selectbox(
        "Fichier",
        rel if rel else ["Aucun fichier"],
    )

    selection_mode = st.radio(
        "Mode de sélection",
        [
            "Toute la liste",
            "Sélection aléatoire",
        ],
        horizontal=True,
    )

    # Ces paramètres n'apparaissent que
    # pour une sélection aléatoire.
    if selection_mode == "Sélection aléatoire":

        n = st.number_input(
            "Nombre de tirages",
            1,
            1000,
            200,
        )

        seed = st.number_input(
            "Seed (0 = aléatoire)",
            0,
            999999,
            0,
        )

    if (
        st.button(
            "Charger la liste",
            type="primary",
        )
        and files
    ):

        path = files[
            rel.index(selected)
        ]

        is_rajouts = (
            source == "➕ Rajouts"
        )

        draws = load_file(
            path,
            rajouts=is_rajouts,
        )

        if selection_mode == "Toute la liste":

            st.session_state.draws = draws

            selected_n = None
            selected_seed = None

        else:

            st.session_state.draws = sample_draws(
                draws,
                min(n, len(draws)),
                None if seed == 0 else seed,
            )

            # On stocke le nombre réellement extrait,
            # notamment si la liste contient moins
            # d'éléments que demandé.
            selected_n = min(
                n,
                len(draws),
            )

            selected_seed = (
                None
                if seed == 0
                else seed
            )

        st.session_state.source_info = selected

        st.session_state.filename_info = {
            "source": (
                "Rajouts"
                if is_rajouts
                else "Liste"
            ),
            "file": selected,
            "mode": selection_mode,
            "n": selected_n,
            "seed": selected_seed,
        }


# ============================================================
# ALÉATOIRE
# ============================================================

else:

    c1, c2, c3 = st.columns(3)

    n = c1.number_input(
        "Nombre de tirages",
        1,
        1000,
        100,
    )

    ratio = (
        c2.slider(
            "Part de chiffres",
            0,
            100,
            25,
        )
        / 100
    )

    letters = c3.selectbox(
        "Nombre de lettres",
        [9, 10],
        index=1,
    )

    required = st.text_input(
        "Lettres obligatoires (facultatif)",
        placeholder="ex. KW",
        help=(
            "Saisis simplement les lettres à imposer "
            "dans chaque tirage de lettres. "
            "Exemple : KW."
        ),
    )

    seed = st.number_input(
        "Seed (0 = aléatoire)",
        0,
        999999,
        0,
        key="random_seed",
    )

    if st.button(
        "Générer les tirages",
        type="primary",
    ):

        st.session_state.draws = (
            generate_random(
                n,
                ratio,
                letters,
                required,
                None if seed == 0 else seed,
            )
        )

        st.session_state.source_info = (
            "Génération aléatoire"
        )

        st.session_state.filename_info = {
            "source": "Aléatoire",
            "n": n,
            "ratio": ratio,
            "letters": letters,
            "required": required,
            "seed": (
                None
                if seed == 0
                else seed
            ),
        }


# ============================================================
# PRÉVISUALISATION
# ============================================================

draws = st.session_state.draws

if draws:

    st.divider()

    st.subheader(
        f"Prévisualisation — "
        f"{len(draws)} tirages"
    )

    edited = st.text_area(
        (
            "Tu peux corriger, supprimer, "
            "ajouter ou réordonner les tirages "
            "avant génération"
        ),
        value=draws_to_text(draws),
        height=300,
        key=(
            f"preview_"
            f"{len(draws)}_"
            f"{st.session_state.source_info}"
        ),
    )

    if st.button(
        "Appliquer les modifications"
    ):
        st.session_state.draws = (
            parse_manual(edited)
        )

        st.rerun()


    # ========================================================
    # SOLVEUR CLAX
    # ========================================================

    st.subheader("Solveur CLAX")

    st.caption(
        "Calcule automatiquement le top, "
        "le nombre de solutions et les solutions "
        "via dcdl-laxou.fr."
    )

    if st.button(
        "🧠 Résoudre avec CLAX",
        type="secondary",
    ):
        try:

            with st.spinner(
                f"CLAX calcule "
                f"{len(st.session_state.draws)} "
                f"tirages…"
            ):

                st.session_state.draws = (
                    solve_draws(
                        st.session_state.draws
                    )
                )

            st.success(
                "Résolution CLAX terminée."
            )

            st.rerun()

        except Exception as e:

            st.error(
                "Impossible d’interroger CLAX : "
                f"{e}"
            )

            st.info(
                "En local, vérifie que Google Chrome "
                "est installé. Le déploiement cloud "
                "demandera une adaptation du moteur "
                "CLAX pour ne plus dépendre d’un "
                "navigateur."
            )


    # ========================================================
    # ÉTAT DE LA RÉSOLUTION
    # ========================================================

    solved_count = sum(
        bool(draw.best or draw.solutions)
        for draw
        in st.session_state.draws
    )

    if solved_count:

        st.caption(
            f"{solved_count}/"
            f"{len(st.session_state.draws)} "
            f"tirages enrichis par CLAX."
        )


    # ========================================================
    # GÉNÉRATION DU PDF
    # ========================================================

    options = SheetOptions(
        sort_tiles=sort_tiles,
        max_solutions=int(max_solutions),
        letters_top=top_letters.strip(),
        show_solutions=show_solutions,
    )

    pdf = generate_pdf(
        st.session_state.draws,
        options,
        ASSETS,
    )


    # ========================================================
    # NOM AUTOMATIQUE
    # ========================================================

    pdf_filename = build_filename()

    st.download_button(
        "📄 Télécharger le PDF",
        pdf,
        file_name=pdf_filename,
        mime="application/pdf",
        type="primary",
    )

    st.caption(
        f"Nom du fichier : **{pdf_filename}**"
    )

    st.caption(
        "PDF A4 paysage, rendu manuscrit. "
        "Les tops et solutions CLAX sont inclus "
        "lorsqu’ils ont été calculés."
    )


# ============================================================
# AUCUN TIRAGE
# ============================================================

else:

    st.info(
        "Choisis une source et charge des tirages "
        "pour commencer."
    )