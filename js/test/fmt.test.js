/**
 * The rendering rule, pinned to strings rather than to whatever the language does.
 *
 * `python/tests/test_fmt.py` is this file in the other language and asserts the same
 * strings. That matters more than it looks: `python/tests/test_parity.py` compares the
 * two halves against EACH OTHER, and two halves that had drifted together would still
 * pass it. These two files are the fixed point they are both compared to.
 *
 * The cases are the ones from issue #1 — where `toPrecision(6)` and `%g` parted company —
 * plus the two rounding cases where `toFixed(1)` and `%.1f` do.
 */

import test from "node:test";
import assert from "node:assert/strict";

import { fmt, plateau } from "../src/index.js";

// [value, sig(value), sig(value, 3), fixed(value, 1), fixed(value, 0)]
const CASES = [
  [0,                  "0",                "0",                "0.0",   "0"],
  [8,                  "8",                "8",                "8.0",   "8"],
  [512,                "512",              "512",              "512.0", "512"],
  [999999,             "999999",           "999999",           "999999.0", "999999"],
  // THE ISSUE. The Python half said `1e+06` and `1.67772e+07` here and this half said the
  // integer; the integer is the one worth keeping, because these are input sizes.
  [1000000,            "1000000",          "1000000",          "1000000.0", "1000000"],
  [1048576,            "1048576",          "1048576",          "1048576.0", "1048576"],
  [16777216,           "16777216",         "16777216",         "16777216.0", "16777216"],
  // The last integer a double holds exactly, and the first one it does not: past it an
  // integer is a rounded value already, so writing it out in full would be a lie about
  // precision and it goes back to significant digits.
  [9007199254740991,   "9007199254740991", "9007199254740991", "9007199254740991.0",
                       "9007199254740991"],
  [9007199254740992,   "9.0072e+15",       "9.01e+15",         "9007199254740992.0",
                       "9007199254740992"],
  [1e21,               "1e+21",            "1e+21",            "1000000000000000000000.0",
                       "1000000000000000000000"],
  [1.5,                "1.5",              "1.5",              "1.5",   "2"],
  [0.25,               "0.25",             "0.25",             "0.3",   "0"],
  [0.0001,             "0.0001",           "0.0001",           "0.0",   "0"],
  // This half used to write these as `0.000012345` and `1.00000e-7`.
  [1.2345e-5,          "1.2345e-05",       "1.23e-05",         "0.0",   "0"],
  [1e-7,               "1e-07",            "1e-07",            "0.0",   "0"],
  [1234567.5,          "1.23457e+06",      "1.23e+06",         "1234567.5", "1234568"],
  [999999.5,           "1e+06",            "1e+06",            "999999.5", "1000000"],
  [1 / 3,              "0.333333",         "0.333",            "0.3",   "0"],
  [0.1 + 0.2,          "0.3",              "0.3",              "0.3",   "0"],
  [2.675,              "2.675",            "2.68",             "2.7",   "3"],
  [-1048576,           "-1048576",         "-1048576",         "-1048576.0", "-1048576"],
  [-1.2345e-5,         "-1.2345e-05",      "-1.23e-05",        "-0.0",  "-0"],
  [1e300,              "1e+300",           "1e+300",           null,    null],
  [5e-324,             "5e-324",           "5e-324",           "0.0",   "0"],
];

test("every case renders to the string the contract says", () => {
  for (const [value, six, three, one, zero] of CASES) {
    assert.equal(fmt.sig(value), six, `sig(${value})`);
    assert.equal(fmt.sig(value, 3), three, `sig(${value}, 3)`);
    if (one !== null) {
      assert.equal(fmt.fixed(value, 1), one, `fixed(${value}, 1)`);
      assert.equal(fmt.fixed(value, 0), zero, `fixed(${value}, 0)`);
    }
  }
});

test("halves round away from zero, by rule and not by inheritance", () => {
  // `(0.25).toFixed(1)` is 0.3 and `'%.1f' % 0.25` is 0.2, and neither language warns you.
  assert.equal(fmt.fixed(0.25, 1), "0.3");
  assert.equal(fmt.fixed(2.25, 1), "2.3");
  assert.equal(fmt.fixed(2.5, 0), "3");
  assert.equal(fmt.fixed(-2.5, 0), "-3");
});

test("rounding is applied to the shortest representation", () => {
  // 2.675 is a hair BELOW 2.675 as a double, so an exact-value rounding gives 2.67. This
  // rounds what was printed, which is what a reader of the number expects — and it is the
  // same choice in both halves, which is the property that matters.
  assert.equal(fmt.fixed(2.675, 2), "2.68");
  assert.equal(fmt.fixed(9.95, 1), "10.0");
});

test("a carry that widens the number moves the exponent with it", () => {
  assert.equal(fmt.sig(999999.5), "1e+06");
  assert.equal(fmt.fixed(0.96, 1), "1.0");
  assert.equal(fmt.fixed(0.96, 0), "1");
  // ... and a carry can move the number across the notation boundary as well.
  assert.equal(fmt.sig(0.0000999999), "9.99999e-05");
  assert.equal(fmt.sig(0.00009999999), "0.0001");
});

test("the exponent is padded to two digits", () => {
  // JavaScript writes `e+6`, `%g` writes `e+06`, and a report that mixes the two is two
  // reports. Two digits, as `%g` has it.
  assert.equal(fmt.sig(1e-7), "1e-07");
  assert.equal(fmt.sig(1.5e8), "150000000");        // exact integer, written in full
  assert.equal(fmt.sig(1.5e8 + 0.5), "1.5e+08");
  assert.equal(fmt.sig(1e100), "1e+100");
});

test("every digit is available when six would blur two values", () => {
  // ALL_DIGITS is the whole shortest representation, which is what a message whose point
  // is that two values DIFFER has to print: at six digits the pair below is one string
  // twice.
  const near = [1 / 3, 1 / 3 + 1e-16];
  assert.equal(fmt.sig(near[0]), fmt.sig(near[1]));
  assert.notEqual(fmt.sig(near[0], fmt.ALL_DIGITS), fmt.sig(near[1], fmt.ALL_DIGITS));
  assert.equal(fmt.sig(near[0], fmt.ALL_DIGITS), "0.3333333333333333");
  assert.equal(fmt.sig(1e-7, fmt.ALL_DIGITS), "1e-07");
  assert.equal(fmt.sig(16777216, fmt.ALL_DIGITS), "16777216");
});

test("fewer than one significant digit is refused rather than punctuated", () => {
  // There is no shortest string for "no digits": `round` returns nothing and the branches
  // below it used to punctuate that into `undefinede+00` -- and, in the other half, into
  // `0.`. Same refusal in both halves instead.
  for (const digits of [0, -1]) {
    assert.throws(() => fmt.sig(0.4, digits), /digits must be at least 1/);
  }
  assert.equal(fmt.sig(0.4, 1), "0.4");
});

test("the undefined values say so in words", () => {
  assert.equal(fmt.sig(NaN), "nan");
  assert.equal(fmt.sig(Infinity), "inf");
  assert.equal(fmt.sig(-Infinity), "-inf");
  assert.equal(fmt.fixed(NaN, 1), "nan");
  assert.equal(fmt.fixed(Infinity, 1), "inf");
});

test("a plateau states a large rung as the rung", () => {
  const ladder = [16777216, 33554432, 67108864].map((truth) => ({ truth, c: 2.0, se: 0.01 }));
  assert.equal(plateau(ladder).why, "3 rungs from truth=16777216 agree within 2.0 sigma");
});
