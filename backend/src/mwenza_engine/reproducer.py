"""The Reproducer's checks (phase H1): recompute reported statistics and sample-size claims.

``check_reported_statistics`` finds APA-style results in a text (t, F, chi-square, r and z with their p-values),
recomputes each p-value from the test statistic and degrees of freedom, and compares, allowing for rounding the way
statcheck does: a reported p is consistent if any value of the statistic that rounds to the reported one gives a p
that rounds to the reported p. An inconsistency that flips significance at .05 is a decision error.

``check_sample_size`` recomputes a sample-size calculation for the designs postgraduate proposals use most: a single
proportion (Cochran, with finite-population correction, design effect and non-response), two proportions, two means
and a correlation. It shows each step so the student can see where their number differs.

Standard library only (``statistics.NormalDist`` and the incomplete beta and gamma functions below), so it runs in
the engine without SciPy. Accuracy is checked against SciPy and statsmodels reference values in the tests.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from statistics import NormalDist
from typing import Any

NORMAL = NormalDist()
ALPHA = 0.05


# --- Distributions ---------------------------------------------------------------------------------------------


def _beta_fraction(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        for numerator in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def upper_gamma(s: float, x: float) -> float:
    """Regularised upper incomplete gamma Q(s, x)."""
    if x <= 0.0:
        return 1.0
    log_front = s * math.log(x) - x - math.lgamma(s)
    if x < s + 1.0:  # series for P, then Q = 1 - P
        term = total = 1.0 / s
        n = s
        for _ in range(1000):
            n += 1.0
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-16:
                break
        return 1.0 - total * math.exp(log_front)
    tiny = 1e-300  # continued fraction for Q
    b, c, d = x + 1.0 - s, 1.0 / tiny, 1.0 / (x + 1.0 - s)
    h = d
    for i in range(1, 1000):
        an = -i * (i - s)
        b += 2.0
        d = an * d + b
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = b + an / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return math.exp(log_front) * h


def p_t(t: float, df: float) -> float:
    """Two-tailed p for Student's t."""
    return incomplete_beta(df / 2.0, 0.5, df / (df + t * t))


def p_f(f: float, df1: float, df2: float) -> float:
    return incomplete_beta(df2 / 2.0, df1 / 2.0, df2 / (df2 + df1 * f)) if f > 0 else 1.0


def p_chi2(x: float, df: float) -> float:
    return upper_gamma(df / 2.0, x / 2.0)


