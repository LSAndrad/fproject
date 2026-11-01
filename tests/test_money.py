import pytest

from fproject.money import format_brl, parse_brl


@pytest.mark.parametrize(
    ("cents", "expected"),
    [
        (0, "R$ 0,00"),
        (5, "R$ 0,05"),
        (1990, "R$ 19,90"),
        (123456, "R$ 1.234,56"),
        (100000000, "R$ 1.000.000,00"),
        (-1990, "-R$ 19,90"),
        (-123456, "-R$ 1.234,56"),
    ],
)
def test_format_brl(cents, expected):
    assert format_brl(cents) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("R$ 0,03", 3),
        ("R$ 2.345,67", 234567),
        ("-R$ 844,90", -84490),
        ("R$ -844,90", -84490),
        ("1.000.000,00", 100000000),
        ("  -12,50 ", -1250),
        ("1234,56", 123456),
    ],
)
def test_parse_brl(text, expected):
    assert parse_brl(text) == expected


@pytest.mark.parametrize("text", ["", "R$ 12", "12.50", "R$ 1,2", "--R$ 1,00", "-R$ -1,00", "abc"])
def test_parse_brl_rejects_malformed(text):
    with pytest.raises(ValueError):
        parse_brl(text)
