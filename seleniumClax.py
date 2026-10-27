import json
import time
import urllib.parse
import unicodedata
import re
import os
import random
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

def _build_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    return webdriver.Chrome(options=chrome_options)

dir_path = "data"
listes_path = dir_path + "/listes/"
listes_standards_path = dir_path + "/listes/Listes standards/"
mots_dissimules_path = dir_path + "/listes/Mots dissimulés/"

filepath_part = listes_standards_path + "L98.txt"
#tirages = open(filepath, "r").read()

def get_json_from_dcdl_laxou(input_text):

    """Automatise l'interaction avec dcdl-laxou.fr et retourne les résultats JSON."""
    # Imports selenium only when needed to avoid import-time stalls.
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    # Lancer Selenium avec les options
    driver = _build_driver()


    try:
        # Ouvrir la page cible
        driver.get("https://dcdl-laxou.fr/cl/solutions.html")

        # Attendre que la page charge complètement
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//textarea"))
        )

        # Trouver la textarea et insérer un texte
        try:
            textarea = driver.find_element(By.XPATH, "//textarea")
            textarea.clear()
            textarea.send_keys(input_text)
            time.sleep(1)
        except Exception as e:
            print(f"Erreur lors de l'insertion du texte : {e}")
            return None

        # Trouver et cliquer sur le bouton "Calculer"
        while True:
            try:
                bouton = driver.find_element(By.XPATH, "//button[contains(text(),'Calculer')]")
                bouton.click()
                break
            except Exception as e:
                print(f"Erreur lors du clic sur le bouton : {e}")
                return None

        # Attendre l'apparition du lien de téléchargement JSON
        while True:
            try:        
                lien_json = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//a[starts-with(@href, 'data:application/json')]"))
                )
                json_data_url = lien_json.get_attribute("href")
                break
            except Exception as e:
                if "Erreur à la ligne" in str(e):
                    ligne_erreur = int(str(e).split("Erreur à la ligne n°")[1].split("\xa0")[0])
                    input_text_lines = input_text.split("\n")
                    input_text_lines = [line for line in input_text_lines if line.strip() != ""]
                    if 0 <= ligne_erreur < len(input_text_lines):
                        del input_text_lines[ligne_erreur-1]
                        input_text = "\n".join(input_text_lines)
                    textarea = driver.find_element(By.XPATH, "//textarea")
                    textarea.clear()
                    textarea.send_keys(input_text)
                    bouton = driver.find_element(By.XPATH, "//button[contains(text(),'Calculer')]")
                    bouton.click()

        # Décoder le JSON depuis le lien data
        try:
            json_encoded = json_data_url.split(",", 1)[1]  # Récupère la partie encodée
            json_decoded = urllib.parse.unquote(json_encoded)  # Décodage
            json_obj = json.loads(json_decoded)  # Convertir en objet Python
        except Exception as e:
            print(f"Erreur lors du décodage du JSON : {e}")
            return None

        return json_obj  # Retourner le JSON sous forme de dict

    finally:
        driver.quit()  # Fermer le navigateur après exécution

def strip_accents(s: str) -> str:
    """Supprime les accents et caractères non ASCII, ne garde que A-Z."""
    s = unicodedata.normalize('NFD', s)
    s = s.encode('ascii', 'ignore').decode('utf-8')
    s = re.sub(r'[^A-Za-z]', '', s)
    return s.upper()

def get_tirages_from_cli_laxou(input_text: str):
    """
    Envoie chaque ligne de `input_text` à la CLI de dcdl-laxou.fr
    et retourne une liste de tirages nettoyés :
      - 1 tirage par mot,
      - tout en majuscules, sans accents ni signes.
    """

    # Imports selenium only when needed to avoid import-time stalls.
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = _build_driver()

    try:
        driver.get("https://dcdl-laxou.fr/cl/cli.html")

        # Attendre que la page soit chargée
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Trouver le champ et le bouton
        cmd_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "clax_cli_cmd"))
        )
        exec_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Exécuter']"))
        )

        tirages = []

        for mot in input_text.splitlines():
            mot = mot.strip()
            if not mot:
                continue

            # Nettoyer : supprimer accents, espaces, tirets, etc.
            mot_clean = strip_accents(mot)
            if not mot_clean:
                continue

            commande = f"motlong complete 10 {mot_clean}"
            print(f"→ Envoi : {commande}")

            # Compter les sorties existantes
            old_count = len(driver.find_elements(By.CSS_SELECTOR, ".cli.cli-stdout"))

            # Envoyer la commande
            cmd_input.clear()
            cmd_input.send_keys(commande)
            exec_button.click()

            # Attendre une nouvelle sortie
            WebDriverWait(driver, 1000).until(
                lambda d: len(d.find_elements(By.CSS_SELECTOR, ".cli.cli-stdout")) > old_count
            )

            # Lire la dernière sortie
            outputs = driver.find_elements(By.CSS_SELECTOR, ".cli.cli-stdout")
            raw_output = outputs[-1].text

            # Prendre uniquement la première ligne non vide
            lines = [l.strip() for l in raw_output.splitlines() if l.strip()]
            if not lines:
                tirages.append(mot_clean)
                continue

            first_line = lines[0]
            first_clean = strip_accents(first_line)

            # Si la ligne commence déjà par le mot → on la prend telle quelle
            if first_clean.startswith(mot_clean):
                tirage = first_clean
            else:
                tirage = mot_clean + first_clean

            print(f"→ Tirage obtenu : {tirage}")
            tirages.append(tirage)

            time.sleep(0.2)
        print(tirages)
        return tirages

    finally:
        driver.quit()

