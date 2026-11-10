import re
import unicodedata
from .models import Draw, DrawType


def normalize_letters(s: str) -> str:
    s = s.replace("œ", "oe").replace("Œ", "OE")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return "".join(c for c in s.upper() if c.isalpha())


def _strip_numbering(line: str) -> str:
    # Accepte 1) ..., 1. ..., 1 - ...
    return re.sub(r"^\s*\d+\s*(?:\)|\.|-)\s*", "", line.strip())


def parse_line(line: str) -> Draw | None:
    original = line.strip()
    if not original:
        return None

    brut = original.replace("\xa0", " ")
    compte = r"(\d+(?:(?:\s+|\s*-\s*)\d+){5})\s*[/=:\-]\s*(\d{3})"

    # Essaie d'abord la ligne brute : « 7- » peut être la première plaque.
    m = re.fullmatch(compte, brut)
    line = _strip_numbering(brut)

    if not m:
        m = re.fullmatch(compte, line)
    if not m:
        # Anciens fichiers avec un espace entre la dernière plaque et la cible.
        m = re.fullmatch(r"(\d+(?:\s+\d+){5})\s+(\d{3})", line)
    if m:
        plaques = re.findall(r"\d+", m.group(1))
        return Draw(original, DrawType.NUMBERS, plaques, int(m.group(2)))

    candidate = line.split(" = ", 1)[-1] if " = " in line else line
    letters = normalize_letters(candidate)
    if 9 <= len(letters) <= 11:
        return Draw(original, DrawType.LETTERS, list(letters))
    return None


def parse_manual(text: str) -> list[Draw]:
    return [d for line in text.splitlines() if (d := parse_line(line))]


def parse_rajouts(text: str) -> list[Draw]:
    out = []
    for line in text.splitlines():
        if "=" not in line:
            continue
        left, right = [x.strip() for x in line.split("=", 1)]
        letters = normalize_letters(right)
        if letters:
            out.append(Draw(line.strip(), DrawType.ADDITION, list(letters), best=left,
                            solution_count=len(letters), solutions=right, indication=left))
    return out


def draws_to_text(draws: list[Draw]) -> str:
    lines = []
    for d in draws:
        if d.kind == DrawType.NUMBERS:
            lines.append(f"{' '.join(d.elements)} / {d.target}")
        else:
            lines.append("".join(d.elements))
    return "\n".join(lines)
