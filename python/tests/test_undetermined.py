"""Each claim, and the control that makes it falsifiable."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # python/, where the package lives
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from _adapters import (  # noqa: E402
    CoinAdapter, DeterministicAdapter, SingleObservableAdapter, UnseededAdapter,
)
from undetermined import (  # noqa: E402
    UNDETERMINED, characterize, fit, granule_for, heterogeneity, ladder_for, mde,
    plateau, to_tolerance, trials_for,
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


class ADeterministicObservableIsNotUndetermined(unittest.TestCase):
    """0.2.0. Before it, every one of these came back UNDETERMINED -- about a quantity the
    tool had measured exactly, in the same words it uses for a quantity that has no constant
    at all."""

    def test_an_exact_deterministic_constant_is_recovered(self):
        r = characterize(DeterministicAdapter(), trials=8)
        self.assertAlmostEqual(r["per_observable"]["exact"]["constant"], 7.0, places=6)

    def test_and_a_deterministic_DRIFT_is_still_refused(self):
        # The control. A fix that only widened error bars would flatten this too.
        r = characterize(DeterministicAdapter(), trials=8)
        self.assertIs(r["per_observable"]["drifting"]["constant"], UNDETERMINED)
        self.assertIn("drifting", r["undetermined"])

    def test_the_ladder_has_rungs_at_all(self):
        lad = ladder_for(lambda t, s: t / 7.0, [8, 16, 32, 64], 4)
        self.assertEqual(len(lad), 4)
        self.assertTrue(all(row["se"] > 0 for row in lad))

    def test_the_error_bar_does_not_shrink_by_re_reading_the_same_number(self):
        # Type B is not divided by sqrt(N). An error bar that fell when you looped would let
        # any deterministic constant be made significant by asking twice.
        _c4, se4 = fit(lambda t, s: t / 7.0, 512, 4)
        _c400, se400 = fit(lambda t, s: t / 7.0, 512, 400)
        self.assertAlmostEqual(se4, se400, places=15)

    def test_a_noisy_observable_is_unchanged(self):
        # The combined uncertainty reduces to Type A when the scatter dominates, so the
        # constant a stochastic adapter reports must not move.
        r = characterize(CoinAdapter(), trials=400)
        self.assertAlmostEqual(r["per_observable"]["heads"]["constant"], 2.0, places=1)


class TheGranuleRule(unittest.TestCase):
    def test_integers_are_one_unit(self):
        self.assertEqual(granule_for([1033, 300033, 8]), 1.0)

    def test_an_integer_valued_float_is_still_an_integer(self):
        self.assertEqual(granule_for([2400056.0, 8056.0]), 1.0)

    def test_a_float_set_is_never_zero(self):
        self.assertGreater(granule_for([0.673, 0.697]), 0.0)

    def test_the_granule_is_the_reported_decimal_place(self):
        self.assertEqual(granule_for([0.673, 0.697]), 1e-3)

    def test_the_finest_reading_sets_it_for_the_whole_set(self):
        # max, not min: a coarse granule is how a drift gets flattened.
        self.assertEqual(granule_for([0.5, 0.25]), 1e-2)

    def test_the_representation_is_a_floor(self):
        import math
        self.assertEqual(granule_for([8 / 7, 16 / 7, 32 / 7]), math.ulp(32 / 7))

    def test_an_empty_set_is_zero(self):
        self.assertEqual(granule_for([]), 0.0)


class TheDeterminismSeam(unittest.TestCase):
    """An observable with no scatter is not an observable with nothing to say.

    Before this, both arrived as the same silence and the report could not tell you which
    one it had. The refusal is what this package sells, so a refusal that cannot say why is
    the failure that matters -- not a wrong number, an unusable one.
    """

    class Det(object):
        observables = {"exact": lambda t, s: t * 2.0,
                       "junk": lambda t, s: 7.0}

        def truths(self):
            return [8, 16, 32, 64, 128]

    DET = {"exact": "deterministic", "junk": "deterministic"}

    def test_routing_is_decided_by_whether_anyone_SAID_what_a_unit_is_worth(self):
        # Not by whether a granule exists: `granule_for` infers one almost always, so
        # routing on its truthiness would make the ask unreachable.
        self.assertEqual(core.route("nondeterministic", False), core.TYPE_A)
        self.assertEqual(core.route("deterministic", True), core.TYPE_B)
        self.assertEqual(core.route("deterministic", False), core.ASK)
        self.assertEqual(core.route("look", False), core.UNPROBED)
        self.assertEqual(core.route("anything unrecognised", True), core.UNPROBED)

    def test_an_UNDETERMINED_deterministic_observable_asks_for_its_resolution(self):
        r = core.characterize(self.Det(), trials=4, determinism=self.DET)
        self.assertEqual(r["seam"]["junk"]["verdict"], core.DETERMINISTIC_NO_RESOLUTION)
        self.assertIn("junk", r["undetermined"])
        self.assertIn("INFERRED", r["seam"]["junk"]["why"])

    def test_an_observable_that_PRODUCED_a_constant_is_never_overwritten(self):
        # The load-bearing half. A deterministic observable with an answer is not missing a
        # resolution, and trading its explanation for the ask would swap a true sentence for
        # one the tool cannot support.
        r = core.characterize(self.Det(), trials=4, determinism=self.DET)
        self.assertEqual(r["seam"]["exact"]["route"], core.ASK)
        self.assertIsNone(r["seam"]["exact"]["verdict"])
        self.assertNotIn("exact", r["undetermined"])

    def test_a_DECLARED_resolution_routes_to_type_b_and_asks_for_nothing(self):
        r = core.characterize(self.Det(), trials=4, determinism=self.DET,
                              granules={"junk": 0.5})
        self.assertEqual(r["seam"]["junk"]["route"], core.TYPE_B)
        self.assertIsNone(r["seam"]["junk"]["verdict"])

    def test_without_a_verdict_from_outside_nothing_changes(self):
        # The seam is a pure addition: an existing caller passing neither argument gets the
        # report it got before, with every observable UNPROBED and no ask anywhere.
        r = core.characterize(self.Det(), trials=4)
        self.assertTrue(all(e["route"] == core.UNPROBED for e in r["seam"].values()))
        self.assertTrue(all(e["verdict"] is None for e in r["seam"].values()))
        self.assertIn("no plateau", " ".join(r["notes"]))

    def test_the_inferred_granule_is_RECORDED_so_the_ask_can_quote_it(self):
        # An ask that cannot say what it assumed instead is a complaint, not a request.
        r = core.characterize(self.Det(), trials=4, determinism=self.DET)
        self.assertEqual(r["per_observable"]["junk"]["granule"], 1.0)
        self.assertIs(r["per_observable"]["junk"]["scatter_free"], True)
