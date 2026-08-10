"""Parses real, messy free-text numeric answers into (value, unit) pairs,
and compares them against a solver's own SI-base-unit result within a
relative tolerance.

Two real sources feed this: a book's own printed `final_answer` (OCR'd,
inconsistently formatted — see calibration.py) and an independent model's
blind re-solve (see blind_resolve.py, format constrained by that stage's
own prompt so it's cleaner, but still free text). Both go through the
same parser and comparison logic here, not two separate ad hoc ones.

Real observed messiness this parser is built against (see
`tests/test_answer_parsing.py` for the actual strings, pulled from this
book's real `final_answer` column, not invented): comma thousands
separators ("24,400 kW"), "x 10^N" scientific notation ("1.27 x 10^5
kJ"), a space after a minus sign ("- 34.6 MJ"), (a)/(b)-style labels,
"name = value" labels, multiple values sharing one trailing unit
("0.718, 1.005 kJ/kg K"), and purely qualitative answers with no number
at all ("Flow is from right to left"). The parser extracts what it can
and returns None only when NOTHING numeric is found — a partial parse
returns the values it found, and callers must decide whether a partial
parse is usable, not have that decided for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = re.compile(
    r"(?P<sign>[+-])?\s*"
    # Comma-grouped form requires an ACTUAL comma group ("24,400"); a plain
    # run of digits with no comma ("1308", "2016") must fall through to the
    # bare `\d+` branch, or `\d{1,3}` alone would greedily cap it at 3
    # digits and strand the rest to be re-matched as a bogus second number.
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?P<frac>\.\d+)?"
    r"(?:\s*[x×]\s*10\s*\^?\s*(?P<sci_exp>[+-]?\d+)"
    r"|\^(?P<bare_exp>[+-]?\d+))?"
    r"(?:[eE](?P<e_exp>[+-]?\d+))?"
)
# A short run of unit-like characters immediately following a number —
# deliberately excludes bare letters that are clearly a NEXT label (e.g.
# "(b)") by requiring the run not start with a lone "(". Deliberately
# INCLUDES digits (e.g. "cm^2", "m/s2") so that a digit inside a unit's
# exponent is consumed as part of the unit span, not left for the next
# search step to re-match as a bogus standalone number.
_UNIT = re.compile(r"[A-Za-z°%/][A-Za-z0-9°%/.\^\-]*")


@dataclass(frozen=True)
class ParsedValue:
    value: float
    unit: str  # "" if no unit was found immediately after the number


def parse_numeric_values(text: str) -> list[ParsedValue] | None:
    """Extracts every numeric value (with its immediately-following unit,
    if any) from free text, in the order they appear. Returns None only
    if no number at all was found (a qualitative answer like "Reversible"
    or "Flow is from right to left") — never an empty list, which would
    read as "zero real values" rather than "nothing parseable".

    Deliberately NOT a `finditer` scan: after each number+unit is matched,
    the cursor is advanced past the CONSUMED UNIT too, not just the number.
    A `finditer` over the raw text independently re-scans unit text for
    more digits (e.g. the "2" in "cm^2/s") and reports it as a bogus
    second value — this manual cursor avoids that by construction.

    Known, disclosed (not fixed) limitations, both rare in this book's
    real data and unsafe to special-case without risking new false
    positives elsewhere: (1) symbolic/formula answers with no real numeric
    answer (e.g. "sqrt(2) * sigma * n * [8*K*T/(pi*m)]^(1/2)") still yield
    spurious numbers pulled from the formula's own literals — callers
    comparing these against a solver's numeric result will see them as
    mismatches, which is the practically-correct outcome even though the
    root cause is "not a numeric answer" rather than "wrong answer"; (2)
    dash-joined state-point labels using this book's own indexing notation
    (e.g. "U1-1 = 1.629 kJ", "Vr-z = 0.012 m3") can have the label's own
    digits misread as a signed number ("1-1" as "1" then "-1") — the
    labeled VALUE after "=" still parses correctly, just with extra bogus
    values mixed in from the label itself.
    """
    values: list[ParsedValue] = []
    pos = 0
    while True:
        m = _NUMBER.search(text, pos)
        if m is None:
            break
        int_part = m.group("int").replace(",", "")
        frac_part = m.group("frac") or ""
        try:
            value = float(int_part + frac_part)
        except ValueError:
            pos = m.end()
            continue
        if m.group("sign") == "-":
            value = -value

        bare_exp = m.group("bare_exp")
        exp = m.group("sci_exp") or m.group("e_exp")
        if bare_exp is not None and int_part + frac_part == "10":
            # Bare "10^N" (no leading coefficient, e.g. "(e) 10^4") means
            # 10 raised to N, not a coefficient times 10^N.
            try:
                value = 10.0 ** int(bare_exp)
            except ValueError:
                pass
        elif exp is not None:
            try:
                value *= 10.0 ** int(exp)
            except ValueError:
                pass

        end = m.end()
        rest = text[end:]
        stripped_rest = rest.lstrip()
        skipped = len(rest) - len(stripped_rest)
        unit_match = _UNIT.match(stripped_rest)
        if unit_match:
            unit = unit_match.group(0).strip()
            end = end + skipped + unit_match.end()
        else:
            unit = ""
        values.append(ParsedValue(value=value, unit=unit))
        pos = end

    if not values:
        return None

    # Multiple values can share one trailing unit ("0.718, 1.005 kJ/kg K"):
    # backfill each unit-less value from the next value that HAS one, so
    # every value in such a group compares at the correct scale instead of
    # being treated as unitless.
    backfilled: list[ParsedValue] = []
    trailing_unit = ""
    for v in reversed(values):
        if v.unit:
            trailing_unit = v.unit
            backfilled.append(v)
        else:
            backfilled.append(ParsedValue(value=v.value, unit=trailing_unit))
    backfilled.reverse()
    return backfilled


# (normalized_unit -> (multiply, add)) such that si_value = raw*multiply + add.
# Deliberately covers only the unit families actually observed in this
# book's real content (see module docstring) — an unrecognized unit is
# reported as such, not silently guessed at.
_UNIT_CONVERSIONS: dict[str, tuple[float, float]] = {
    "j": (1.0, 0.0), "kj": (1000.0, 0.0), "mj": (1e6, 0.0),
    "w": (1.0, 0.0), "kw": (1000.0, 0.0), "mw": (1e6, 0.0),
    "pa": (1.0, 0.0), "kpa": (1000.0, 0.0), "mpa": (1e6, 0.0), "bar": (1e5, 0.0),
    "kg": (1.0, 0.0), "g": (0.001, 0.0),
    "k": (1.0, 0.0), "c": (1.0, 273.15), "°c": (1.0, 273.15),
    "kwh": (3_600_000.0, 0.0),
    "%": (0.01, 0.0),
    "": (1.0, 0.0),
}


def _normalize_unit(unit: str) -> str:
    # Strip anything after a "/" or inside "()" for the purposes of family
    # lookup (e.g. "kJ/kg" and "kJ/kg K" both key on "kj" as the leading
    # magnitude unit) — a real simplification: this cannot distinguish
    # "kJ/kg" from "kJ" for comparison purposes, only their SCALE, so a
    # per-mass vs. absolute mismatch would not be caught by this alone.
    stripped = re.split(r"[/(\s]", unit.strip())[0]
    return stripped.lower().replace(".", "")


def to_si(value: float, unit: str) -> tuple[float, bool]:
    """Converts `value` (given in `unit`) toward SI-base scale for
    comparison against a solver's raw SI-base output. Returns
    (converted_value, recognized) — `recognized=False` means the unit
    wasn't in the known table and `converted_value` is just the raw input,
    unconverted; callers must surface that, not treat the comparison as
    trustworthy when it fires."""
    key = _normalize_unit(unit)
    if key not in _UNIT_CONVERSIONS:
        return value, False
    mult, add = _UNIT_CONVERSIONS[key]
    return value * mult + add, True


@dataclass(frozen=True)
class ComparisonResult:
    matched: bool
    relative_difference: float | None  # None if not comparable (e.g. zero reference with nonzero diff)
    unit_recognized: bool


def compare_values(solver_si_value: float, reference_value: float, reference_unit: str, tol: float = 0.01) -> ComparisonResult:
    """Compares a solver's own SI-base-unit output against a reference
    value+unit (from a book answer or an independent re-solve), within
    relative tolerance `tol` (1% by default, per the calibration spec)."""
    converted, recognized = to_si(reference_value, reference_unit)
    diff = abs(solver_si_value - converted)
    if converted == 0:
        return ComparisonResult(matched=diff < 1e-6, relative_difference=None, unit_recognized=recognized)
    rel_diff = diff / abs(converted)
    return ComparisonResult(matched=rel_diff <= tol, relative_difference=rel_diff, unit_recognized=recognized)
