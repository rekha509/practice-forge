"""S4 (descoped, see docs/adr/0007) unit tests: the text-only
figure-dependency classifier is a pure function — these test its own
logic with small illustrative strings, not textbook accuracy claims."""

from __future__ import annotations

from practice_forge.figures.figures import classify_figure_dependency
from practice_forge.models.enums import FigureDependency


def test_no_figure_reference_is_none() -> None:
    text = "A resistor of 10 ohm carries a current of 2 A. Find the voltage drop."
    assert classify_figure_dependency(text) == FigureDependency.NONE


def test_explicit_figure_number_is_essential() -> None:
    text = "The beam shown in Fig. 5.3 carries a point load at midspan."
    assert classify_figure_dependency(text) == FigureDependency.ESSENTIAL


def test_shown_in_diagram_is_essential() -> None:
    text = "For the cycle shown in the diagram, determine the net work output."
    assert classify_figure_dependency(text) == FigureDependency.ESSENTIAL


def test_as_shown_is_essential() -> None:
    text = "As shown, the piston moves from state 1 to state 2."
    assert classify_figure_dependency(text) == FigureDependency.ESSENTIAL


def test_refers_to_figure_is_essential() -> None:
    text = "This problem refers to the figure for the pipe network layout."
    assert classify_figure_dependency(text) == FigureDependency.ESSENTIAL


def test_case_insensitive() -> None:
    text = "SHOWN IN FIGURE 2, determine the pressure."
    assert classify_figure_dependency(text) == FigureDependency.ESSENTIAL
