"""Point it at a program; get back what can and cannot be determined about it.

One interface, no capability-specific logic.

An adapter exposes only:
    truths()              -> the controllable input values, known by construction
    observables           -> {name: f(truth, seed) -> float}
    knobs                 -> {name: [values]}  (optional)
    perturbed(knob, v)    -> {name: f(truth, seed)}  (optional, required if knobs given)

Everything below is assembled from instruments earlier rounds paid for:
  * fit c = truth / E[raw]                    (exp 297)
  * plateau across a ladder                   (exp 298)
  * heterogeneity = spread / own error        (exp 302)
  * report what is UNDETERMINED, never guess  (exps 298, 300, 303)

The rule that survived every round: compare against the NOISE, never against the SIZE.
"""
import math

from . import fmt

UNDETERMINED = None
MIN_RATIO = 3.0
MIN_MARGIN = 3.0
PLATEAU_K = 2.0
PLATEAU_RUN = 3


# ---------------------------------------------------------------- primitives

SQRT12 = math.sqrt(12.0)


def _decimals(value):
    """Decimal places in the shortest string that round-trips this float."""
    text = repr(float(value)).lower()
    if "e" in text:
        mant, _, exp = text.partition("e")
        frac = len(mant.partition(".")[2])
        return max(0, frac - int(exp))
    return len(text.partition(".")[2])


def _ulp(value):
    """The spacing of the representation at `value`. 2**(e-53) for frexp's exponent."""
    v = abs(float(value))
    if v == 0.0:
        return 0.0
    _m, e = math.frexp(v)
    return 2.0 ** (e - 53)


def granule_for(values):
    """The resolution at which these observations are REPORTED.

    THE DEFECT THIS EXISTS FOR. Every error bar in this package used to be Type A -- the
    scatter of repeated draws, `sd/sqrt(N)`. An observable that answers the same number every
    time has none, so `se` is zero, `ladder_for` drops the rung, and the report says the
    constant could not be determined. **It says that about a quantity it measured exactly.**
    The eleven capabilities this package was measured on were all stochastic simulations, so
    the case never arose; pointed at real systems it is the common case, and pointed at a
    corpus of ordinary functions it is nearly the only case.

    The metrological answer is older than this package: an instrument reporting whole units
    carries a Type B uncertainty of one unit's worth of quantisation, `granule/sqrt(12)`,
    whether or not you read it twice. This derives that granule from what the observations
    themselves carry:

      * every value an integer -> 1.0;
      * otherwise -> 10^-d for the greatest number of decimal places any observation is
        reported at, floored at the ULP of the largest value, so it is never finer than the
        representation can carry.

    IT ERRS FINE, ON PURPOSE. A coarse granule widens every error bar, and wide error bars are
    how a search flattens a drift that was never constant -- the failure this package's
    plateau rule exists to prevent. The alternatives (the greatest common divisor of the
    values, the spacing between them) can only err coarse, so neither is used, and taking the
    MAXIMUM decimal count across the set is the same argument once more: one finely-reported
    reading pulls the whole granule fine.

    What it does NOT do is make a drifting quantity plateau. A constant that is still moving
    at the top of the ladder is still moving; what changes is that the ladder exists at all.
    """
    vals = [float(v) for v in values]
    if not vals:
        return 0.0
    if all(v.is_integer() for v in vals):
        return 1.0
    places = max(_decimals(v) for v in vals)
    nonzero = [abs(v) for v in vals if v]
    floor = max(_ulp(v) for v in nonzero) if nonzero else 0.0
    return max(10.0 ** -places, floor)


# ---------------------------------------------------------------- the determinism seam
#
# THE DEFECT THIS NAMES. An observable with no sampling scatter is not an observable with
# nothing to say, and until this existed the report could not tell you which one it had. Both
# arrived as the same silence. That silence is the product here -- a refusal is the thing this
# package sells -- so a refusal that cannot say WHY is the failure mode that matters.
#
# WHAT IS AND IS NOT DECIDED HERE. Whether an observable is deterministic is a question about
# the SYSTEM, answered by running it in fresh processes and comparing; `nondet` does exactly
# that and does it better than a re-derivation would. So the verdict is an INPUT. This package
# stays a zero-dependency root and any determinism oracle can drive it, which is also why the
# routing is four lines and not a module.
#
# THE ASK IS AIMED AT SOMETHING ANSWERABLE. "What is the resolution of this observable?" is a
# property of the instrument, checkable before any fit runs, and able to be WRONG -- which is
# what makes it a request rather than a wish. `granule_for` already GUESSES it from the last
# reported digit and says so; the difference this draws is between a resolution that was
# declared and one that was inferred, because only the second is worth asking about.

