"""The two halves are one instrument, or they are two instruments with one name.

Every threshold in this package is a judgement call that was measured once: three errors
of heterogeneity before an observable is called informative, three times the runner-up
before one is chosen over another, two sigma across three rungs before a ladder is called
flat. A half that drifted on any of them would answer a different question under the same
documentation — and it would drift silently, because both halves would still return a
number with an error bar.

So the thresholds are compared directly, and the arithmetic is compared on IDENTICAL
inputs. Random adapters cannot be compared across the two: the languages have different
generators, and a fixture that agreed would be agreeing about its RNG. What can be
compared is every function that takes numbers and returns numbers, which is all of them
once the sampling is done.

Skips — loudly — when `node` is not on PATH, so a Python-only contributor can still run
the suite. CI asserts they were not skipped, because a skipped parity test and a passing
one look identical in a tally.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)
JS = os.path.join(REPO, "js", "src", "index.js")
sys.path.insert(0, ROOT)

import undetermined as U  # noqa: E402

NODE = shutil.which("node")


def from_node(expression):
    script = (f"import * as m from {json.dumps(JS)};"
              f"console.log(JSON.stringify({expression}));")
    proc = subprocess.run([NODE, "--input-type=module", "-e", script],
                          capture_output=True, text=True, cwd=REPO, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"node failed: {proc.stderr.strip()[:400]}")
    return json.loads(proc.stdout)


@unittest.skipUnless(NODE, "node is not on PATH, so the cross-half contract cannot be checked")
class TheThresholdsAreOneContract(unittest.TestCase):
    def test_every_threshold_is_identical(self):
        js = from_node("[m.MIN_RATIO, m.MIN_MARGIN, m.PLATEAU_K, m.PLATEAU_RUN, "
                       "m.SIGMAS, m.FLOOR_TRIALS, m.CAP_TRIALS, m.GROWTH]")
        from undetermined.budget import CAP_TRIALS, FLOOR_TRIALS, GROWTH, SIGMAS
        from undetermined.core import MIN_MARGIN, MIN_RATIO, PLATEAU_K, PLATEAU_RUN

        self.assertEqual(js, [MIN_RATIO, MIN_MARGIN, PLATEAU_K, PLATEAU_RUN,
                              SIGMAS, FLOOR_TRIALS, CAP_TRIALS, GROWTH])

    def test_UNDETERMINED_is_falsy_in_both_and_is_not_a_number(self):
        # `None` and `null` are both the absence of an answer. A half that used 0 or NaN
        # would let an undetermined constant flow into arithmetic.
        self.assertIsNone(U.UNDETERMINED)
        self.assertIsNone(from_node("m.UNDETERMINED"))


@unittest.skipUnless(NODE, "node is not on PATH, so the cross-half contract cannot be checked")
class TheArithmeticAgrees(unittest.TestCase):
    LADDER_FLAT = [{"truth": 8, "c": 2.00, "se": 0.02},
                   {"truth": 32, "c": 2.01, "se": 0.02},
                   {"truth": 128, "c": 1.99, "se": 0.02},
                   {"truth": 512, "c": 2.00, "se": 0.02}]
    LADDER_MOVING = [{"truth": 8, "c": 1.0, "se": 0.01},
                     {"truth": 32, "c": 2.0, "se": 0.01},
                     {"truth": 128, "c": 3.0, "se": 0.01},
                     {"truth": 512, "c": 4.0, "se": 0.01}]

    # Every value in issue #1's table, plus the two `%.1f` / `toFixed(1)` rounding cases
    # and the edges of the exactly-representable integers.
    FORMATTER_CASES = [0, 8, 512, 999999, 1000000, 1048576, 16777216, 9007199254740991,
                       9007199254740992.0, 1e21, 1.5, 0.25, 2.25, 0.0001, 1.2345e-05,
                       1e-07, 1234567.5, 999999.5, 1.0 / 3.0, 0.1 + 0.2, 2.675, -1048576,
                       -1.2345e-05, -2.5, 1e300, 5e-324]

    def assert_close(self, a, b, msg=""):
        self.assertAlmostEqual(a, b, places=10, msg=msg)

    def test_plateau_agrees_on_a_flat_ladder(self):
        mine = U.plateau(self.LADDER_FLAT)
        js = from_node(f"m.plateau({json.dumps(self.LADDER_FLAT)})")
        self.assert_close(mine["value"], js["value"])
        self.assert_close(mine["se"], js["se"])
        self.assertEqual(mine["from_truth"], js["from_truth"])
        self.assertEqual(mine["why"], js["why"], "the two halves explain it differently")

    def test_plateau_agrees_that_a_moving_ladder_is_UNDETERMINED(self):
        mine = U.plateau(self.LADDER_MOVING)
        js = from_node(f"m.plateau({json.dumps(self.LADDER_MOVING)})")
        self.assertIs(mine["value"], U.UNDETERMINED)
        self.assertIsNone(js["value"])
        self.assertEqual(mine["why"], js["why"])

    def test_heterogeneity_agrees(self):
        values, errors = [1.0, 2.0, 3.5], [0.1, 0.12, 0.09]
        self.assert_close(U.heterogeneity(values, errors),
                          from_node(f"m.heterogeneity({values}, {errors})"))

    def test_mde_and_the_trial_arithmetic_agree(self):
        self.assert_close(U.mde(0.013, 2.4), from_node("m.mde(0.013, 2.4)"))
        self.assertEqual(U.trials_for(0.037, 0.01, 900),
                         from_node("m.trialsFor(0.037, 0.01, 900)"))
        self.assertIsNone(U.trials_for(0.005, 0.01, 900))
        self.assertIsNone(from_node("m.trialsFor(0.005, 0.01, 900)"))

    # THE BAND. `%g` and `toPrecision(6)` agreed on integers below 1e6 and on non-integers
    # in [1e-4, 1e6) and disagreed everywhere else, and every fixture above sits inside
    # that band -- which is why the `why` assertion above was green for a defect that was
    # always there (issue #1). These values are outside it, in all three of the ways the
    # two formatters used to part company.
    OUT_OF_BAND = [1000000, 1048576, 16777216, 1e21, 1.2345e-05, 1e-07, 1234567.5]

    def test_the_shared_formatter_agrees_digit_for_digit(self):
        js = from_node("%s.map((x) => [m.fmt.sig(x), m.fmt.sig(x, 3), m.fmt.fixed(x, 1), "
                       "m.fmt.fixed(x, 0)])" % json.dumps(self.FORMATTER_CASES))
        mine = [[U.fmt.sig(x), U.fmt.sig(x, 3), U.fmt.fixed(x, 1), U.fmt.fixed(x, 0)]
                for x in self.FORMATTER_CASES]
        for x, a, b in zip(self.FORMATTER_CASES, mine, js):
            self.assertEqual(a, b, "the halves render %r differently" % (x,))

    def test_the_shared_formatter_agrees_on_the_values_that_are_not_numbers(self):
        self.assertEqual([U.fmt.sig(float("nan")), U.fmt.sig(float("inf")),
                          U.fmt.sig(float("-inf")), U.fmt.fixed(float("nan"), 1)],
                         from_node("[m.fmt.sig(NaN), m.fmt.sig(Infinity), "
                                   "m.fmt.sig(-Infinity), m.fmt.fixed(NaN, 1)]"))

    def test_plateau_explains_a_ladder_outside_that_band_in_the_same_words(self):
        # `why` names the LOWEST rung of the plateau, so a fixture only reaches the
        # formatter when the plateau itself starts out of band -- appending a high rung to
        # a ladder that was already flat from truth=8 still reports truth=8.
        for base in self.OUT_OF_BAND:
            ladder = [{"truth": base * n, "c": 2.0, "se": 0.01} for n in (1, 2, 4)]
            mine = U.plateau(ladder)
            js = from_node("m.plateau(%s)" % json.dumps(ladder))
            self.assertEqual(mine["why"], js["why"],
                             "the two halves explain a plateau from truth=%r differently"
                             % (base,))
            self.assertIn("2.0 sigma", mine["why"])

    def test_plateau_agrees_where_a_drifting_ladder_settles_late(self):
        # The shape the reporter hit: the low rungs are still moving and the plateau begins
        # at a rung whose size is exactly where the two formatters disagreed.
        ladder = [{"truth": 4096, "c": 1.0, "se": 0.01},
                  {"truth": 65536, "c": 1.5, "se": 0.01},
                  {"truth": 1048576, "c": 2.0, "se": 0.01},
                  {"truth": 16777216, "c": 2.0, "se": 0.01},
                  {"truth": 268435456, "c": 2.0, "se": 0.01}]
        mine = U.plateau(ladder)
        js = from_node("m.plateau(%s)" % json.dumps(ladder))
        self.assertEqual(mine["from_truth"], 1048576)
        self.assertEqual(mine["why"], js["why"])
        self.assertEqual(mine["why"], "3 rungs from truth=1048576 agree within 2.0 sigma")

    def test_fit_agrees_on_a_deterministic_sample(self):
        # A sample that ignores its seed is refused by `characterize`, but `fit` is the
        # primitive underneath and takes whatever it is handed -- which makes it the one
        # place the two halves can be compared on identical numbers.
        #
        # THIS TEST USED TO ASSERT `se == 0.0` IN BOTH HALVES, and that is worth keeping in
        # the file rather than only in a changelog: the defect 0.2.0 fixes was not merely
        # unnoticed, it was PINNED. A deterministic sample has no scatter, so the Type A
        # error is zero, so `ladder_for` dropped the rung and the report said the constant
        # could not be determined -- about a quantity it had measured exactly. The error is
        # now the COMBINED uncertainty, and what the two halves must agree on is that.
        mine_c, mine_se = U.fit(lambda t, s: t / 2.0, 512, 50)
        js = from_node("m.fit((t, s) => t / 2.0, 512, 50)")
        self.assert_close(mine_c, js[0])
        self.assertGreater(mine_se, 0.0)
        self.assert_close(mine_se, js[1])

    def test_the_granule_rule_agrees(self):
        for vals in ([1033.0, 300033.0], [0.673, 0.697], [0.5, 0.25],
                     [8 / 7, 16 / 7, 32 / 7], [1.0, 2.5], [1e-7, 2e-7], [0.0, 0.25]):
            js = from_node("m.granuleFor(%s)" % json.dumps(vals))
            self.assert_close(U.granule_for(vals), js)

    def test_the_ladder_agrees_on_a_deterministic_observable(self):
        # The case 0.1.0 could not answer at all: every rung dropped, ladder empty.
        mine = U.ladder_for(lambda t, s: t / 7.0, [8, 16, 32, 64], 4)
        js = from_node("m.ladderFor((t, s) => t / 7.0, [8, 16, 32, 64], 4)")
        self.assertEqual(len(mine), 4)
        self.assertEqual(len(js), 4)
        for a, b in zip(mine, js):
            self.assert_close(a["c"], b["c"])
            self.assert_close(a["se"], b["se"])


@unittest.skipUnless(NODE, "node is not on PATH, so the cross-half contract cannot be checked")
class TheRENDEREDReportAgrees(unittest.TestCase):
    """The comparison the reporter of issue #1 was making when they found the defect.

    Comparing the numbers a report was rendered FROM is the weaker check: `why` strings
    are what a consumer quotes, and they went through two different formatters. The
    adapter below is deterministic in both languages -- no RNG, so nothing here is
    agreeing about its generator -- which makes the whole rendered report comparable.
    """

    # Both observables are proportional to the truth with a seeded wobble, so each one
    # has a constant AND an error bar, and the arithmetic between the halves is the same
    # sequence of IEEE-754 operations on the same doubles.
    JS_ADAPTER = ("{truths: () => [1000, 2000, 4000], observables: "
                  "{a: (t, s) => t * (0.5 + (s % 7) / 100), "
                  "b: (t, s) => t * (0.25 + (s % 5) / 40)}}")

    class Adapter:
        def truths(self):
            return [1000, 2000, 4000]

        @property
        def observables(self):
            return {"a": lambda t, s: t * (0.5 + (s % 7) / 100),
                    "b": lambda t, s: t * (0.25 + (s % 5) / 40)}

    def test_both_halves_say_the_same_thing_about_an_unsupportable_constant(self):
        # A tolerance far below what 64 trials can resolve, so every constant comes back
        # unsupported and has to explain itself -- in numbers spanning several magnitudes.
        mine = U.to_tolerance(self.Adapter(), 1e-9, floor=64, cap=64)
        js = from_node(f"m.toTolerance({self.JS_ADAPTER}, 1e-9, "
                       f"{{floor: 64, cap: 64}})")
        for name in ("a", "b"):
            self.assertIn("could not have detected",
                          mine["per_observable"][name]["why_unsupported"])
            self.assertEqual(mine["per_observable"][name]["why_unsupported"],
                             js["per_observable"][name]["why_unsupported"],
                             f"the halves explain {name} differently")
        self.assertEqual(mine["notes"], js["notes"])

    def test_both_halves_refuse_in_the_same_words(self):
        mine = U.characterize(self.Adapter(), trials=64)
        js = from_node(f"m.characterize({self.JS_ADAPTER}, {{trials: 64}})")
        self.assertEqual(mine["per_observable"]["a"]["plateau"]["why"],
                         js["per_observable"]["a"]["plateau"]["why"])
        self.assertEqual(mine["notes"], js["notes"])

    def test_the_whole_budget_block_agrees_including_a_shortfall_on_a_tie(self):
        # `shortfall` is a NUMBER and so escaped the `why` comparisons above, but it was
        # rounded by each language's own primitive: `round` rounds halves to even and
        # `Math.round` rounds them up. This tolerance is chosen so `would_need` lands on
        # 72 and the shortfall is exactly 72/64 == 1.125 -- the tie, where the two used to
        # report 1.12 and 1.13.
        mine = U.to_tolerance(self.Adapter(), 0.0244, floor=64, cap=64)
        js = from_node(f"m.toTolerance({self.JS_ADAPTER}, 0.0244, "
                       f"{{floor: 64, cap: 64}})")
        self.assertEqual(mine["budget"]["would_need"], 72)
        self.assertEqual(mine["budget"]["shortfall"], 1.13)
        self.assertEqual(mine["budget"], js["budget"])


@unittest.skipUnless(NODE, "node is not on PATH, so the cross-half contract cannot be checked")
class BothHalvesRefuseTheSameThings(unittest.TestCase):
    def test_both_refuse_a_single_observable_adapter(self):
        js = from_node(
            "(() => { try { m.characterize({truths: () => [1,2,3], "
            "observables: {a: () => 1}}); return null; } "
            "catch (e) { return e.message; } })()"
        )
        self.assertIsNotNone(js, "the JavaScript half accepted one observable")
        self.assertIn("cannot be shown to make one", js)

        from _adapters import SingleObservableAdapter

        with self.assertRaises(ValueError) as caught:
            U.characterize(SingleObservableAdapter(), trials=50)
        self.assertIn("cannot be shown to make one", str(caught.exception))

    def test_both_refuse_an_observable_that_ignores_its_seed(self):
        js = from_node(
            "(() => { try { m.characterize({truths: () => [8, 64], observables: "
            "{a: (t, s) => t + s, b: (t) => Math.random() * t}}, {trials: 20}); "
            "return null; } catch (e) { return e.message; } })()"
        )
        self.assertIsNotNone(js, "the JavaScript half accepted an unseeded observable")
        self.assertIn("not reproducible", js)

        from _adapters import UnseededAdapter

        with self.assertRaises(ValueError) as caught:
            U.characterize(UnseededAdapter(), trials=20)
        self.assertIn("not reproducible", str(caught.exception))

    def test_both_refuse_it_in_the_SAME_words_and_not_merely_at_the_same_time(self):
        # The test above compares a substring, because `Math.random` and `random.random`
        # cannot be made to return the same pair. This observable is unreproducible
        # DETERMINISTICALLY -- a counter, not a generator -- so the whole refusal is
        # comparable, and it is a refusal that prints four numbers. It went out through
        # `%r` on one side and a template literal on the other until the formatter was
        # made to cover it too.
        counter = ("(() => { let i = 0; try { m.reproducible({a: () => 1 / 3 + i++ * 1e-16,"
                   " b: () => 1}, [1000000]); return null; } catch (e) "
                   "{ return e.message; } })()")
        js = from_node(counter)
        self.assertIsNotNone(js, "the JavaScript half accepted a non-reproducible one")

        i = iter(range(99))
        obs = {"a": lambda t, s: 1.0 / 3.0 + next(i) * 1e-16, "b": lambda t, s: 1.0}
        with self.assertRaises(ValueError) as caught:
            U.reproducible(obs, [1000000])
        self.assertEqual(str(caught.exception), js)
        # And at full precision, so the two values it is contrasting are two strings.
        self.assertIn("returned 0.3333333333333333 and then 0.3333333333333334",
                      str(caught.exception))

    def test_both_refuse_to_render_fewer_than_one_significant_digit(self):
        js = from_node("(() => { try { m.fmt.sig(0.4, 0); return null; } "
                       "catch (e) { return e.message; } })()")
        self.assertIsNotNone(js, "the JavaScript half rendered zero significant digits")
        with self.assertRaises(ValueError) as caught:
            U.fmt.sig(0.4, 0)
        self.assertEqual(str(caught.exception), js)

    def test_both_refuse_a_tolerance_of_zero(self):
        js = from_node(
            "(() => { try { m.toTolerance({truths: () => [1,2,3], observables: "
            "{a: () => 1, b: () => 2}}, 0); return null; } "
            "catch (e) { return e.message; } })()"
        )
        self.assertIn("will not choose it for you", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
