from pathlib import Path
import re
import unicodedata

import streamlit as st

from dcdl.models import SheetOptions
from dcdl.parser import parse_manual, draws_to_text
from dcdl.randomizer import generate_random
from dcdl.lists import (
    load_file,
    sample_draws,
    word_categories,
    draw_files,
    weighted_revision,
    addition_categories,
    parse_additions_file,
    sample_additions,
    weighted_additions_revision,
)
from dcdl.tournaments import (
    tournament_years,
    tournaments_for_year,
    load_tournament,
)
from dcdl.pdf_generator import generate_pdf
from dcdl.solver import solve_draws


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
LISTS = ROOT / "data" / "listes"
TOURNAMENTS = ROOT / "data" / "tournois"

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
    if source_type in ("Liste"):
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
    # RÉVISION ALÉATOIRE
    # --------------------------------------------------------
    if source_type == "Revision":
        n = info.get("n", "")
        seed = info.get("seed")

        name = f"Revision_{n}_mots"

        if seed:
            name += f"_seed{seed}"

        return safe_filename(name) + ".pdf"

    # --------------------------------------------------------
    # TIRAGES ENREGISTRÉS
    # --------------------------------------------------------
    if source_type == "Tirages":
        selected_file = info.get(
            "file",
            "tirages",
        )

        stem = Path(
            selected_file
        ).stem

        name = f"Tirages_{stem}"

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
# SESSION RAJOUTS
# ============================================================

if "additions_session" not in st.session_state:
    st.session_state.additions_session = []

if "additions_answers" not in st.session_state:
    st.session_state.additions_answers = False

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
        "🎯 Tirages",
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

    years = tournament_years(TOURNAMENTS)

    if not years:

        st.warning(
            "Aucun tournoi n'est encore présent dans "
            "data/tournois."
        )

        st.caption(
            "Lance le script de synchronisation depuis "
            "ton Mac pour importer les tournois."
        )

    else:

        year = st.selectbox(
            "Année",
            years,
        )

        available = tournaments_for_year(
            TOURNAMENTS,
            year,
        )

        if not available:

            st.warning(
                "Aucun tournoi disponible pour cette année."
            )

        else:

            labels = [
                tournament["name"]
                for tournament in available
            ]

            selected_name = st.selectbox(
                "Tournoi",
                labels,
            )

            selected_tournament = available[
                labels.index(selected_name)
            ]

            if st.button(
                "Charger le tournoi",
                type="primary",
            ):

                try:

                    st.session_state.draws = (
                        load_tournament(
                            selected_tournament["path"]
                        )
                    )

                    st.session_state.source_info = (
                        selected_tournament[
                            "relative_path"
                        ]
                    )

                    st.session_state.filename_info = {
                        "source": "Tournoi",
                        "city": selected_tournament[
                            "name"
                        ],
                        "year": year,
                    }

                except Exception as e:
                    st.error(str(e))
# ============================================================
# LISTES DE MOTS
# ============================================================

