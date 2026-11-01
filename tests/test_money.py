import pytest

from fproject.money import format_brl


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
