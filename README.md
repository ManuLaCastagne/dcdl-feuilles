# DCDL — Générateur de feuilles de jeu

Refactorisation Streamlit du script historique de génération de feuilles DCDL.

## Fonctionnalités V1

- saisie manuelle de tirages lettres/chiffres ;
- récupération des fichiers `.txt` d'un tournoi Club DCDL sans Selenium ;
- chargement des listes existantes et des rajouts ;
- génération aléatoire lettres/chiffres ;
- prévisualisation et correction avant export ;
- tri optionnel des plaques ;
- export PDF direct avec les plaques manuscrites, sans LibreOffice.

## Lancer en local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## GitHub

```bash
git init
git add .
git commit -m "Initial Streamlit DCDL sheet generator"
git branch -M main
git remote add origin <URL_DU_NOUVEAU_REPO>
git push -u origin main
```

Puis déployer `app.py` sur Streamlit Community Cloud.

## Architecture

- `app.py` : interface uniquement.
- `dcdl/models.py` : modèle `Draw` et options.
- `dcdl/parser.py` : parsing/nettoyage des entrées.
- `dcdl/randomizer.py` : sabots et génération aléatoire.
- `dcdl/lists.py` : banque de listes.
- `dcdl/tournaments.py` : récupération des tournois via HTTP/BeautifulSoup.
- `dcdl/pdf_generator.py` : rendu PDF direct.
- `assets/` : plaques manuscrites.
- `data/listes/` : listes historiques.

## Point restant : solveur Laxou

Le script historique pilote `dcdl-laxou.fr` avec Selenium/Chrome. Cette dépendance est volontairement découplée de la V1 afin que l'application soit déployable sur Streamlit Cloud sans ChromeDriver. La prochaine étape consiste à remplacer cette automatisation par un accès HTTP/JS compatible cloud, ou à isoler le solveur derrière un service adapté.

## V2 — rendu historique

- PDF A4 **paysage**.
- Aucun titre imprimé sur la feuille.
- Dimensions des plaques basées sur le DPI original des PNG, comme dans le générateur PowerPoint historique.
- Cible des comptes composée avec les chiffres manuscrits.
- Parser chiffres compatible avec `/`, `-`, `=` et les anciens fichiers sans séparateur explicite.
- Le solveur (tops et solutions) reste à intégrer dans une prochaine étape.
