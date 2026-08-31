"""Each claim, and the control that makes it falsifiable."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # python/, where the package lives
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _adapters import CoinAdapter, SingleObservableAdapter, UnseededAdapter  # noqa: E402
from undetermined import (  # noqa: E402
    UNDETERMINED, characterize, fit, heterogeneity, mde, plateau, to_tolerance,
    trials_for,
)


class ItRecoversAConstantItKnowsTheAnswerTo(unittest.TestCase):
    def test_a_fair_coin_gives_exactly_two(self):
        # E[heads] = truth/2, so c = truth / E[heads] = 2 by construction. A tool that
        # returned 2.0 for everything would also pass this, which is why the next class
        # exists.
        r = characterize(CoinAdapter(), trials=400)
        self.assertAlmostEqual(r["per_observable"]["heads"]["constant"], 2.0, places=1)

    def test_the_constant_carries_an_error_bar_and_a_regime(self):
        row = characterize(CoinAdapter(), trials=400)["per_observable"]["heads"]
        self.assertIsNotNone(row["constant_se"])
        self.assertGreater(row["constant_se"], 0)
        self.assertIsNotNone(row["regime_from"])
        self.assertIn("agree within", row["plateau"]["why"])


class ItRefusesRatherThanFits(unittest.TestCase):
    """The differentiator. Anything can fit a curve; this puts things on a list."""

    def test_an_observable_with_no_constant_is_UNDETERMINED(self):
        # `flat` has an expectation independent of the truth, so c = truth/E climbs every
        # rung and never settles.
        r = characterize(CoinAdapter(), trials=400)
        self.assertIn("flat", r["undetermined"])
        self.assertIs(r["per_observable"]["flat"]["constant"], UNDETERMINED)
        self.assertIn("still moving", r["per_observable"]["flat"]["plateau"]["why"])

    def test_and_the_other_observable_in_the_same_run_is_NOT_undetermined(self):
        # THE CONTROL. A tool that called everything undetermined would satisfy the test
        # above and be useless.
        r = characterize(CoinAdapter(), trials=400)
        self.assertNotIn("heads", r["undetermined"])

    def test_one_observable_is_refused_outright(self):
        with self.assertRaises(ValueError) as caught:
            characterize(SingleObservableAdapter(), trials=100)
        self.assertIn("cannot be shown to make one", str(caught.exception))

    def test_choosing_between_instances_is_UNDETERMINED_from_one_instance(self):
        r = characterize(CoinAdapter(), trials=200)
        self.assertIs(r["informative"]["choice"], UNDETERMINED)
        self.assertIn("only one instance", r["informative"]["why"])


class TheReproducibilityPrecondition(unittest.TestCase):
    """An observable that ignores its seed makes every number below it a mean over noise."""

    def test_an_unseeded_observable_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            characterize(UnseededAdapter(), trials=100)
        message = str(caught.exception)
        self.assertIn("not reproducible", message)
        self.assertIn("unseeded", message)
        self.assertIn("mean over noise", message)

    def test_a_seeded_adapter_passes_the_same_gate(self):
        # THE CONTROL: the gate must not simply reject everything.
        characterize(CoinAdapter(), trials=100)

    def test_the_gate_is_why_it_matters_not_merely_that_it_fires(self):
        # An unseeded observable does NOT fail on its own: it still produces a mean, a
        # standard error and a ladder. Shown here so the precondition is not mistaken
        # for a nicety -- without it, this is what would have been reported.
        from undetermined import ladder_for
        lad = ladder_for(UnseededAdapter()._unseeded, [64, 256, 1024], 200)
        self.assertEqual(len(lad), 3)
        for rung in lad:
            self.assertGreater(rung["se"], 0)


class TheBudget(unittest.TestCase):
    def test_mde_is_three_standard_errors_relative(self):
        self.assertAlmostEqual(mde(0.01, 2.0), 3.0 * 0.005)
        self.assertIsNone(mde(None, 2.0))
        self.assertIsNone(mde(0.01, 0))

    def test_being_k_times_too_coarse_costs_k_squared_trials(self):
        # se falls as 1/sqrt(N). Twice too coarse is four times the trials.
        self.assertEqual(trials_for(0.02, 0.01, 1000), 4001)
        self.assertIsNone(trials_for(0.005, 0.01, 1000), "already supported")

    def test_a_tolerance_must_be_supplied(self):
        with self.assertRaises(ValueError) as caught:
            to_tolerance(CoinAdapter(), tolerance=0)
        self.assertIn("will not choose it for you", str(caught.exception))

    def test_it_reports_support_rather_than_only_a_number(self):
        r = to_tolerance(CoinAdapter(), tolerance=0.05, floor=200, cap=1600)
        row = r["per_observable"]["heads"]
        self.assertIn("supported", row)
        self.assertIn("mde", row)
        self.assertIn("all_supported", r["budget"])
        self.assertGreaterEqual(len(r["budget"]["history"]), 1)

    def test_an_UNDETERMINED_observable_is_never_chased_with_more_trials(self):
        # No amount of precision turns a ladder that never flattens into a constant.
        r = to_tolerance(CoinAdapter(), tolerance=0.05, floor=200, cap=800)
        self.assertNotIn("flat", r["budget"]["unsupported"])


class ThePrimitives(unittest.TestCase):
    def test_heterogeneity_is_in_units_of_error_never_magnitude(self):
        # The rule that survived every round: compare against the NOISE, not the SIZE.
        # Same spread, same errors, magnitudes 1000x apart -> the same answer.
        small = heterogeneity([1.0, 2.0, 3.0], [0.1, 0.1, 0.1])
        large = heterogeneity([1001.0, 1002.0, 1003.0], [0.1, 0.1, 0.1])
        self.assertAlmostEqual(small, large)

    def test_a_ladder_shorter_than_the_run_is_UNDETERMINED(self):
        p = plateau([{"truth": 1, "c": 1.0, "se": 0.1}])
        self.assertIs(p["value"], UNDETERMINED)
        self.assertIn("shorter than the required run", p["why"])

    def test_fit_returns_nothing_when_the_mean_is_zero(self):
        c, se = fit(lambda t, s: 0.0, 10, 5)
        self.assertIsNone(c)
        self.assertIsNone(se)


if __name__ == "__main__":
    unittest.main(verbosity=2)
