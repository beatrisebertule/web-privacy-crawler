"""
Tests for the axis titles on Q1's box plots.

Assignment wants both axes titled on every plot.
"""

# Standard library imports
import importlib

# Third party imports
import pytest
from matplotlib.figure import Figure

# Local package imports
# Import statement can't load a module name starting with a digit.
q1 = importlib.import_module("01_analysis")


def draw(data_by_mode: dict[str, list[int]], metric_label: str):
    ax = Figure().add_subplot()
    q1.boxplot(ax, data_by_mode, metric_label)
    return ax


@pytest.mark.parametrize("metric_label", list(q1.METRICS.values()))
def test_boxplot_titles_both_axes(metric_label: str) -> None:
    ax = draw({mode: [1, 2, 3] for mode in q1.MODES}, metric_label)
    # Literal on purpose. Test fails if the label Q1 and Q3 share changes.
    assert ax.get_xlabel() == "Crawl Type"
    assert ax.get_ylabel() == metric_label


def test_boxplot_titles_axes_with_an_empty_crawl() -> None:
    data = {mode: [1, 2, 3] for mode in q1.MODES if mode != "ignore"}
    ax = draw(data, "Number of requests per website")
    assert ax.get_xlabel() == "Crawl Type"
    assert ax.get_ylabel() == "Number of requests per website"
    ticks = [tick.get_text() for tick in ax.get_xticklabels()]
    assert ticks[-1] == "Ignore\n(n=0)"
