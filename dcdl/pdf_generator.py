from io import BytesIO
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import DrawType, SheetOptions

# Géométrie reprise du générateur PowerPoint historique.
ROWS_PER_PAGE = 7
IN = 72.0
PAGE_SIZE = landscape(A4)


def _draw_image(c, path: Path, x_in: float, top_in: float, *, width_in=None, height_in=None, clean_plaque=False):
    """Dessine une image depuis le coin supérieur gauche.

    Pour les plaques manuscrites, ``clean_plaque`` rend transparents les pixels
    blancs / quasi blancs. Cela supprime le rectangle propre au fichier PNG et
    permet au cadre de rester parfaitement visible par-dessus les plaques.
    """
    if not path.exists():
        return
    page_w, page_h = PAGE_SIZE
    with Image.open(path) as source:
        im = source.convert("RGBA")
        px_w, px_h = im.size
        dpi_x, dpi_y = source.info.get("dpi", (330, 330))
        dpi_x = dpi_x or 330
        dpi_y = dpi_y or 330
        w = (width_in * IN) if width_in is not None else (px_w / dpi_x * IN)
        h = (height_in * IN) if height_in is not None else (px_h / dpi_y * IN)

        if clean_plaque:
            pixels = []
            for r, g, b, a in im.getdata():
                # Le papier/scanner des PNG est blanc ou gris très clair.
                # On ne conserve que l'écriture manuscrite.
                if min(r, g, b) >= 215:
                    pixels.append((r, g, b, 0))
                else:
                    pixels.append((r, g, b, a))
            im.putdata(pixels)

        image_buffer = BytesIO()
        im.save(image_buffer, format="PNG")
        image_buffer.seek(0)
        reader = ImageReader(image_buffer)
        x = x_in * IN
        y = page_h - (top_in * IN) - h
        c.drawImage(reader, x, y, width=w, height=h, mask="auto")


def _draw_target(c, numbers_dir: Path, target: int | None, left_in: float, top_in: float):
    if target is None:
        return
    # Même positionnement que l'ancien PPT : chiffres manuscrits de 0,22 x 0,38 po.
    x = left_in + 0.79
    for digit in str(target):
        _draw_image(c, numbers_dir / f"{digit}_1.png", x, top_in - 0.02,
                    width_in=0.22, height_in=0.38, clean_plaque=True)
        x += 0.12


def _draw_numbers(c, d, numbers_dir: Path, left_in: float, top_in: float, sort_tiles: bool):
    plaques = [int(v) for v in d.elements[:6]]
    if sort_tiles:
        plaques.sort()

    _draw_target(c, numbers_dir, d.target, left_in, top_in)

    # Valeurs reprises de tirage_chiffres() dans le script historique.
    ecart_c = 0.15
    ecart_ccc = 0.30
    x = left_in + 0.1 - 1.1 * ecart_ccc
    plaque_top = top_in + 0.40
    for plaque in plaques:
        x += 1.1 * ecart_ccc
        offset = 0.0
        if plaque < 10:
            offset = 0.0
        elif plaque < 100:
            offset = -ecart_c / 8.5
        else:
            offset = -ecart_c / 2
        _draw_image(c, numbers_dir / f"{plaque}_1.png", x + offset, plaque_top, clean_plaque=True)

    # Le cadre est volontairement dessiné EN DERNIER : ses traits passent au-dessus
    # des plaques, comme dans la feuille physique.
    _draw_image(c, numbers_dir / "cadre_2.png", left_in, top_in,
                width_in=2.05, height_in=0.70)


def _draw_letters(c, d, letters_dir: Path, left_in: float, top_in: float, sort_tiles: bool):
    chars = list(d.elements)
    consonants = [z for z in chars if z not in "AEIOUY"]
    vowels = [z for z in chars if z in "AEIOUY"]
    if sort_tiles:
        consonants.sort()
        vowels.sort()

    # Les PNG font physiquement ~0,32 po de large grâce à leur DPI 330.
    # On ne les redimensionne donc plus artificiellement.
    spacing = 0.32
    for row_top, seq in ((top_in, consonants), (top_in + 0.40, vowels)):
        x = left_in
        for letter in seq:
            _draw_image(c, letters_dir / f"{letter}_1.png", x, row_top, clean_plaque=True)
            x += spacing

    # Même principe que pour les chiffres : le cadre doit être la couche supérieure.
    _draw_image(c, letters_dir / "cadre.png", left_in, top_in,
                width_in=2.25, height_in=0.77)


def generate_pdf(draws, options: SheetOptions, assets: Path) -> bytes:
    buf = BytesIO()
    page_w, page_h = PAGE_SIZE
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    letters_dir = assets / "lettres"
    numbers_dir = assets / "chiffres"

    filtered = []
    for d in draws:
        if d.solution_count and d.solution_count > options.max_solutions and d.kind != DrawType.ADDITION:
            continue
        if options.letters_top and d.kind != DrawType.NUMBERS and d.best != options.letters_top:
            continue
        filtered.append(d)

    def start_page():
        # Aucun titre : on conserve uniquement la séparation historique avec les solutions.
        c.setLineWidth(0.5)
        x = 6.7 * IN
        c.line(x, 0, x, page_h)

    start_page()
    row = 0

    for d in filtered:
        if row >= ROWS_PER_PAGE:
            c.showPage()
            start_page()
            row = 0

        left = 0.10
        top = 0.10 + row * 1.00

        if d.kind == DrawType.NUMBERS:
            _draw_numbers(c, d, numbers_dir, left, top, options.sort_tiles)
            meta_top = top + 0.20
            solution_top = top + 0.20
        else:
            _draw_letters(c, d, letters_dir, left, top, options.sort_tiles)
            meta_top = top + 0.10
            solution_top = top + 0.10

        # Top / nombre de solutions, au même emplacement logique que l'ancien fichier.
        if d.best:
            c.setFont("Helvetica", 8)
            c.drawString(3.0 * IN, page_h - meta_top * IN - 8,
                         f"{d.best} ({d.solution_count})")

        if options.show_solutions and d.solutions:
            text = c.beginText(6.78 * IN, page_h - solution_top * IN - 7)
            text.setFont("Helvetica", 7)
            for line in str(d.solutions).splitlines()[:8]:
                text.textLine(line[:72])
            c.drawText(text)

        row += 1

    c.save()
    return buf.getvalue()