def creer_fichier_tirages(filepath: str):
    """
    Lit un fichier .txt de mots, envoie chaque mot à la CLI Laxou,
    et écrit les tirages obtenus dans un nouveau fichier *_caché.txt.
    """
    # Vérifier l’existence du fichier d’entrée
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Fichier introuvable : {filepath}")

    # Lire le contenu du fichier source
    with open(filepath, "r", encoding="utf-8") as f:
        contenu = f.read()

    # Obtenir les tirages via la fonction existante
    tirages = get_tirages_from_cli_laxou(contenu)

    # Construire le nom du fichier de sortie dans le dossier des mots dissimulés
    filename = os.path.basename(filepath)
    base, ext = os.path.splitext(filename)
    output_path = os.path.join(mots_dissimules_path, f"{base}_caché{ext}")

    # Créer le dossier cible si nécessaire
    os.makedirs(mots_dissimules_path, exist_ok=True)

    # Écrire les tirages (un par ligne)
    with open(output_path, "w", encoding="utf-8") as f:
        for t in tirages:
            f.write(t + "\n")

    print(f"✅ Tirages écrits dans : {output_path}")
    return output_path

def tirer_lignes_aleatoires(filepath, n=200, seed=None):
    """
    Tire n lignes aléatoires.

    - Si filepath contient Rajouts : conserve uniquement les lignes avec '='
      et ne les nettoie pas.
    - Sinon : nettoie les lignes classiques.
    """

    is_rajouts = "rajouts" in filepath.lower()

    def nettoyer(ligne):
        ligne = ligne.strip()

        if not ligne:
            return ""

        if is_rajouts:
            if "=" not in ligne:
                return ""
            return ligne

        # Enlève les annotations type (19), (08), (00)
        ligne = re.sub(r"\(\d+\)", "", ligne)

        # Enlève les marques *, #, ~
        ligne = ligne.replace("*", "").replace("#", "").replace("~", "")

        # Si format "tirage = solution", on garde la solution
        if " = " in ligne:
            ligne = ligne.split(" = ", 1)[1]

        # Cas œ / Œ
        ligne = ligne.replace("œ", "oe").replace("Œ", "OE")

        ligne = ligne.replace("-", "").replace("'", "").replace("(", "").replace(")", "")
        ligne = ligne.translate(str.maketrans(
            "éèêëàâäîïôöùûüçÉÈÊËÀÂÄÎÏÔÖÙÛÜÇ",
            "eeeeaaaiioouuucEEEEAAAIIOOUUUC"
        ))

        # Ne garde que les lettres
        ligne = "".join(c for c in ligne if c.isalpha())

        return ligne.upper().strip()
    
    lignes = []

    if os.path.isdir(filepath):
        for filename in os.listdir(filepath):
            if filename.endswith(".txt"):
                fullpath = os.path.join(filepath, filename)

                with open(fullpath, "r", encoding="utf-8") as f:
                    for line in f:
                        propre = nettoyer(line)
                        if propre:
                            lignes.append(propre)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                propre = nettoyer(line)
                if propre:
                    lignes.append(propre)

    if not lignes:
        raise ValueError("Aucune ligne valide trouvée")

    rng = random.Random(seed)

    if n > len(lignes):
        raise ValueError(f"Seulement {len(lignes)} lignes disponibles")

    tirage = rng.sample(lignes, n)

    return "\n".join(tirage)

creer_fichier_tirages(filepath_part)


