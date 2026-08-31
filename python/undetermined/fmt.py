"""One number, one rendering, in both halves.

Every user-visible number this package prints goes through here, because the obvious way
-- each half reaching for its own language's formatter -- produced two instruments with
one name. `%g` and `toPrecision(6)` agree on integers below 1e6 and on non-integers in
[1e-4, 1e6), and disagree everywhere else; `%.1f` and `toFixed(1)` round halves in
opposite directions. Both defects were invisible to the parity suite because every
fixture in it sat inside the band where the two happen to agree (issue #1).

So the rule is written out rather than delegated, and `js/src/fmt.js` is this file in the
other language. THE RULE:

  * THE DIGITS COME FROM THE SHORTEST DECIMAL STRING THAT ROUND-TRIPS TO THE DOUBLE.
    Python's `repr` and JavaScript's `String` are both specified to produce exactly that
    string, which makes it the one decimal expansion the two halves can be built on.
    They disagree about how to punctuate it -- where to switch to exponent notation, how
    wide the exponent is -- so only the digits and the exponent are taken from them and
    everything below re-punctuates from scratch.

  * ROUNDING IS HALF AWAY FROM ZERO, on those digits. Pinned explicitly because the
    primitives disagree silently: `'%.1f' % 0.25` is `0.2` (half to even) and
    `(0.25).toFixed(1)` is `0.3` (half away from zero). Note that this rounds the
    shortest representation and not the exact binary value, so `fixed(2.675, 2)` is
    `2.68` even though the double is a hair under 2.675. That is a choice, it is the
    same choice in both halves, and it is the one a reader of the printed number expects.

  * AN INTEGER A DOUBLE HOLDS EXACTLY IS WRITTEN OUT IN FULL -- never rounded, never in
    exponent notation. These are mostly ladder rungs, and a rung at 16777216 is not
    clarified by calling it 1.67772e+07.

  * ANYTHING ELSE gets `digits` significant digits with trailing zeros stripped: fixed
    notation while the decimal exponent is in [-4, digits), exponent notation outside it
    with the exponent padded to two places. That is `%g`'s notation rule, kept because
    the Python half already printed it and it is the more familiar of the two.

Both functions take anything float() accepts and render it as the double it becomes:
the JavaScript half has nothing wider than a double, so a Python int past 2**53 has no
rendering the two halves could agree on and is not given a special one here.
"""

SIG_DIGITS = 6
EXACT_INT = 9007199254740991        # 2**53 - 1, the last integer a double holds exactly

_INF = float("inf")


def sig(x, digits=SIG_DIGITS):
    """`x` to `digits` significant digits. Exact integers are written out in full."""
    x = float(x)
    special = _special(x)
    if special is not None:
        return special
    neg, ds, exp = _parts(x)
    if not ds:
        return "0"
    if not (x.is_integer() and abs(x) <= EXACT_INT):
        ds, exp = _round(ds, exp, digits)
        if not (-4 <= exp - 1 < digits):
            return _sign(neg) + _scientific(ds, exp - 1)
    return _sign(neg) + _plain(ds, exp)


def fixed(x, places):
    """`x` with exactly `places` digits after the point, half away from zero."""
    x = float(x)
    special = _special(x)
    if special is not None:
        return special
    neg, ds, exp = _parts(x)
    ds, exp = _round(ds, exp, exp + places)
    return _sign(neg) + _padded(ds, exp, places)


# ------------------------------------------------------------------- the shared rule

def _special(x):
    if x != x:
        return "nan"
    if x == _INF:
        return "inf"
    if x == -_INF:
        return "-inf"
    return None


def _sign(neg):
    return "-" if neg else ""


def _parts(x):
    """(negative, digits, exp) with |x| == 0.<digits> * 10**exp.

    `digits` carries no leading or trailing zeros and is empty exactly when x is zero, so
    the caller never has to care which of `1e+16`, `0.0001` or `1.5` repr chose to hand
    back -- or which of the three JavaScript would have chosen for the same double.
    """
    s = repr(abs(x))
    mant, _, e = s.partition("e")
    exp = int(e) if e else 0
    intp, _, frac = mant.partition(".")
    ds = intp + frac
    exp += len(intp)
    trimmed = ds.lstrip("0")
    exp -= len(ds) - len(trimmed)
    return x < 0, trimmed.rstrip("0"), exp


def _round(ds, exp, keep):
    """Keep the leading `keep` of `ds`, rounding half away from zero."""
    if keep >= len(ds):
        return ds, exp
    if keep < 0 or not ds:
        return "", exp
    if keep == 0:
        # Everything is below the rounding position: this is 0 or one unit above it.
        return ("1", exp + 1) if ds[0] >= "5" else ("", exp)
    head = ds[:keep]
    if ds[keep] < "5":
        return head.rstrip("0"), exp
    carried = str(int(head) + 1)
    if len(carried) > keep:                     # 999 -> 1000, a digit wider and a rung up
        carried, exp = carried[:-1], exp + 1
    return carried.rstrip("0"), exp


def _plain(ds, exp):
    """0.<ds> * 10**exp without an exponent, trailing zeros already stripped from `ds`."""
    if exp <= 0:
        return "0." + "0" * -exp + ds
    if exp >= len(ds):
        return ds + "0" * (exp - len(ds))
    return ds[:exp] + "." + ds[exp:]


def _scientific(ds, e):
    """<d>.<ds> e +NN -- the exponent padded to two digits, as `%g` writes it."""
    mant = ds[0] + ("." + ds[1:] if len(ds) > 1 else "")
    return "%se%s%02d" % (mant, "+" if e >= 0 else "-", abs(e))


def _padded(ds, exp, places):
    if not ds:
        whole, frac = "0", ""
    elif exp <= 0:
        whole, frac = "0", "0" * -exp + ds
    elif exp >= len(ds):
        whole, frac = ds + "0" * (exp - len(ds)), ""
    else:
        whole, frac = ds[:exp], ds[exp:]
    if places <= 0:
        return whole
    return whole + "." + (frac + "0" * places)[:places]