DETERMINISTIC_NO_RESOLUTION = "DETERMINISTIC_NO_RESOLUTION"

TYPE_A = "type-a"        # real scatter: the Type A path this package shipped with
TYPE_B = "type-b"        # deterministic, resolution KNOWN: combined uncertainty
ASK = "ask"              # deterministic, resolution INFERRED: say so and ask
UNPROBED = "unprobed"    # determinism could not be established either way


def route(state, granule_declared):
    """Which error model an observable earns. `state` is a determinism verdict from outside.

    `granule_declared` is deliberately a BOOLEAN and not the granule itself. A granule is
    almost always available -- `granule_for` infers one from the reported digits -- so routing
    on its truthiness would send every deterministic observable down the Type B path and the
    ask would be unreachable. What decides is whether anyone SAID what one unit is worth.
    """
    if state not in ("deterministic", "nondeterministic"):
        return UNPROBED
    if state == "nondeterministic":
        return TYPE_A
    return TYPE_B if granule_declared else ASK


def ask_text(name, granule):
    """The request, naming the observable and the resolution that was assumed instead."""
    return ("`%s` answered identically on every repeat, so its Type A error is zero by "
            "construction and repeating it buys nothing. A resolution of %s was INFERRED from "
            "the digits it reports, not declared. Supply what one unit of `%s` is worth and "
            "the ladder is built from the combined uncertainty instead. That is a fact about "
            "the instrument, it can be checked before any fit runs, and it can be wrong: too "
            "fine and this observable stays silent, too coarse and the tool manufactures a "
            "constant that is not there." % (name, fmt.sig(granule), name))


def _from_raws(raws, truth, granule):
    """(c, u) for one rung, with the COMBINED standard uncertainty.

    `u = sqrt(u_A^2 + u_B^2)`, and `u_B` is NOT divided by sqrt(N): repeating a deterministic
    measurement does not buy resolution, and an error bar that shrinks when you re-read the
    same number is manufacturing precision. At `granule = 0` every line here reduces to the
    Type A formula this package shipped with.
    """
    mean = sum(raws) / len(raws)
    if mean == 0.0:
        return None, None
    c = truth / mean
    # NO SCATTER MEANS NO SCATTER, and the explicit test is not a shortcut. Summing N copies
    # of one float and dividing by N does not always return that float, so the two-pass
    # variance of identical readings comes out at ~1e-30 rather than 0 -- invisible while
    # every error bar was Type A and dominant once u_B is a real 1e-16. It is also
    # LANGUAGE-DEPENDENT: the JS half and this one disagreed on `fit(t/7, 512, 400)` by an
    # order of magnitude for exactly this reason, and the parity suite caught it.
    var = 0.0
    if len(raws) > 1 and min(raws) != max(raws):
        var = sum((r - mean) ** 2 for r in raws) / (len(raws) - 1)
    ua = math.sqrt(var) / math.sqrt(len(raws))
    ub = granule / SQRT12
    u = math.hypot(ua, ub)
    if not u:
        return None, None
    return c, abs(c) * u / abs(mean)


def fit(sample, truth, trials, seed0=0, granule=None):
    """c such that c * E[raw] == truth. Returns (c, standard_error).

    `granule` defaults to one derived from THIS rung's own draws. `ladder_for` derives one
    across the WHOLE ladder and passes it in, which is the finer and therefore safer of the
    two: a single rung of identical readings can report fewer decimal places than the ladder
    as a whole, and fewer decimal places means a coarser granule.
    """
    raws = [sample(truth, seed0 + i) for i in range(trials)]
    g = granule_for(raws) if granule is None else granule
    return _from_raws(raws, truth, g)


