"""The Reproducer's checks. Reference values come from SciPy 1.18.1 and statsmodels 0.15.0 (computed once, pinned
here); the results sections and proposals are synthetic, with errors seeded on purpose."""

import pytest

from mwenza_engine.reproducer import SampleSizeError, check_reported_statistics, check_sample_size, p_chi2, p_f, p_r, p_t, p_z

# (function, arguments, SciPy value)
REFERENCE = [
    (p_t, (2.0, 10), 0.07338803477), (p_t, (4.7, 120), 7.000310651e-06), (p_t, (1.96, 1000), 0.05027318496), (p_t, (3.1, 1.5), 0.1277697766),
    (p_f, (2.5, 3, 40), 0.07325435202), (p_f, (10.2, 2, 200), 6.051186641e-05), (p_f, (35.0, 1, 2), 0.02740247484),
    (p_chi2, (3.84, 1), 0.05004352125), (p_chi2, (40.0, 10), 1.694474393e-05), (p_chi2, (150.0, 100), 0.0009039320424),
    (p_z, (3.29,), 0.001001873828), (p_r, (0.3, 48), 0.03428618003), (p_r, (-0.12, 300), 0.03713590017),
]


@pytest.mark.parametrize("function,args,expected", REFERENCE)
def test_distributions_match_scipy(function, args, expected):
    assert function(*args) == pytest.approx(expected, rel=1e-9)


SEEDED = """[SYNTHETIC RESULTS SECTION - fictional study, errors seeded on purpose]
Women who lived within 5 km of a facility were more likely to deliver there, t(98) = 2.45, p = .016.
Satisfaction differed across the three counties, F(2, 147) = 3.10, p = .03.
Delivery place was associated with parity, χ2(2, N = 400) = 9.21, p = .010.
Distance correlated negatively with antenatal visits, r(88) = −.31, p = .003.
The intervention group scored higher, t(45) = 1.70, p = .048.
Age did not predict facility delivery, t(120) = 1.20, p = .03.
Travel cost predicted home delivery, z = 2.10, p < .05.
Household size showed no effect, F(1, 60) = 1.02, p = .32.
Education strongly predicted delivery, t(200) = 6.80, p < .001."""


def by_value(report):
    return {(result["test"], result["value"]): result for result in report["results"]}


def test_seeded_p_value_errors_are_caught_and_correct_ones_pass():
    report = check_reported_statistics(SEEDED)
    results = by_value(report)
    assert len(report["results"]) == 9
    assert results[("t", 2.45)]["verdict"] == "consistent"
    assert results[("F", 3.10)]["verdict"] == "inconsistent"  # recomputed p = .048: same side of .05, wrong value
    assert results[("chi2", 9.21)]["verdict"] == "consistent"
    assert results[("r", -0.31)]["verdict"] == "consistent"  # Unicode minus handled
    one_tailed = results[("t", 1.70)]
    assert one_tailed["verdict"] == "decision-error" and "one-tailed" in one_tailed["note"]  # two-tailed p = .096
    assert results[("t", 1.20)]["verdict"] == "decision-error" and results[("t", 1.20)]["computed_p"] == pytest.approx(0.2325, abs=1e-4)
    assert results[("z", 2.10)]["verdict"] == "consistent"
    assert results[("F", 1.02)]["verdict"] == "consistent"
    assert results[("t", 6.80)]["verdict"] == "consistent"
    assert report["status"] == "decision-errors" and report["counts"] == {"consistent": 6, "inconsistent": 1, "decision-error": 2}
    assert all(result["teach"] for result in report["results"] if result["verdict"] != "consistent")


def test_rounding_of_the_statistic_is_allowed_for():
    # t(28) = 2.05 gives p = .0499; t = 2.045 (which rounds to 2.05) gives .0503, so "p = .05" is consistent.
    assert check_reported_statistics("t(28) = 2.05, p = .05")["results"][0]["verdict"] == "consistent"
    assert check_reported_statistics("t(28) = 2.05, p = .04")["results"][0]["verdict"] == "inconsistent"  # still below .05
    assert check_reported_statistics("t(28) = 2.05, p = .07")["results"][0]["verdict"] == "decision-error"


def test_text_without_results_says_so():
    assert check_reported_statistics("We will use logistic regression.")["status"] == "none-found"


def test_cochran_sample_sizes():
    common = check_sample_size("proportion", {"p": 0.5, "margin": 0.05}, 384)
    assert common["computed_n"] == 385 and common["verdict"] == "consistent"  # students usually round 384.16 down
    adjusted = check_sample_size("proportion", {"p": 0.5, "margin": 0.05, "population": 2000, "nonresponse": 0.1})
    assert adjusted["computed_n"] == 359 and len(adjusted["steps"]) == 4  # n0 384.2, FPC 322.4, /0.9 = 358.2, round up
    assert check_sample_size("proportion", {"p": 0.5, "margin": 0.05}, 200)["verdict"] == "too-small"


def test_seeded_power_calculation_errors_are_caught():
    # Synthetic proposal: "to detect a 5-point difference (SD 10) with 80% power at alpha .05 we need 30 per group".
    two_means = check_sample_size("two-means", {"difference": 5, "sd": 10, "alpha": 0.05, "power": 0.8}, 30)
    assert two_means["computed_n"] == 64 and two_means["verdict"] == "too-small"
    assert 0.45 < two_means["achieved_power"] < 0.5  # statsmodels exact t-test power at n = 30: 0.478
    proportions = check_sample_size("two-proportions", {"p1": 0.6, "p2": 0.4}, 97)
    assert proportions["computed_n"] == 97 and proportions["verdict"] == "consistent"
    assert check_sample_size("correlation", {"r": 0.3}, 85)["verdict"] == "consistent"
    assert check_sample_size("two-means", {"difference": 0.5, "sd": 1}, 150)["verdict"] == "larger-than-needed"


def test_exact_t_test_sample_sizes_match_statsmodels():
    # statsmodels TTestIndPower.solve_power(d, alpha=.05, power=.8): 393.41, 63.77, 25.52
    assert [check_sample_size("two-means", {"difference": d, "sd": 1})["computed_n"] for d in (0.2, 0.5, 0.8)] == [394, 64, 26]


def test_bad_inputs_are_refused_with_guidance():
    with pytest.raises(SampleSizeError, match="Unknown design"):
        check_sample_size("anova", {})
    with pytest.raises(SampleSizeError, match="Unknown parameters"):
        check_sample_size("proportion", {"p": 0.5, "margin": 0.05, "effect": 2})
    with pytest.raises(SampleSizeError, match="Cannot compute"):
        check_sample_size("correlation", {"r": 0.0})