def p_z(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def p_r(r: float, df: float) -> float:
    if abs(r) >= 1.0:
        return 0.0
    return p_t(r * math.sqrt(df / (1.0 - r * r)), df)


# --- Reported statistics -----------------------------------------------------------------------------------------

NUMBER = r"-?\d*\.?\d+"
P_PART = r"\s*,\s*(?:ns\s*,\s*)?p\s*(?P<op>[<>=≤≥])\s*(?P<p>0?\.\d+|1(?:\.0+)?|0)"
PATTERNS = {
    "t": re.compile(rf"\bt\s*\(\s*(?P<df1>\d+(?:\.\d+)?)\s*\)\s*=\s*(?P<value>{NUMBER}){P_PART}", re.IGNORECASE),
    "F": re.compile(rf"\bF\s*\(\s*(?P<df1>\d+(?:\.\d+)?)\s*,\s*(?P<df2>\d+(?:\.\d+)?)\s*\)\s*=\s*(?P<value>{NUMBER}){P_PART}"),
    "chi2": re.compile(rf"(?:χ\s*2|χ²|X\s*2|chi[- ]?square[d]?)\s*\(\s*(?P<df1>\d+(?:\.\d+)?)(?:\s*,\s*N\s*=\s*\d+)?\s*\)\s*=\s*(?P<value>{NUMBER}){P_PART}", re.IGNORECASE),
    "r": re.compile(rf"\br\s*\(\s*(?P<df1>\d+)\s*\)\s*=\s*(?P<value>-?\.?\d*\.?\d+){P_PART}"),
    "z": re.compile(rf"\bz\s*=\s*(?P<value>{NUMBER}){P_PART}", re.IGNORECASE),
}
TEACH = {
    "consistent": "",
    "inconsistent": "The p-value does not follow from the test statistic and degrees of freedom you report. One of the three is probably mistyped or copied from a different test; recompute it from your output before anyone else does.",
    "decision-error": "The recomputed p-value falls on the other side of .05 from the one you report, so the conclusion about significance may be wrong. Check this result first: it changes what you can claim.",
}


@dataclass
class StatisticCheck:
    text: str
    test: str
    df: tuple[float, ...]
    value: float
    reported: str
    computed_p: float
    verdict: str
    start: int
    end: int
    note: str = ""
    teach: str = ""


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _p_of(test: str, value: float, df: tuple[float, ...]) -> float:
    if test == "t":
        return p_t(value, df[0])
    if test == "F":
        return p_f(value, df[0], df[1])
    if test == "chi2":
        return p_chi2(value, df[0])
    if test == "r":
        return p_r(value, df[0])
    return p_z(value)


def _p_range(test: str, raw_value: str, df: tuple[float, ...]) -> tuple[float, float]:
    """Smallest and largest p over every statistic that rounds to the reported one."""
    value, half = abs(float(raw_value)), 0.5 * 10 ** -_decimals(raw_value)
    low, high = max(value - half, 0.0), value + half
    if test == "r":
        high = min(high, 0.999999)
    ps = (_p_of(test, low, df), _p_of(test, high, df))
    return min(ps), max(ps)


def _consistent(op: str, reported: float, decimals: int, p_low: float, p_high: float) -> bool:
    if op in "<≤":
        return p_low < reported or (op == "≤" and p_low <= reported)
    if op in ">≥":
        return p_high > reported or (op == "≥" and p_high >= reported)
    half = 0.5 * 10 ** -decimals
    return p_low < reported + half and p_high >= reported - half


def _significant(op: str, reported: float) -> bool | None:
    if op in "<≤":
        return True if reported <= ALPHA else None
    if op in ">≥":
        return False if reported >= ALPHA else None
    return reported < ALPHA


def check_reported_statistics(text: str) -> dict[str, Any]:
    """Every APA-style result in ``text`` with its recomputed p-value and a verdict."""
    checks: list[StatisticCheck] = []
    taken: list[tuple[int, int]] = []
    for test, pattern in PATTERNS.items():
        for match in pattern.finditer(text.replace("−", "-")):
            if any(start <= match.start() < end for start, end in taken):
                continue
            taken.append((match.start(), match.end()))
            df = tuple(float(match.group(name)) for name in ("df1", "df2") if name in pattern.groupindex and match.group(name))
            raw, op, p_text = match.group("value"), match.group("op"), match.group("p")
            reported = float(p_text)
            p_low, p_high = _p_range(test, raw, df)
            computed = _p_of(test, float(raw), df)
            if _consistent(op, reported, _decimals(p_text), p_low, p_high):
                verdict, note = "consistent", ""
            else:
                claimed, actual = _significant(op, reported), computed < ALPHA
                verdict = "decision-error" if claimed is not None and claimed != actual else "inconsistent"
                note = "Consistent with a one-tailed test: if that was intended, say so and justify it." if test in ("t", "z") and _consistent(op, reported, _decimals(p_text), p_low / 2, p_high / 2) else ""
            checks.append(StatisticCheck(match.group(0), test, df, float(raw), f"p {op} {p_text}", round(computed, 6), verdict, match.start(), match.end(), note, TEACH[verdict]))
    checks.sort(key=lambda check: check.start)
    counts = {verdict: sum(check.verdict == verdict for check in checks) for verdict in TEACH}
    status = "none-found" if not checks else "decision-errors" if counts["decision-error"] else "inconsistencies" if counts["inconsistent"] else "consistent"
    return {"status": status, "counts": counts, "results": [asdict(check) for check in checks]}


# --- Sample size -------------------------------------------------------------------------------------------------


def z_of(probability: float) -> float:
    return NORMAL.inv_cdf(probability)


@dataclass
class SampleSizeCheck:
    design: str
    computed_n: int
    unit: str
    reported_n: int | None
    verdict: str
    steps: list[str] = field(default_factory=list)
    achieved_power: float | None = None
    teach: str = ""


def _ceil(value: float) -> int:
    return math.ceil(value - 1e-9)


def proportion_n(p: float, margin: float, confidence: float = 0.95, population: int | None = None, design_effect: float = 1.0, nonresponse: float = 0.0) -> tuple[int, list[str]]:
    z = z_of(1 - (1 - confidence) / 2)
    n0 = z * z * p * (1 - p) / (margin * margin)
    steps = [f"Cochran: n0 = z² p(1-p) / e² = {z:.3f}² x {p:g} x {1 - p:g} / {margin:g}² = {n0:.1f}"]
    n = n0
    if population:
        n = n0 / (1 + (n0 - 1) / population)
        steps.append(f"Finite population correction (N = {population}): n = n0 / (1 + (n0 - 1)/N) = {n:.1f}")
    if design_effect != 1.0:
        n *= design_effect
        steps.append(f"Design effect {design_effect:g}: n = {n:.1f}")
    if nonresponse:
        n /= 1 - nonresponse
        steps.append(f"Non-response {nonresponse:.0%}: n / (1 - {nonresponse:g}) = {n:.1f}")
    steps.append(f"Round up: {_ceil(n)}")
    return _ceil(n), steps


def two_proportions_n(p1: float, p2: float, alpha: float = ALPHA, power: float = 0.8, two_sided: bool = True) -> tuple[int, list[str]]:
    za, zb = z_of(1 - alpha / (2 if two_sided else 1)), z_of(power)
    pbar = (p1 + p2) / 2
    n = (za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 / (p1 - p2) ** 2
    return _ceil(n), [
        f"z for alpha = {alpha:g} ({'two' if two_sided else 'one'}-sided): {za:.3f}; z for power {power:g}: {zb:.3f}",
        f"Pooled proportion p = ({p1:g} + {p2:g}) / 2 = {pbar:.3f}",
        f"n per group = (z_a sqrt(2 p(1-p)) + z_b sqrt(p1 q1 + p2 q2))² / (p1 - p2)² = {n:.1f}",
        f"Round up: {_ceil(n)} per group",
    ]


def two_means_n(difference: float, sd: float, alpha: float = ALPHA, power: float = 0.8, two_sided: bool = True) -> tuple[int, list[str]]:
    za, zb = z_of(1 - alpha / (2 if two_sided else 1)), z_of(power)
    d = abs(difference) / sd
    n_normal = 2 * (za + zb) ** 2 / (d * d)
    n = n_normal + za * za / 4  # Guenther's correction brings the normal approximation close to the exact t-test value
    return _ceil(n), [
        f"Standardised effect d = difference / SD = {abs(difference):g} / {sd:g} = {d:.3f}",
        f"z for alpha = {alpha:g}: {za:.3f}; z for power {power:g}: {zb:.3f}",
        f"Normal approximation: n per group = 2 (z_a + z_b)² / d² = {n_normal:.1f}",
        f"t-test correction (+ z_a²/4): {n:.1f}; round up: {_ceil(n)} per group",
    ]


def correlation_n(r: float, alpha: float = ALPHA, power: float = 0.8, two_sided: bool = True) -> tuple[int, list[str]]:
    za, zb = z_of(1 - alpha / (2 if two_sided else 1)), z_of(power)
    c = 0.5 * math.log((1 + abs(r)) / (1 - abs(r)))
    n = ((za + zb) / c) ** 2 + 3
    return _ceil(n), [f"Fisher's z of r = {r:g}: {c:.4f}", f"n = ((z_a + z_b) / z_r)² + 3 = (({za:.3f} + {zb:.3f}) / {c:.4f})² + 3 = {n:.1f}", f"Round up: {_ceil(n)}"]


def two_means_power(n_per_group: int, difference: float, sd: float, alpha: float = ALPHA, two_sided: bool = True) -> float:
    za = z_of(1 - alpha / (2 if two_sided else 1))
    d = abs(difference) / sd
    return NORMAL.cdf(d * math.sqrt(max(n_per_group - za * za / 4, 0.0) / 2) - za)


def two_proportions_power(n_per_group: int, p1: float, p2: float, alpha: float = ALPHA, two_sided: bool = True) -> float:
    za = z_of(1 - alpha / (2 if two_sided else 1))
    pbar = (p1 + p2) / 2
    spread = math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return NORMAL.cdf((abs(p1 - p2) * math.sqrt(n_per_group) - za * math.sqrt(2 * pbar * (1 - pbar))) / spread)


DESIGNS = {
    "proportion": (proportion_n, "participants", ("p", "margin", "confidence", "population", "design_effect", "nonresponse")),
    "two-proportions": (two_proportions_n, "per group", ("p1", "p2", "alpha", "power", "two_sided")),
    "two-means": (two_means_n, "per group", ("difference", "sd", "alpha", "power", "two_sided")),
    "correlation": (correlation_n, "participants", ("r", "alpha", "power", "two_sided")),
}
SAMPLE_TEACH = {
    "consistent": "",
    "larger-than-needed": "Your sample is larger than the calculation requires. That is allowed, but explain why (for example, subgroup analyses or expected attrition) or examiners may ask.",
    "too-small": "Your sample is smaller than the calculation you describe requires, so the study may be underpowered. Recheck each input, or justify a smaller sample (for example, a pilot or a fixed population).",
}


class SampleSizeError(ValueError):
    pass


def check_sample_size(design: str, parameters: dict[str, Any], reported_n: int | None = None) -> dict[str, Any]:
    """Recompute a sample size and compare it with the reported one (2% or 2 participants of tolerance for software differences)."""
    if design not in DESIGNS:
        raise SampleSizeError(f"Unknown design {design!r}; use one of {', '.join(DESIGNS)}.")
    function, unit, allowed = DESIGNS[design]
    unknown = set(parameters) - set(allowed)
    if unknown:
        raise SampleSizeError(f"Unknown parameters for {design}: {', '.join(sorted(unknown))}. Allowed: {', '.join(allowed)}.")
    try:
        computed, steps = function(**{key: value for key, value in parameters.items() if value is not None})
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise SampleSizeError(f"Cannot compute a {design} sample size from these values: {exc}") from exc
    verdict, power = "consistent", None
    if reported_n is not None:
        tolerance = max(2, math.ceil(0.02 * computed))
        verdict = "consistent" if abs(reported_n - computed) <= tolerance else "larger-than-needed" if reported_n > computed else "too-small"
        if verdict == "too-small" and design == "two-means":
            power = round(two_means_power(reported_n, parameters["difference"], parameters["sd"], parameters.get("alpha", ALPHA), parameters.get("two_sided", True)), 3)
        elif verdict == "too-small" and design == "two-proportions":
            power = round(two_proportions_power(reported_n, parameters["p1"], parameters["p2"], parameters.get("alpha", ALPHA), parameters.get("two_sided", True)), 3)
        if power is not None:
            steps.append(f"With the reported {reported_n} per group, power is about {power:.0%}.")
    return asdict(SampleSizeCheck(design, computed, unit, reported_n, verdict, steps, power, SAMPLE_TEACH[verdict]))