elif source == "📚 Liste":

    revision_mode = st.radio(
        "Mode d'entraînement",
        [
            "Liste précise",
            "Révision aléatoire",
        ],
        horizontal=True,
    )

    # --------------------------------------------------------
    # LISTE PRÉCISE
    # --------------------------------------------------------

    if revision_mode == "Liste précise":

        categories = word_categories(LISTS)

        if not categories:

            st.warning(
                "Aucune liste de mots disponible."
            )

        else:

            category_labels = [
                category["label"]
                for category in categories
            ]

            selected_category_label = st.selectbox(
                "Catégorie",
                category_labels,
            )

            category = next(
                item
                for item in categories
                if item["label"]
                == selected_category_label
            )

            files = category["files"]

            file_labels = [
                path.stem
                for path in files
            ]

            selected_file_label = st.selectbox(
                "Liste",
                file_labels,
            )

            selected_path = files[
                file_labels.index(
                    selected_file_label
                )
            ]

            selection_mode = st.radio(
                "Quantité",
                [
                    "Toute la liste",
                    "Sélection aléatoire",
                ],
                horizontal=True,
            )

            if selection_mode == "Sélection aléatoire":

                n = st.number_input(
                    "Nombre de mots",
                    1,
                    1000,
                    100,
                )

                seed = st.number_input(
                    "Seed (0 = aléatoire)",
                    0,
                    999999,
                    0,
                    key="list_seed",
                )

            if st.button(
                "Charger la liste",
                type="primary",
            ):

                draws = load_file(
                    selected_path
                )

                if selection_mode == "Toute la liste":

                    selected_draws = draws
                    selected_n = None
                    selected_seed = None

                else:

                    selected_draws = sample_draws(
                        draws,
                        min(n, len(draws)),
                        None if seed == 0 else seed,
                    )

                    selected_n = len(
                        selected_draws
                    )

                    selected_seed = (
                        None
                        if seed == 0
                        else seed
                    )

                st.session_state.draws = (
                    selected_draws
                )

                relative = str(
                    selected_path.relative_to(
                        LISTS
                    )
                )

                st.session_state.source_info = (
                    relative
                )

                st.session_state.filename_info = {
                    "source": "Liste",
                    "file": relative,
                    "mode": selection_mode,
                    "n": selected_n,
                    "seed": selected_seed,
                }

    # --------------------------------------------------------
    # RÉVISION ALÉATOIRE INTELLIGENTE
    # --------------------------------------------------------

    else:

        st.caption(
            "Compose une séance à partir de plusieurs "
            "familles de mots. Les mots prioritaires "
            "reviennent plus souvent."
        )

        n = st.number_input(
            "Nombre de mots",
            1,
            1000,
            100,
            key="revision_n",
        )

        st.markdown("##### Sources principales")

        c1, c2, c3 = st.columns(3)

        include_standard = c1.checkbox(
            "Listes standards",
            True,
        )

        include_priority = c2.checkbox(
            "Prioritaires",
            True,
            help=(
                "Contient notamment L_inratable. "
                "Ces mots ont davantage de chances "
                "d'être sélectionnés."
            ),
        )

        include_frequent = c3.checkbox(
            "Socle fréquent",
            True,
            help=(
                "Mots très fréquents à revoir "
                "régulièrement sans qu'ils dominent "
                "la séance."
            ),
        )

        st.markdown("##### Sources complémentaires")

        c4, c5, c6 = st.columns(3)

        include_entries = c4.checkbox(
            "Entrées",
            False,
        )

        include_thematic = c5.checkbox(
            "Thématiques",
            False,
        )

        include_old = c6.checkbox(
            "Anciennes listes",
            False,
        )

        with st.expander(
            "⚙️ Pondération"
        ):

            st.caption(
                "Plus le poids est élevé, plus les mots "
                "de cette famille ont de chances "
                "d'apparaître."
            )

            standard_weight = st.slider(
                "Listes standards",
                1,
                10,
                1,
                key="standard_weight",
            )

            priority_weight = st.slider(
                "Prioritaires",
                1,
                10,
                4,
                key="priority_weight",
            )

            frequent_weight = st.slider(
                "Socle fréquent",
                1,
                10,
                1,
                key="frequent_weight",
            )

        seed = st.number_input(
            "Seed (0 = aléatoire)",
            0,
            999999,
            0,
            key="revision_seed",
        )

        if st.button(
            "Générer la révision",
            type="primary",
        ):

            if not any(
                [
                    include_standard,
                    include_priority,
                    include_frequent,
                    include_entries,
                    include_thematic,
                    include_old,
                ]
            ):

                st.warning(
                    "Sélectionne au moins une source."
                )

            else:

                draws = weighted_revision(
                    LISTS,
                    n,
                    None if seed == 0 else seed,
                    include_standard=include_standard,
                    include_priority=include_priority,
                    include_frequent=include_frequent,
                    include_entries=include_entries,
                    include_thematic=include_thematic,
                    include_old=include_old,
                    priority_weight=priority_weight,
                    standard_weight=standard_weight,
                    frequent_weight=frequent_weight,
                )

                st.session_state.draws = draws

                st.session_state.source_info = (
                    "Révision aléatoire"
                )

                st.session_state.filename_info = {
                    "source": "Revision",
                    "n": len(draws),
                    "seed": (
                        None
                        if seed == 0
                        else seed
                    ),
                }

# ============================================================
# TIRAGES ENREGISTRÉS
# ============================================================

elif source == "🎯 Tirages":

    files = draw_files(LISTS)

    if not files:

        st.warning(
            "Aucun fichier disponible dans "
            "data/listes/Tirages."
        )

    else:

        labels = [
            path.stem
            for path in files
        ]

        selected_label = st.selectbox(
            "Fichier de tirages",
            labels,
        )

        selected_path = files[
            labels.index(selected_label)
        ]

        selection_mode = st.radio(
            "Quantité",
            [
                "Tous les tirages",
                "Sélection aléatoire",
            ],
            horizontal=True,
        )

        if selection_mode == "Sélection aléatoire":

            n = st.number_input(
                "Nombre de tirages",
                1,
                1000,
                300,
                key="draw_file_n",
            )

            seed = st.number_input(
                "Seed (0 = aléatoire)",
                0,
                999999,
                0,
                key="draw_file_seed",
            )

        if st.button(
            "Charger les tirages",
            type="primary",
        ):

            draws = load_file(
                selected_path
            )

            if selection_mode == "Tous les tirages":

                selected_draws = draws
                selected_n = None
                selected_seed = None

            else:

                selected_draws = sample_draws(
                    draws,
                    min(n, len(draws)),
                    None if seed == 0 else seed,
                )

                selected_n = len(
                    selected_draws
                )

                selected_seed = (
                    None
                    if seed == 0
                    else seed
                )

            st.session_state.draws = (
                selected_draws
            )

            relative = str(
                selected_path.relative_to(
                    LISTS
                )
            )

            st.session_state.source_info = (
                relative
            )

            st.session_state.filename_info = {
                "source": "Tirages",
                "file": relative,
                "mode": selection_mode,
                "n": selected_n,
                "seed": selected_seed,
            }

