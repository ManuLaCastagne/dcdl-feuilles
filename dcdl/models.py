from dataclasses import dataclass, field
from enum import Enum

class DrawType(str, Enum):
    LETTERS = "Lettres"
    NUMBERS = "Chiffres"
    ADDITION = "Rajout"

@dataclass
class Draw:
    raw: str
    kind: DrawType
    elements: list[str] = field(default_factory=list)
    target: int | None = None
    best: str = ""
    solution_count: int = 0
    solutions: str = ""
    indication: str = ""

@dataclass
class SheetOptions:
    sort_tiles: bool = False
    max_solutions: int = 10000
    letters_top: str = ""
    show_solutions: bool = True