def _sd(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def heterogeneity(values, errors):
    """Spread across cases in units of the measurement error. Never divided by magnitude."""
    sd = _sd(values)
    if sd is None:
        return None
    mean_e = sum(errors) / len(errors)
    return None if mean_e <= 0 else sd / mean_e


def plateau(ladder, k=PLATEAU_K, need=PLATEAU_RUN):
    """Earliest rung from which every later rung agrees within k combined errors."""
    rungs = sorted(ladder, key=lambda r: r["truth"])
    if len(rungs) < need:
        return {"value": UNDETERMINED, "se": None, "from_truth": None,
                "why": "ladder shorter than the required run of %d" % need}
    for i in range(len(rungs) - need + 1):
        tail = rungs[i:]
        if all(abs(tail[0]["c"] - r["c"]) <=
               k * math.sqrt(tail[0]["se"] ** 2 + r["se"] ** 2) for r in tail[1:]):
            w = sum(1.0 / r["se"] ** 2 for r in tail)
            return {"value": sum(r["c"] / r["se"] ** 2 for r in tail) / w,
                    "se": math.sqrt(1.0 / w), "from_truth": tail[0]["truth"],
                    "why": "%d rungs from truth=%s agree within %s sigma"
                           % (len(tail), fmt.sig(tail[0]["truth"]), fmt.fixed(k, 1))}
    return {"value": UNDETERMINED, "se": None, "from_truth": None,
            "why": "no run of %d rungs agrees; the constant is still moving at the top of "
                   "the ladder" % need}


def granule_by_probe(inputs, values):
    """The granule MEASURED at consecutive inputs, or None when it cannot be.

    `granule_for` infers a granule from the reported digits and errs FINE on purpose,
    which is safe: too fine widens nothing, so a rung is dropped rather than a drift
    flattened into a plateau. Its docstring rejects the greatest common divisor because
    "the alternatives can only err coarse". That rejection is correct **for the regime
    this package samples in** and not for every regime, and the difference is measurable.

    Reckoner's exp 391 priced it over 15 observables whose quantum is derivable from a
    published constant (`struct.calcsize("P")`, `sys.int_info.sizeof_digit`, PEP 393 kind
    widths, `array.itemsize`, `get_clock_info().resolution`):

      * at CONSECUTIVE inputs the GCD of the differences recovers the true quantum on
        13 of 13 integer observables -- exactly, not approximately;
      * at a LADDER's rungs it errs coarse by the rung spacing: `list` sampled at
        1,000...300,000 gives 8,000 against a true 8;
      * on a plain linear sweep BOTH the values' GCD and the differences' GCD err coarse
        together, because a constant step `k` makes every difference `k` times the
        quantum. `[7, 14, 21, 28]` on `list` gives 56 either way, seven times too coarse.

    So the safe quantity is not an estimator but a estimator-and-regime pair: **the GCD of
    the differences at consecutive inputs**. Consecutive sampling makes the differences
    constant, which is what makes the GCD the quantum by construction rather than by luck.

    This function therefore REFUSES anything else. It is a separate probe, run for the
    granule alone and never over a fit's own rungs, and nothing here changes what
    `granule_for` returns or when `ladder_for` calls it.

    Returns None -- never a guess -- when the inputs are not consecutive, when fewer than
    two readings are given, when any reading is not an integer, or when every difference
    is zero (an observable that did not move has no quantum to find).
    """
    if len(inputs) != len(values) or len(values) < 2:
        return None
    if any(int(i) != i for i in inputs):
        return None
    steps = {int(b) - int(a) for a, b in zip(inputs, inputs[1:])}
    if steps != {1}:
        return None                      # not consecutive: the regime the GCD needs
    if any(float(v) != int(v) for v in values):
        return None                      # no integer quantum to find
    g = 0
    for a, b in zip(values, values[1:]):
        g = math.gcd(g, abs(int(b) - int(a)))
    return float(g) if g else None


# ---------------------------------------------------------------- the report

def ladder_for(sample, truths, trials, seed0=0, into=None):
    """The ladder, with ONE granule derived across every rung's draws.

    Sampling happens once. The granule is derived from the whole set rather than per rung
    because it is a property of the instrument, not of a reading, and because the whole set
    can only give a finer answer than its coarsest member.
    """
    drawn = [(t, [sample(t, seed0 + i) for i in range(trials)]) for t in truths]
    granule = granule_for([r for _t, raws in drawn for r in raws])
    # The granule is INFERRED here and the caller cannot otherwise see which number it got.
    # `into` is an optional out-parameter rather than a changed return type, because the
    # return shape is pinned against the JavaScript half and a silent widening there is the
    # drift `test_parity.py` exists to stop.
    if into is not None:
        into["granule"] = granule
        into["scatter_free"] = all(len(raws) < 2 or min(raws) == max(raws)
                                   for _t, raws in drawn)
    out = []
    for t, raws in drawn:
        c, se = _from_raws(raws, t, granule)
        if c is not None and se:
            out.append({"truth": t, "c": c, "se": se})
    return out


def reproducible(obs, truths, seed0=17):
    """Every observable must answer the same for the same (truth, seed), or refuse.

    THE PRECONDITION NOTHING ELSE HERE CAN SUBSTITUTE FOR. `fit` averages an observable
    over `trials` DIFFERENT seeds, so an observable that ignores its seed and reads the
    clock, the environment or an unseeded RNG produces a mean over noise -- and a mean
    over noise still has a standard error, still forms a ladder, and can still plateau.
    Every guard downstream compares against that error, so a broken adapter does not
    produce a wrong-looking answer: it produces a confident one.

    Checked at the cheapest place it can fail -- the first and last rung, twice each --
    because an observable that is stable at one size and not another is stable at
    neither, and four calls is a price nobody notices.

    A raise, not a `look`. The other refusals in this module describe what the program
    would not reveal; this one says the instrument was wired up wrong, and continuing
    would report a number about nothing.

    Its numbers go through `fmt` like every other number this package prints, at
    ALL_DIGITS rather than six: the message exists to say that two values differed, and
    six significant digits would render a pair that differs in the tenth as one string
    twice.
    """
    whole = fmt.ALL_DIGITS
    for name, f in sorted(obs.items()):
        for truth in ({truths[0], truths[-1]} if truths else ()):
            first, second = f(truth, seed0), f(truth, seed0)
            if first != second:
                raise ValueError(
                    "observable `%s` is not reproducible: at truth=%s and seed=%s it "
                    "returned %s and then %s. Every constant below is fitted from a mean "
                    "over seeds, so an observable that ignores its seed yields a mean "
                    "over noise -- which still plateaus, and would be reported as an "
                    "answer." % (name, fmt.sig(truth, whole), fmt.sig(seed0, whole),
                                 fmt.sig(first, whole), fmt.sig(second, whole)))


def characterize(adapter, trials=2500, seed0=17, determinism=None, granules=None):
    """The whole report. Nothing here knows what program it is looking at.

    `determinism` is `{observable: state}` from an outside oracle -- `nondet` or anything that
    answers the same question. Absent, every observable routes as before and this is a pure
    addition. `granules` is `{observable: resolution}` for the ones somebody has DECLARED; an
    observable missing from it still gets `granule_for`'s inferred value, and the difference
    between the two is what decides whether the report asks for a resolution or assumes one.
    """
    truths = list(adapter.truths())
    obs = adapter.observables
    if len(obs) < 2:
        raise ValueError("an adapter must expose at least two observables, or there is no "
                         "choice to make and the tool cannot be shown to make one")
    reproducible(obs, truths, seed0)
    per = {}
    for name, f in obs.items():
        seen = {}
        lad = ladder_for(f, truths, trials, seed0, into=seen)
        p = plateau(lad)
        per[name] = {"ladder": lad, "plateau": p,
                     "granule": seen.get("granule"),
                     "scatter_free": seen.get("scatter_free"),
                     "constant": p["value"], "constant_se": p["se"],
                     "regime_from": p["from_truth"],
                     "top_rung": lad[-1]["c"] if lad else None,
                     "top_rung_se": lad[-1]["se"] if lad else None}

    # which observable carries information about THIS instance?  Only answerable with more
    # than one instance; with one, say so rather than guessing (exp 303's family C).
    inst = getattr(adapter, "instances", None)
    informative = {"choice": UNDETERMINED,
                   "why": "only one instance was supplied, so no constant can be shown to "
                          "vary across instances; supply >=2 to decide"}
    if inst:
        vals, errs = {}, {}
        for name in obs:
            vs, es = [], []
            for sub in inst():
                c, se = fit(sub.observables[name], truths[-1], trials, seed0)
                if c is not None and se:
                    vs.append(c); es.append(se)
            vals[name], errs[name] = vs, es
        ratios = {n: heterogeneity(vals[n], errs[n]) for n in obs}
        informative = _pick(ratios)
        informative["ratios"] = ratios

    # does anything respond to perturbing the program itself?
    knobs = getattr(adapter, "knobs", None)
    response = {}
    if knobs and hasattr(adapter, "perturbed"):
        for name in obs:
            response[name] = {}
            for knob, values in knobs.items():
                pts = []
                for v in values:
                    c, _ = fit(adapter.perturbed(knob, v)[name], truths[-1], max(400, trials // 4), seed0)
                    if c and c > 0:
                        pts.append((math.log(v), math.log(c)))
                response[name][knob] = _slope(pts)

    undetermined = [n for n in obs if per[n]["constant"] is UNDETERMINED]
    seam = _seam(obs, per, determinism or {}, granules or {})
    return {"observables": sorted(obs), "per_observable": per,
            "informative": informative, "perturbation_response": response,
            "undetermined": undetermined, "seam": seam,
            "notes": _notes(per, informative, undetermined, seam)}


def _slope(pts):
    if len(pts) < 2:
        return None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return None if den <= 0 else sum((p[0]-mx)*(p[1]-my) for p in pts) / den


def _pick(ratios):
    usable = {k: v for k, v in ratios.items() if v is not None}
    live = {k: v for k, v in usable.items() if v >= MIN_RATIO}
    if not live:
        return {"choice": UNDETERMINED,
                "why": "no constant varies beyond %sx its own error across instances"
                       % fmt.fixed(MIN_RATIO, 0)}
    rank = sorted(live.items(), key=lambda kv: -kv[1])
    if len(rank) > 1 and rank[0][1] < MIN_MARGIN * rank[1][1]:
        return {"choice": UNDETERMINED,
                "why": "%s (%s) does not beat %s (%s) by %sx"
                       % (rank[0][0], fmt.fixed(rank[0][1], 1), rank[1][0],
                          fmt.fixed(rank[1][1], 1), fmt.fixed(MIN_MARGIN, 0))}
    return {"choice": rank[0][0],
            "why": "%s varies %sx its own error"
                   % (rank[0][0], fmt.fixed(rank[0][1], 1))}


def _seam(obs, per, determinism, granules):
    """{observable: {route, state, verdict, why}} -- why each silence is the silence it is.

    Only an observable that came back UNDETERMINED can carry the ask. One that produced a
    constant is not missing a resolution, and overwriting its explanation would trade a true
    sentence for one the tool cannot support -- the same rule exp 390 froze.
    """
    out = {}
    for name in obs:
        state = determinism.get(name, "unprobed")
        declared = name in granules
        where = route(state, declared)
        entry = {"route": where, "state": state, "granule_declared": declared,
                 "verdict": None, "why": None}
        if where == ASK and per[name]["constant"] is UNDETERMINED:
            entry["verdict"] = DETERMINISTIC_NO_RESOLUTION
            entry["why"] = ask_text(name, per[name].get("granule"))
        out[name] = entry
    return out


def _notes(per, informative, undetermined, seam=None):
    out = []
    for n in sorted(undetermined):
        asked = (seam or {}).get(n, {}).get("verdict")
        if asked:
            out.append("`%s`: %s -- %s" % (n, asked, (seam or {})[n]["why"]))
            continue
        out.append("`%s`: no plateau -- %s" % (n, per[n]["plateau"]["why"]))
    if informative["choice"] is UNDETERMINED:
        out.append("which observable characterises the program: UNDETERMINED -- %s"
                   % informative["why"])
    return out
