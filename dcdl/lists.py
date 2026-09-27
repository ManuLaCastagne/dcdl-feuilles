from pathlib import Path
import random
from .parser import parse_manual, parse_rajouts

def list_files(root: Path):
    return sorted([p for p in root.rglob("*.txt") if p.is_file()], key=lambda p: str(p).lower())

def load_file(path: Path, rajouts=False):
    text=path.read_text(encoding="utf-8", errors="ignore")
    return parse_rajouts(text) if rajouts else parse_manual(text)

def sample_draws(draws, n, seed=None):
    if n >= len(draws): return draws.copy()
    return random.Random(seed).sample(draws, n)