# ============================================================
# RAJOUTS — RÉVISION DE MASSE
# ============================================================

elif source == "➕ Rajouts":

    st.subheader("➕ Révision des rajouts")

    st.caption(
        "Révise une série complète d'un coup, "
        "puis affiche toutes les réponses lorsque tu veux vérifier."
    )

    revision_mode = st.radio(
        "Mode",
        [
            "Révision aléatoire",
            "Liste précise",
        ],
        horizontal=True,
    )

    # --------------------------------------------------------
    # RÉVISION ALÉATOIRE
    # --------------------------------------------------------

    if revision_mode == "Révision aléatoire":

        c1, c2 = st.columns(2)

        n = c1.number_input(
            "Nombre de rajouts",
            min_value=1,
            max_value=1000,
            value=100,
            step=10,
            key="additions_random_n",
        )

        priority_weight = c2.slider(
            "Poids des prioritaires",
            min_value=1,
            max_value=10,
            value=4,
            key="additions_priority_weight",
            help=(
                "Un rajout prioritaire a davantage "
                "de chances d'apparaître dans la série."
            ),
        )

        seed = st.number_input(
            "Seed (0 = aléatoire)",
            min_value=0,
            max_value=999999,
            value=0,
            key="additions_random_seed",
        )

        if st.button(
            "🎲 Générer les rajouts",
            type="primary",
        ):

            additions = weighted_additions_revision(
                LISTS,
                n=int(n),
                seed=(
                    None
                    if seed == 0
                    else int(seed)
                ),
                priority_weight=int(
                    priority_weight
                ),
            )

            st.session_state.additions_session = (
                additions
            )

            st.session_state.additions_answers = (
                False
            )

    # --------------------------------------------------------
    # LISTE PRÉCISE
    # --------------------------------------------------------

    else:

        categories = addition_categories(
            LISTS
        )

        if not categories:

            st.warning(
                "Aucun fichier de rajouts trouvé dans "
                "data/listes/Rajouts."
            )

        else:

            category_labels = [
                category["label"]
                for category in categories
            ]

            selected_category_label = st.selectbox(
                "Catégorie",
                category_labels,
                key="addition_category",
            )

            category = next(
                item
                for item in categories
                if item["label"]
                == selected_category_label
            )

            files = category["files"]

            file_labels = [
                path.stem
                for path in files
            ]

            selected_file_label = st.selectbox(
                "Liste",
                file_labels,
                key="addition_file",
            )

            selected_path = files[
                file_labels.index(
                    selected_file_label
                )
            ]

            n = st.number_input(
                "Nombre de rajouts",
                min_value=1,
                max_value=1000,
                value=100,
                step=10,
                key="additions_file_n",
            )

            seed = st.number_input(
                "Seed (0 = aléatoire)",
                min_value=0,
                max_value=999999,
                value=0,
                key="additions_file_seed",
            )

            if st.button(
                "🎲 Générer les rajouts",
                type="primary",
            ):

                additions = (
                    parse_additions_file(
                        selected_path
                    )
                )

                additions = sample_additions(
                    additions,
                    n=int(n),
                    seed=(
                        None
                        if seed == 0
                        else int(seed)
                    ),
                )

                st.session_state.additions_session = (
                    additions
                )

                st.session_state.additions_answers = (
                    False
                )


    # ========================================================
    # AFFICHAGE DE LA SÉRIE
    # ========================================================

    additions = (
        st.session_state.additions_session
    )

    if additions:

        st.divider()

        st.markdown(
            f"### Série — {len(additions)} rajouts"
        )

        # ----------------------------------------------------
        # BOUTON RÉPONSES
        # ----------------------------------------------------

        if not st.session_state.additions_answers:

            if st.button(
                "👁️ Afficher les réponses",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.additions_answers = True
                st.rerun()

        else:

            if st.button(
                "🙈 Masquer les réponses",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.additions_answers = False
                st.rerun()


        # ----------------------------------------------------
        # GRILLE 4 COLONNES
        # ----------------------------------------------------

        columns = st.columns(4)

        total = len(additions)

        # Nombre de lignes nécessaires par colonne.
        # 100 rajouts => 25 par colonne.
        per_column = (
            total + 3
        ) // 4

        for index, addition in enumerate(
            additions
        ):

            column_index = min(
                index // per_column,
                3,
            )

            if addition.letter == "(X)":
                question = (
                    f"{index + 1}. "
                    f"{addition.base} (X)"
                )
            else:
                question = (
                    f"{index + 1}. "
                    f"{addition.base} "
                    f"+ {addition.letter}"
                )

            if st.session_state.additions_answers:

                text = (
                    f"{question} "
                    f"→ **{addition.answer}**"
                )

            else:

                text = question

            with columns[column_index]:

                st.markdown(
                    text
                )

# ============================================================
# ALÉATOIRE
# ============================================================

elif source == "🎲 Aléatoire":

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

if draws and source != "➕ Rajouts":

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

elif source != "➕ Rajouts":

    st.info(
        "Choisis une source et charge des tirages "
        "pour commencer."
    )