"""
Tests for printout wording shared by analysis scripts.
"""

# Local package imports
from report_text import counted


def test_counted_one_is_singular() -> None:
    assert counted(1, "website") == "1 website"


def test_counted_many_is_plural() -> None:
    assert counted(3, "website") == "3 websites"


def test_counted_zero_is_plural() -> None:
    assert counted(0, "website") == "0 websites"
