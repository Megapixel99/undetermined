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

def fit(sample, truth, trials, seed0=0):
    """c such that c * E[raw] == truth. Returns (c, standard_error)."""
    raws = [sample(truth, seed0 + i) for i in range(trials)]
    mean = sum(raws) / len(raws)
    if mean == 0.0:
        return None, None
    c = truth / mean
    var = sum((r - mean) ** 2 for r in raws) / (len(raws) - 1) if len(raws) > 1 else 0.0
    cv = math.sqrt(var) / abs(mean)
    return c, abs(c) * cv / math.sqrt(len(raws))


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


# ---------------------------------------------------------------- the report

def ladder_for(sample, truths, trials, seed0=0):
    out = []
    for t in truths:
        c, se = fit(sample, t, trials, seed0)
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
    """
    for name, f in sorted(obs.items()):
        for truth in ({truths[0], truths[-1]} if truths else ()):
            first, second = f(truth, seed0), f(truth, seed0)
            if first != second:
                raise ValueError(
                    "observable %r is not reproducible: at truth=%r and seed=%r it "
                    "returned %r and then %r. Every constant below is fitted from a mean "
                    "over seeds, so an observable that ignores its seed yields a mean "
                    "over noise -- which still plateaus, and would be reported as an "
                    "answer." % (name, truth, seed0, first, second))


def characterize(adapter, trials=2500, seed0=17):
    """The whole report. Nothing here knows what program it is looking at."""
    truths = list(adapter.truths())
    obs = adapter.observables
    if len(obs) < 2:
        raise ValueError("an adapter must expose at least two observables, or there is no "
                         "choice to make and the tool cannot be shown to make one")
    reproducible(obs, truths, seed0)
    per = {}
    for name, f in obs.items():
        lad = ladder_for(f, truths, trials, seed0)
        p = plateau(lad)
        per[name] = {"ladder": lad, "plateau": p,
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
    return {"observables": sorted(obs), "per_observable": per,
            "informative": informative, "perturbation_response": response,
            "undetermined": undetermined,
            "notes": _notes(per, informative, undetermined)}


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


def _notes(per, informative, undetermined):
    out = []
    for n in sorted(undetermined):
        out.append("`%s`: no plateau -- %s" % (n, per[n]["plateau"]["why"]))
    if informative["choice"] is UNDETERMINED:
        out.append("which observable characterises the program: UNDETERMINED -- %s"
                   % informative["why"])
    return out
