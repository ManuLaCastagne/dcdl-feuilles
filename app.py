from pathlib import Path
import streamlit as st
from dcdl.models import SheetOptions
from dcdl.parser import parse_manual, draws_to_text
from dcdl.randomizer import generate_random
from dcdl.lists import list_files, load_file, sample_draws
from dcdl.tournaments import fetch_tournament
from dcdl.pdf_generator import generate_pdf
from dcdl.solver import solve_draws

ROOT=Path(__file__).parent; ASSETS=ROOT/"assets"; LISTS=ROOT/"data"/"listes"
st.set_page_config(page_title="DCDL — Feuilles de jeu", page_icon="🎲", layout="wide")
st.title("🎲 DCDL — Générateur de feuilles de jeu")
st.caption("Créer une feuille d'entraînement depuis des tirages saisis, un tournoi, une liste ou une génération aléatoire.")

if "draws" not in st.session_state: st.session_state.draws=[]
if "source_info" not in st.session_state: st.session_state.source_info=""

with st.sidebar:
    st.header("Feuille")
    name=st.text_input("Nom", "Feuille d'entraînement")
    sort_tiles=st.checkbox("Trier les plaques", False)
    show_solutions=st.checkbox("Afficher les solutions", True)
    max_solutions=st.number_input("Nombre max. de solutions",1,100000,10000)
    top_letters=st.text_input("Filtrer sur un top lettres (facultatif)", placeholder="ex. 10L")

source=st.segmented_control("Source", ["✍️ Manuel","🏆 Tournoi","📚 Liste","➕ Rajouts","🎲 Aléatoire"], default="✍️ Manuel")

if source=="✍️ Manuel":
    text=st.text_area("Un tirage par ligne",height=260,placeholder="SAPEKDUSOD\n1 10 8 7 9 25 / 203")
    if st.button("Charger les tirages",type="primary"):
        st.session_state.draws=parse_manual(text); st.session_state.source_info="Saisie manuelle"
elif source=="🏆 Tournoi":
    c1,c2=st.columns(2); city=c1.text_input("Ville (slug)","la-roche-sur-yon"); year=c2.text_input("Année","2026")
    url=st.text_input("URL de l'article (facultatif)",placeholder="https://clubdcdl.over-blog.com/2026/09/...")
    if st.button("Récupérer le tournoi",type="primary"):
        try:
            with st.spinner("Récupération des fichiers de tirages…"):
                st.session_state.draws,page=fetch_tournament(city,year,url)
                st.session_state.source_info=page
        except Exception as e: st.error(str(e))
elif source in ("📚 Liste","➕ Rajouts"):
    files=list_files(LISTS)
    rel=[str(p.relative_to(LISTS)) for p in files]
    selected=st.selectbox("Fichier",rel if rel else ["Aucun fichier"])
    selection_mode = st.radio(
        "Mode de sélection",
        ["Toute la liste", "Sélection aléatoire"],
        horizontal=True,
    )
    if selection_mode == "Sélection aléatoire":
        n = st.number_input("Nombre de tirages", 1, 1000, 200)
        seed = st.number_input("Seed (0 = aléatoire)", 0, 999999, 0)

    if st.button("Charger la liste", type="primary") and files:
        path = files[rel.index(selected)]
        draws = load_file(path, rajouts=(source == "➕ Rajouts"))
        if selection_mode == "Toute la liste":
            st.session_state.draws = draws
        else:
            st.session_state.draws = sample_draws(
                draws, min(n, len(draws)), None if seed == 0 else seed
            )
        st.session_state.source_info = selected
else:
    c1,c2,c3=st.columns(3); n=c1.number_input("Nombre de tirages",1,1000,100); ratio=c2.slider("Part de chiffres",0,100,25)/100; letters=c3.selectbox("Nombre de lettres",[9,10],index=1)
    required=st.text_input("Lettres obligatoires (facultatif)"); seed=st.number_input("Seed (0 = aléatoire)",0,999999,0,key="random_seed")
    if st.button("Générer les tirages",type="primary"):
        st.session_state.draws=generate_random(n,ratio,letters,required,None if seed==0 else seed); st.session_state.source_info="Génération aléatoire"

draws=st.session_state.draws
if draws:
    st.divider(); st.subheader(f"Prévisualisation — {len(draws)} tirages")
    edited=st.text_area("Tu peux corriger, supprimer, ajouter ou réordonner les tirages avant génération",value=draws_to_text(draws),height=300,key=f"preview_{len(draws)}_{st.session_state.source_info}")
    if st.button("Appliquer les modifications"):
        st.session_state.draws=parse_manual(edited); st.rerun()
    st.subheader("Solveur CLAX")
    st.caption("Calcule automatiquement le top, le nombre de solutions et les solutions via dcdl-laxou.fr.")
    if st.button("🧠 Résoudre avec CLAX", type="secondary"):
        try:
            with st.spinner(f"CLAX calcule {len(st.session_state.draws)} tirages…"):
                st.session_state.draws = solve_draws(st.session_state.draws)
            st.success("Résolution CLAX terminée.")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d’interroger CLAX : {e}")
            st.info("En local, vérifie que Google Chrome est installé. Le déploiement cloud demandera une adaptation du moteur CLAX pour ne plus dépendre d’un navigateur.")

    solved_count = sum(bool(d.best or d.solutions) for d in st.session_state.draws)
    if solved_count:
        st.caption(f"{solved_count}/{len(st.session_state.draws)} tirages enrichis par CLAX.")

    options=SheetOptions(sort_tiles=sort_tiles,max_solutions=int(max_solutions),letters_top=top_letters.strip(),show_solutions=show_solutions)
    pdf=generate_pdf(st.session_state.draws,options,ASSETS)
    st.download_button("📄 Télécharger le PDF",pdf,file_name=f"{name.strip() or 'feuille'}.pdf",mime="application/pdf",type="primary")
    st.caption("PDF A4 paysage, rendu manuscrit. Les tops et solutions CLAX sont inclus lorsqu’ils ont été calculés.")
else:
    st.info("Choisis une source et charge des tirages pour commencer.")
