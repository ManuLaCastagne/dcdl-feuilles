from dcdl.models import DrawType
from dcdl.parser import parse_line


def test_numbers_slash():
    d = parse_line("1) 100 1 8 10 7 10 / 606")
    assert d and d.kind == DrawType.NUMBERS and d.target == 606


def test_numbers_dash():
    d = parse_line("100 1 8 10 7 10 - 606")
    assert d and d.kind == DrawType.NUMBERS and d.target == 606


def test_numbers_equals():
    d = parse_line("3. 100 1 8 10 7 10 = 606")
    assert d and d.kind == DrawType.NUMBERS and d.target == 606


def test_numbers_without_separator():
    d = parse_line("100 1 8 10 7 10 606")
    assert d and d.kind == DrawType.NUMBERS and d.target == 606


def test_letters():
    d = parse_line("2) NFTT AIEIEA".replace(" ", ""))
    assert d and d.kind == DrawType.LETTERS
