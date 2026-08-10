"""Tests for the calibration/blind-resolve answer parser. Every string here
(except where noted) is pulled verbatim from this book's real, OCR'd
`final_answer` column (book_id 4d97664c-50ee-4c77-83b8-7951efae4d60) — not
invented — and several are direct regressions for real bugs found by
running the parser against all 243 real non-null `final_answer` rows:
a digit-group cap that split plain 4+-digit numbers in two ("1308" ->
130 + 8), a unit's own digit (e.g. "cm^2") being re-matched as a bogus
second value, and bare "10^N" splitting into two tokens instead of one."""

from __future__ import annotations

import math

from practice_forge.verification.answer_parsing import (
    ParsedValue,
    compare_values,
    parse_numeric_values,
    to_si,
)


def test_plain_multidigit_number_without_commas_is_one_value() -> None:
    # Regression: `\d{1,3}` alone capped this at "130" + a stray "8 kW".
    assert parse_numeric_values("1308 kW") == [ParsedValue(1308.0, "kW")]
    assert parse_numeric_values("2016") == [ParsedValue(2016.0, "")]


def test_comma_thousands_separator() -> None:
    assert parse_numeric_values("24,400 kW") == [ParsedValue(24400.0, "kW")]


def test_scientific_notation_with_coefficient() -> None:
    assert parse_numeric_values("1.27 x 10^5 kJ") == [ParsedValue(127000.0, "kJ")]


def test_bare_power_of_ten_is_one_value_not_two() -> None:
    # Regression: "10^4" used to split into ParsedValue(10.0) + ParsedValue(4.0).
    result = parse_numeric_values("(e) 10^4")
    assert result == [ParsedValue(10000.0, "")]


def test_unit_with_embedded_digit_is_not_double_counted() -> None:
    # Regression: the "2" in "cm^2" used to re-match as a bogus second value.
    assert parse_numeric_values("0.139 cm^2/s") == [ParsedValue(0.139, "cm^2/s")]
    assert parse_numeric_values("1.13 g/m^2 s") == [ParsedValue(1.13, "g/m^2")]
    result = parse_numeric_values("2.845 x 10^21 collisions/m^2s")
    assert result is not None
    assert len(result) == 1
    assert math.isclose(result[0].value, 2.845e21, rel_tol=1e-9)
    assert result[0].unit == "collisions/m^2s"


def test_multiple_values_sharing_one_trailing_unit() -> None:
    # The unit trails the whole comma-separated group in the book's own
    # notation; the earlier, unit-less value backfills it from the later
    # one so both compare at the correct scale.
    result = parse_numeric_values("0.718, 1.005 kJ/kg K")
    assert result == [ParsedValue(0.718, "kJ/kg"), ParsedValue(1.005, "kJ/kg")]


def test_space_after_minus_sign() -> None:
    assert parse_numeric_values("- 34.6 MJ") == [ParsedValue(-34.6, "MJ")]


def test_ans_prefix_label() -> None:
    assert parse_numeric_values("Ans. 45.6 kJ/kg") == [ParsedValue(45.6, "kJ/kg")]


def test_lettered_sub_answers() -> None:
    result = parse_numeric_values("(a) 1.87 x 10^-10 m, (c) 340 m/s, (e) 10^4")
    assert result is not None
    assert len(result) == 3
    assert math.isclose(result[0].value, 1.87e-10, rel_tol=1e-9)
    assert result[0].unit == "m"
    assert result[1] == ParsedValue(340.0, "m/s")
    assert result[2] == ParsedValue(10000.0, "")


def test_purely_qualitative_answer_returns_none() -> None:
    assert parse_numeric_values("Flow is from right to left") is None
    assert parse_numeric_values("Reversible, (b) Impossible, (c) Irreversible") is None
    assert parse_numeric_values("Yes, the device can operate as described") is None


def test_known_limitation_symbolic_formula_yields_spurious_values() -> None:
    # Disclosed, accepted limitation (see module docstring): a symbolic
    # answer with no real number still yields spurious values pulled from
    # its own literals. Documented here so a change in this behavior is a
    # deliberate decision, not an unnoticed regression.
    result = parse_numeric_values("sqrt(2) * sigma * n * [8 * K * T / (pi * m)]^(1/2)")
    assert result is not None
    assert [v.value for v in result] == [2.0, 8.0, 1.0]


def test_known_limitation_dash_joined_state_label_yields_spurious_values() -> None:
    # Disclosed, accepted limitation: "U1-1" (this book's own state-point
    # label notation) is misread as "1" then "-1". The labeled VALUE after
    # "=" still parses correctly alongside the bogus label-derived values.
    result = parse_numeric_values("U1-1 = 1.629 kJ, Pr = 1.35 bar")
    assert result is not None
    values = [v.value for v in result]
    assert 1.629 in values
    assert 1.35 in values


def test_to_si_conversions() -> None:
    assert to_si(45.6, "kJ/kg") == (45600.0, True)
    assert to_si(1.35, "bar") == (135000.0, True)
    celsius, recognized = to_si(20.0, "C")
    assert recognized
    assert math.isclose(celsius, 293.15)
    unrecognized_value, recognized = to_si(5.0, "furlongs")
    assert not recognized
    assert unrecognized_value == 5.0


def test_compare_values_within_tolerance() -> None:
    result = compare_values(solver_si_value=45601.0, reference_value=45.6, reference_unit="kJ/kg")
    assert result.matched
    assert result.unit_recognized
    assert result.relative_difference is not None
    assert result.relative_difference < 0.01


def test_compare_values_outside_tolerance() -> None:
    result = compare_values(solver_si_value=50000.0, reference_value=45.6, reference_unit="kJ/kg")
    assert not result.matched


def test_compare_values_unrecognized_unit_still_compares_but_flags_it() -> None:
    result = compare_values(solver_si_value=5.0, reference_value=5.0, reference_unit="furlongs")
    assert not result.unit_recognized
