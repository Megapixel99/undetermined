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

    def test_fit_agrees_on_a_deterministic_sample(self):
        # A sample that ignores its seed is refused by `characterize`, but `fit` is the
        # primitive underneath and takes whatever it is handed -- which makes it the one
        # place the two halves can be compared on identical numbers.
        mine_c, mine_se = U.fit(lambda t, s: t / 2.0, 512, 50)
        js = from_node("m.fit((t, s) => t / 2.0, 512, 50)")
        self.assert_close(mine_c, js[0])
        self.assertEqual(mine_se, 0.0)
        self.assert_close(js[1], 0.0)


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

    def test_both_refuse_a_tolerance_of_zero(self):
        js = from_node(
            "(() => { try { m.toTolerance({truths: () => [1,2,3], observables: "
            "{a: () => 1, b: () => 2}}, 0); return null; } "
            "catch (e) { return e.message; } })()"
        )
        self.assertIn("will not choose it for you", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
