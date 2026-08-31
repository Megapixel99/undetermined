/**
 * One number, one rendering, in both halves.
 *
 * Every user-visible number this package prints goes through here, because the obvious
 * way — each half reaching for its own language's formatter — produced two instruments
 * with one name. `%g` and `toPrecision(6)` agree on integers below 1e6 and on
 * non-integers in [1e-4, 1e6), and disagree everywhere else; `%.1f` and `toFixed(1)`
 * round halves in opposite directions. Both defects were invisible to the parity suite
 * because every fixture in it sat inside the band where the two happen to agree
 * (issue #1).
 *
 * So the rule is written out rather than delegated, and `python/undetermined/fmt.py` is
 * this file in the other language. THE RULE:
 *
 *   * THE DIGITS COME FROM THE SHORTEST DECIMAL STRING THAT ROUND-TRIPS TO THE DOUBLE.
 *     JavaScript's `String` and Python's `repr` are both specified to produce exactly
 *     that string, which makes it the one decimal expansion the two halves can be built
 *     on. They disagree about how to punctuate it — where to switch to exponent
 *     notation, how wide the exponent is — so only the digits and the exponent are taken
 *     from them and everything below re-punctuates from scratch.
 *
 *   * ROUNDING IS HALF AWAY FROM ZERO, on those digits. Pinned explicitly because the
 *     primitives disagree silently: `(0.25).toFixed(1)` is `0.3` (half away from zero)
 *     and `'%.1f' % 0.25` is `0.2` (half to even). Note that this rounds the shortest
 *     representation and not the exact binary value, so `fixed(2.675, 2)` is `2.68` even
 *     though the double is a hair under 2.675. That is a choice, it is the same choice
 *     in both halves, and it is the one a reader of the printed number expects.
 *
 *   * AN INTEGER A DOUBLE HOLDS EXACTLY IS WRITTEN OUT IN FULL — never rounded, never in
 *     exponent notation. These are mostly ladder rungs, and a rung at 16777216 is not
 *     clarified by calling it 1.67772e+07.
 *
 *   * ANYTHING ELSE gets `digits` significant digits with trailing zeros stripped: fixed
 *     notation while the decimal exponent is in [-4, digits), exponent notation outside
 *     it with the exponent padded to two places. That is `%g`'s notation rule, kept
 *     because the Python half already printed it and it is the more familiar of the two.
 */

export const SIG_DIGITS = 6;
export const ALL_DIGITS = 17;              // a double's shortest decimal never needs more
export const EXACT_INT = 9007199254740991; // 2**53 - 1, the last integer a double holds

// Below one significant digit there is nothing left to be significant: `round` hands back
// an empty digit string and every branch under it would punctuate the empty string into
// something that is not a number -- `undefinede+00` here, `0.` in the other half. A
// refusal rather than either, and the same refusal in both halves.
const NO_DIGITS =
  "digits must be at least 1: a number rendered to fewer significant digits " +
  "than one is not a rendering of that number";

/** `x` to `digits` significant digits. Exact integers are written out in full. */
export function sig(x, digits = SIG_DIGITS) {
  if (digits < 1) throw new Error(NO_DIGITS);
  x = Number(x);
  const special = isSpecial(x);
  if (special !== null) return special;
  const [neg, ds0, exp0] = parts(x);
  let [ds, exp] = [ds0, exp0];
  if (!ds) return "0";
  if (!(Number.isInteger(x) && Math.abs(x) <= EXACT_INT)) {
    [ds, exp] = round(ds, exp, digits);
    if (!(exp - 1 >= -4 && exp - 1 < digits)) return sign(neg) + scientific(ds, exp - 1);
  }
  return sign(neg) + plain(ds, exp);
}

/** `x` with exactly `places` digits after the point, half away from zero. */
export function fixed(x, places) {
  x = Number(x);
  const special = isSpecial(x);
  if (special !== null) return special;
  const [neg, ds0, exp0] = parts(x);
  const [ds, exp] = round(ds0, exp0, exp0 + places);
  return sign(neg) + padded(ds, exp, places);
}

// --------------------------------------------------------------------- the shared rule

function isSpecial(x) {
  if (Number.isNaN(x)) return "nan";
  if (x === Infinity) return "inf";
  if (x === -Infinity) return "-inf";
  return null;
}

function sign(neg) {
  return neg ? "-" : "";
}

/**
 * [negative, digits, exp] with |x| === 0.<digits> * 10**exp.
 *
 * `digits` carries no leading or trailing zeros and is empty exactly when x is zero, so
 * the caller never has to care which of `1e+21`, `0.0001` or `1.5` String chose to hand
 * back — or which of the three Python would have chosen for the same double.
 */
function parts(x) {
  const s = String(Math.abs(x));
  const at = s.indexOf("e");
  const mant = at < 0 ? s : s.slice(0, at);
  let exp = at < 0 ? 0 : Number(s.slice(at + 1));
  const dot = mant.indexOf(".");
  const intp = dot < 0 ? mant : mant.slice(0, dot);
  const ds = dot < 0 ? mant : intp + mant.slice(dot + 1);
  exp += intp.length;
  const trimmed = ds.replace(/^0+/, "");
  exp -= ds.length - trimmed.length;
  return [x < 0, trimmed.replace(/0+$/, ""), exp];
}

/** Keep the leading `keep` of `ds`, rounding half away from zero. */
function round(ds, exp, keep) {
  if (keep >= ds.length) return [ds, exp];
  if (keep < 0 || !ds) return ["", exp];
  if (keep === 0) {
    // Everything is below the rounding position: this is 0 or one unit above it.
    return ds[0] >= "5" ? ["1", exp + 1] : ["", exp];
  }
  const head = ds.slice(0, keep);
  if (ds[keep] < "5") return [head.replace(/0+$/, ""), exp];
  let carried = String(Number(head) + 1);
  if (carried.length > keep) {
    // 999 -> 1000, a digit wider and a rung up.
    carried = carried.slice(0, -1);
    exp += 1;
  }
  return [carried.replace(/0+$/, ""), exp];
}

/** 0.<ds> * 10**exp without an exponent; trailing zeros are already gone from `ds`. */
function plain(ds, exp) {
  if (exp <= 0) return `0.${"0".repeat(-exp)}${ds}`;
  if (exp >= ds.length) return ds + "0".repeat(exp - ds.length);
  return `${ds.slice(0, exp)}.${ds.slice(exp)}`;
}

/** <d>.<ds>e+NN — the exponent padded to two digits, as `%g` writes it. */
function scientific(ds, e) {
  const mant = ds.length > 1 ? `${ds[0]}.${ds.slice(1)}` : ds[0];
  return `${mant}e${e >= 0 ? "+" : "-"}${String(Math.abs(e)).padStart(2, "0")}`;
}

function padded(ds, exp, places) {
  let whole, frac;
  if (!ds) {
    whole = "0"; frac = "";
  } else if (exp <= 0) {
    whole = "0"; frac = "0".repeat(-exp) + ds;
  } else if (exp >= ds.length) {
    whole = ds + "0".repeat(exp - ds.length); frac = "";
  } else {
    whole = ds.slice(0, exp); frac = ds.slice(exp);
  }
  if (places <= 0) return whole;
  return `${whole}.${(frac + "0".repeat(places)).slice(0, places)}`;
}
