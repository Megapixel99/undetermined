"""Spend trials until the answer is supportable, and refuse to report one that is not.

`characterize(adapter, trials=2500)` and `discover(adapter, trials=1200)` both take a trial
count the caller has to guess. Exp 310 measured what guessing costs, on twelve sealed
capabilities with the same rule and only the precision differing:

    a coarse guess     2 of 12 correct
    a good guess      11 of 12
    a fine guess      12 of 12
    DERIVED           11 of 12   -- and you cannot guess wrong

So the derived budget is not more accurate than a good guess. What it buys is that there is
no guess: the trial count is computed from the size of effect you said you cared about and
the variance actually observed, and it varied 100x across those twelve capabilities (400 to
40,000) with nothing in the rule knowing which capability was which.

THE SECOND HALF MATTERS MORE. Exp 309 published twelve verdicts and five of them were
unresolved -- right, and reached by measurements that could not have detected the effect that
decides the question. It reported a minimum detectable effect only on the branch where it
abstained. So here EVERY constant carries its MDE, and one whose MDE exceeds the tolerance is
reported `supported: False` with what it would cost, instead of being reported as a number.

    from budget import to_tolerance
    report = to_tolerance(MyAdapter(), tolerance=0.01)   # "1% in the constant matters to me"

`tolerance` is a statement of what difference matters -- like a significance level, it is part
of the question and not a nuisance parameter. It is the one number this module will not choose
for you, and exp 310's TARGETS said so before that round ran.
"""
from . import core as CH
from . import fmt

SIGMAS = 3.0            # exp 309's RESOLVABLE_SIGMAS; an MDE is this many standard errors
FLOOR_TRIALS = 400      # exp 310's floor
CAP_TRIALS = 40000      # exp 310's cap
GROWTH = 2.0


def mde(se, value):
    """The smallest RELATIVE effect a measurement of this precision could have detected."""
    if se is None or value in (None, 0):
        return None
    return SIGMAS * abs(se / value)


def trials_for(current_mde, tolerance, spent):
    """How many trials would bring the MDE down to the tolerance.

    se falls as 1/sqrt(N), so being k times too coarse costs k^2 the trials. Returns None
    when the measurement already supports the claim.
    """
    if current_mde is None or spent <= 0 or tolerance <= 0:
        return None
    if current_mde <= tolerance:
        return None
    return int(spent * (current_mde / tolerance) ** 2) + 1


def _annotate(report, tolerance):
    """Attach an MDE and a support verdict to every constant the report carries."""
    worst = None
    for name, row in report["per_observable"].items():
        m = mde(row.get("constant_se"), row.get("constant"))
        row["mde"] = m
        row["tolerance"] = tolerance
        row["supported"] = m is not None and m <= tolerance
        if not row["supported"]:
            row["why_unsupported"] = (
                "no constant was determined" if m is None else
                "the constant is %s but this measurement could not have detected a "
                "%s relative effect (MDE %s), so it does not support a claim at that "
                "tolerance" % (fmt.sig(row["constant"]), fmt.sig(tolerance, 3),
                               fmt.sig(m, 3)))
            if m is not None and (worst is None or m > worst):
                worst = m
    return worst


def to_tolerance(adapter, tolerance, seed0=17, floor=FLOOR_TRIALS, cap=CAP_TRIALS,
                 on_step=None):
    """Run `characterize`, raising the trial count until every constant it determined is
    supported at `tolerance`, or the budget is spent.

    Returns characterize's report with three things added per observable -- `mde`,
    `tolerance`, `supported` -- plus a top-level `budget` block recording what was spent,
    whether every determined constant is supported, and what the shortfall would cost.

    An observable that comes back UNDETERMINED is left alone: no amount of precision turns a
    ladder that never flattens into a constant, and pretending otherwise is what exp 310's
    leg 0 found exp 309 doing on five of twelve.
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be positive: it is the size of effect you care "
                         "about, and this module will not choose it for you")
    trials = floor
    history = []
    while True:
        report = CH.characterize(adapter, trials=trials, seed0=seed0)
        worst = _annotate(report, tolerance)
        determined = [n for n, r in report["per_observable"].items()
                      if r["constant"] is not CH.UNDETERMINED]
        unsupported = [n for n in determined if not report["per_observable"][n]["supported"]]
        history.append({"trials": trials, "worst_mde": worst,
                        "unsupported": sorted(unsupported)})
        if on_step:
            on_step(history[-1])
        want = trials_for(worst, tolerance, trials) if unsupported else None
        if not unsupported or want is None or trials >= cap:
            report["budget"] = {
                "tolerance": tolerance, "trials": trials, "floor": floor, "cap": cap,
                "all_supported": not unsupported, "unsupported": sorted(unsupported),
                "worst_mde": worst, "history": history,
                "would_need": None if want is None else min(want, 10 ** 12),
                # Through `fmt` and back, and not through `round`: Python rounds halves to
                # even and JavaScript's `Math.round` rounds them up, so `want / cap` of
                # exactly 1.125 is 1.12 in one half and 1.13 in the other. The formatter is
                # the rule both halves already share, and a decimal string parses to the
                # same double on both sides of it.
                "shortfall": (None if want is None
                              else float(fmt.fixed(want / float(cap), 2)))}
            return report
        trials = min(cap, max(int(trials * GROWTH), want))
