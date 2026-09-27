"""Pont vers le solveur CLAX de dcdl-laxou.fr.

La V5 reprend le mécanisme éprouvé de l'ancien seleniumClax.py, mais sans
chemin macOS codé en dur. Selenium Manager choisit le navigateur/driver.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import replace
from typing import Iterable

from .models import Draw, DrawType

import os
import shutil

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

CLAX_URL = "https://dcdl-laxou.fr/cl/solutions.html"


def create_driver():

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

        from selenium.webdriver.chrome.service import Service

        return webdriver.Chrome(

            service=Service(driver_path),

            options=options,

        )

    return webdriver.Chrome(options=options)


def _draw_to_clax_line(draw: Draw) -> str:
    if draw.kind == DrawType.NUMBERS:
        return f"{' '.join(draw.elements[:6])} / {draw.target}"
    return "".join(draw.elements)


def _fetch_clax_json(input_text: str) -> dict:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = _build_driver()
    try:
        driver.get(CLAX_URL)
        wait = WebDriverWait(driver, 30)
        textarea = wait.until(EC.presence_of_element_located((By.XPATH, "//textarea")))
        textarea.clear()
        textarea.send_keys(input_text)
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(.,'Calculer')]")))
        button.click()
        link = wait.until(EC.presence_of_element_located((By.XPATH, "//a[starts-with(@href,'data:application/json')]")))
        href = link.get_attribute("href")
        payload = href.split(",", 1)[1]
        return json.loads(urllib.parse.unquote(payload))
    finally:
        driver.quit()


def _letters_result(payload: dict) -> tuple[str, int, str]:
    lengths = []
    for key, words in payload.items():
        m = re.fullmatch(r"(\d+)L", str(key))
        if m and words:
            lengths.append((int(m.group(1)), list(words)))
    if not lengths:
        return "", 0, ""
    lengths.sort(reverse=True)
    top_len, top_words = lengths[0]
    second = lengths[1] if len(lengths) > 1 else None
    lines = [f"{top_len}L: " + ", ".join(map(str, top_words))]
    if second:
        lines.append(f"{second[0]}L: " + ", ".join(map(str, second[1])))
    return f"{top_len}L", len(top_words), "\n".join(lines)


def _numbers_result(payload: dict) -> tuple[str, int, str]:
    best = payload.get("best", "")
    if best == 0:
        label = "CB"
    elif best in ("", None):
        label = ""
    else:
        label = f"Approche à {best}"
    solutions = payload.get("solutions", "")
    if isinstance(solutions, list):
        solutions_text = "\n".join(map(str, solutions))
    else:
        solutions_text = str(solutions or "")
    try:
        count = int(payload.get("number", 0) or 0)
    except (TypeError, ValueError):
        count = 0
    return label, count, solutions_text


def solve_draws(draws: Iterable[Draw]) -> list[Draw]:
    """Enrichit les tirages avec top, nombre de solutions et solutions CLAX."""
    source = list(draws)
    if not source:
        return []
    lines = [_draw_to_clax_line(d) for d in source]
    data = _fetch_clax_json("\n".join(lines))
    values = list(data.values())

    # CLAX renvoie normalement un dictionnaire dans l'ordre des lignes envoyées.
    # On préfère une correspondance par clé, avec repli par position.
    solved = []
    for idx, draw in enumerate(source):
        line = lines[idx]
        candidates = [line, line.replace(" ", ""), draw.raw, "".join(draw.elements)]
        payload = None
        for key in candidates:
            if key in data:
                payload = data[key]
                break
        if payload is None and idx < len(values):
            payload = values[idx]
        if not isinstance(payload, dict):
            solved.append(draw)
            continue
        if draw.kind == DrawType.NUMBERS:
            best, count, solutions = _numbers_result(payload)
        else:
            best, count, solutions = _letters_result(payload)
        solved.append(replace(draw, best=best, solution_count=count, solutions=solutions))
    return solved
