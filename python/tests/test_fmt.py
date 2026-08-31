"""The rendering rule, pinned to strings rather than to whatever the language does.

`js/test/fmt.test.js` is this file in the other language and asserts the same strings.
That matters more than it looks: `python/tests/test_parity.py` compares the two halves
against EACH OTHER, and two halves that had drifted together would still pass it. These
two files are the fixed point they are both compared to.

The cases are the ones from issue #1 -- where `%g` and `toPrecision(6)` parted company --
plus the two rounding cases where `%.1f` and `toFixed(1)` do.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from undetermined import fmt  # noqa: E402

# (value, sig(value), sig(value, 3), fixed(value, 1), fixed(value, 0))
CASES = [
    (0,                  "0",                "0",                "0.0",   "0"),
    (8,                  "8",                "8",                "8.0",   "8"),
    (512,                "512",              "512",              "512.0", "512"),
    (999999,             "999999",           "999999",           "999999.0", "999999"),
    # THE ISSUE. `%g` said `1e+06` and `1.67772e+07` here and the JavaScript half said the
    # integer; the integer is the one worth keeping, because these are input sizes.
    (1000000,            "1000000",          "1000000",          "1000000.0", "1000000"),
    (1048576,            "1048576",          "1048576",          "1048576.0", "1048576"),
    (16777216,           "16777216",         "16777216",         "16777216.0", "16777216"),
    # The last integer a double holds exactly, and the first one it does not: past it an
    # integer is a rounded value already, so writing it out in full would be a lie about
    # precision and it goes back to significant digits.
    (9007199254740991,   "9007199254740991", "9007199254740991", "9007199254740991.0",
                         "9007199254740991"),
    (9007199254740992.0, "9.0072e+15",       "9.01e+15",         "9007199254740992.0",
                         "9007199254740992"),
    (1e21,               "1e+21",            "1e+21",            "1000000000000000000000.0",
                         "1000000000000000000000"),
    (1.5,                "1.5",              "1.5",              "1.5",   "2"),
    (0.25,               "0.25",             "0.25",             "0.3",   "0"),
    (0.0001,             "0.0001",           "0.0001",           "0.0",   "0"),
    # `toPrecision(6)` wrote these as `0.000012345` and `1.00000e-7`.
    (1.2345e-05,         "1.2345e-05",       "1.23e-05",         "0.0",   "0"),
    (1e-07,              "1e-07",            "1e-07",            "0.0",   "0"),
    (1234567.5,          "1.23457e+06",      "1.23e+06",         "1234567.5", "1234568"),
    (999999.5,           "1e+06",            "1e+06",            "999999.5", "1000000"),
    (1.0 / 3.0,          "0.333333",         "0.333",            "0.3",   "0"),
    (0.1 + 0.2,          "0.3",              "0.3",              "0.3",   "0"),
    (2.675,              "2.675",            "2.68",             "2.7",   "3"),
    (-1048576,           "-1048576",         "-1048576",         "-1048576.0", "-1048576"),
    (-1.2345e-05,        "-1.2345e-05",      "-1.23e-05",        "-0.0",  "-0"),
    (1e300,              "1e+300",           "1e+300",           None,    None),
    (5e-324,             "5e-324",           "5e-324",           "0.0",   "0"),
]


class TheRuleIsWrittenDownRatherThanDelegated(unittest.TestCase):
    def test_every_case_renders_to_the_string_the_contract_says(self):
        for value, six, three, one, zero in CASES:
            self.assertEqual(fmt.sig(value), six, "sig(%r)" % (value,))
            self.assertEqual(fmt.sig(value, 3), three, "sig(%r, 3)" % (value,))
            if one is not None:
                self.assertEqual(fmt.fixed(value, 1), one, "fixed(%r, 1)" % (value,))
                self.assertEqual(fmt.fixed(value, 0), zero, "fixed(%r, 0)" % (value,))

    def test_halves_round_away_from_zero_and_not_to_even(self):
        # `'%.1f' % 0.25` is 0.2 and `(0.25).toFixed(1)` is 0.3, and neither language warns
        # you. The rule is the JavaScript one, chosen and written out, not inherited.
        self.assertEqual(fmt.fixed(0.25, 1), "0.3")
        self.assertEqual(fmt.fixed(2.25, 1), "2.3")
        self.assertEqual(fmt.fixed(2.5, 0), "3")
        self.assertEqual(fmt.fixed(-2.5, 0), "-3")

    def test_rounding_is_applied_to_the_shortest_representation(self):
        # 2.675 is a hair BELOW 2.675 as a double, so an exact-value rounding gives 2.67.
        # This rounds what was printed, which is what a reader of the number expects -- and
        # it is the same choice in both halves, which is the property that matters.
        self.assertEqual(fmt.fixed(2.675, 2), "2.68")
        self.assertEqual(fmt.fixed(9.95, 1), "10.0")

    def test_a_carry_that_widens_the_number_moves_the_exponent_with_it(self):
        self.assertEqual(fmt.sig(999999.5), "1e+06")
        # ... and a carry can move the number across the notation boundary as well.
        self.assertEqual(fmt.sig(0.0000999999), "9.99999e-05")
        self.assertEqual(fmt.sig(0.00009999999), "0.0001")
        self.assertEqual(fmt.fixed(0.96, 1), "1.0")
        self.assertEqual(fmt.fixed(0.96, 0), "1")

    def test_the_exponent_is_padded_to_two_digits(self):
        # `%g` writes `e+06`, JavaScript writes `e+6`, and a report that mixes the two is
        # two reports. Two digits, as `%g` has it.
        self.assertEqual(fmt.sig(1e-7), "1e-07")
        self.assertEqual(fmt.sig(1.5e8), "150000000")     # exact integer, written in full
        self.assertEqual(fmt.sig(1.5e8 + 0.5), "1.5e+08")
        self.assertEqual(fmt.sig(1e100), "1e+100")

    def test_it_renders_what_a_double_can_hold_and_not_what_python_can(self):
        # The other half has nothing wider than a double, so a Python int past 2**53 has no
        # rendering the two could agree on. It is rendered as the double it becomes.
        self.assertEqual(fmt.sig(10 ** 30), fmt.sig(1e30))
        self.assertEqual(fmt.sig(10 ** 30), "1e+30")

    def test_the_undefined_values_say_so_in_words(self):
        self.assertEqual(fmt.sig(float("nan")), "nan")
        self.assertEqual(fmt.sig(float("inf")), "inf")
        self.assertEqual(fmt.sig(float("-inf")), "-inf")
        self.assertEqual(fmt.fixed(float("nan"), 1), "nan")
        self.assertEqual(fmt.fixed(float("inf"), 1), "inf")


class TheReportsGoThroughIt(unittest.TestCase):
    def test_a_plateau_states_a_large_rung_as_the_rung(self):
        from undetermined import plateau

        ladder = [{"truth": t, "c": 2.0, "se": 0.01} for t in (16777216, 33554432, 67108864)]
        self.assertEqual(plateau(ladder)["why"],
                         "3 rungs from truth=16777216 agree within 2.0 sigma")


if __name__ == "__main__":
    unittest.main(verbosity=2)
