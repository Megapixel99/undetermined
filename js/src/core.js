/**
 * Point it at a program; get back what can and cannot be determined about it.
 *
 * One interface, no capability-specific logic. An adapter exposes only:
 *
 *     truths()              -> the controllable input values, known by construction
 *     observables           -> {name: (truth, seed) => number}
 *     instances()           -> sibling instances of the same family      (optional)
 *     knobs                 -> {name: [values]}                          (optional)
 *     perturbed(knob, v)    -> {name: (truth, seed) => number}           (required with knobs)
 *
 * THE RULE THAT SURVIVED EVERY ROUND: compare against the NOISE, never against the SIZE.
 * A spread is only meaningful in units of the error on the thing that spread; dividing by
 * the magnitude instead is how a large number gets mistaken for a real one.
 *
 * This half and the Python half are one contract. The thresholds below are the contract,
 * and `python/tests/test_parity.py` asserts they are equal and that both halves give the
 * same answer on the same numbers.
 */

import * as fmt from "./fmt.js";

export const UNDETERMINED = null;
export const MIN_RATIO = 3.0;
export const MIN_MARGIN = 3.0;
export const PLATEAU_K = 2.0;
export const PLATEAU_RUN = 3;

// ------------------------------------------------------------------ primitives

/** c such that c * E[raw] === truth. Returns [c, standardError]. */
const SQRT12 = Math.sqrt(12);

/** Decimal places in the shortest string that round-trips this float. */
function decimals(value) {
  const text = String(Number(value)).toLowerCase();
  if (text.includes('e')) {
    const [mant, exp] = text.split('e');
    const frac = (mant.split('.')[1] || '').length;
    return Math.max(0, frac - Number(exp));
  }
  return (text.split('.')[1] || '').length;
}

/**
 * The spacing of the representation at `value`: 2**(e - 53) for frexp's exponent.
 *
 * Read from the exponent bits rather than from `Math.log2`, so it is exact at every power
 * of two and agrees with Python's `math.ulp` digit for digit -- which the parity suite
 * checks, because a resolution that differs between the halves is two instruments with one
 * name.
 */
function ulp(value) {
  const v = Math.abs(Number(value));
  if (v === 0) return 0;
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, v);
  const biased = (view.getUint32(0) >>> 20) & 0x7ff;
  if (biased === 0) return 5e-324; // subnormal: the smallest representable step
  return 2 ** (biased - 1023 + 1 - 53);
}

/**
 * The resolution at which these observations are REPORTED.
 *
 * THE DEFECT THIS EXISTS FOR. Every error bar in this package used to be Type A — the
 * scatter of repeated draws, `sd/sqrt(N)`. An observable that answers the same number every
 * time has none, so `se` is zero, `ladderFor` drops the rung, and the report says the
 * constant could not be determined. **It says that about a quantity it measured exactly.**
 *
 * The rule: every value an integer → 1.0; otherwise 10^-d for the greatest number of decimal
 * places any observation is reported at, floored at the ULP of the largest value.
 *
 * IT ERRS FINE, ON PURPOSE. A coarse granule widens every error bar, and wide error bars are
 * how a search flattens a drift that was never constant. The alternatives (the GCD of the
 * values, the spacing between them) can only err coarse, so neither is used.
 */
export function granuleFor(values) {
  const vals = Array.from(values, Number);
  if (vals.length === 0) return 0;
  if (vals.every((v) => Number.isInteger(v))) return 1;
  const places = Math.max(...vals.map(decimals));
  const nonzero = vals.filter((v) => v !== 0).map(Math.abs);
  const floor = nonzero.length ? Math.max(...nonzero.map(ulp)) : 0;
  return Math.max(10 ** -places, floor);
}

/**
 * [c, u] for one rung, with the COMBINED standard uncertainty.
 *
 * `u = sqrt(u_A^2 + u_B^2)`, and `u_B` is NOT divided by sqrt(N): repeating a deterministic
 * measurement does not buy resolution. At `granule = 0` this reduces to the Type A formula
 * the package shipped with.
 */
// ---------------------------------------------------------------- the determinism seam
//
// An observable with no sampling scatter is not an observable with nothing to say, and until
// this existed the report could not tell you which one it had. Both arrived as the same
// silence. The refusal is the product here, so a refusal that cannot say WHY is the failure
// that matters. Mirrors `python/undetermined/core.py`; `test_parity.py` pins the vocabulary.
//
// The determinism verdict is an INPUT, not a dependency. Deciding it means running the thing
// in fresh processes and comparing, which is `nondet`'s job; taking that on would move this
// package off layer 0 and drag `countfn` with it. Four lines, and any oracle can drive them.

export const DETERMINISTIC_NO_RESOLUTION = "DETERMINISTIC_NO_RESOLUTION";

export const TYPE_A = "type-a";      // real scatter: the Type A path this package shipped with
export const TYPE_B = "type-b";      // deterministic, resolution KNOWN: combined uncertainty
export const ASK = "ask";            // deterministic, resolution INFERRED: say so and ask
export const UNPROBED = "unprobed";  // determinism could not be established either way

/**
 * Which error model an observable earns. `state` is a determinism verdict from outside.
 *
 * `granuleDeclared` is deliberately a BOOLEAN and not the granule. A granule is almost always
 * available -- `granuleFor` infers one from the reported digits -- so routing on its
 * truthiness would send every deterministic observable down Type B and make the ask
 * unreachable. What decides is whether anyone SAID what one unit is worth.
 */
export function route(state, granuleDeclared) {
  if (state !== "deterministic" && state !== "nondeterministic") return UNPROBED;
  if (state === "nondeterministic") return TYPE_A;
  return granuleDeclared ? TYPE_B : ASK;
}

/** The request, naming the observable and the resolution that was assumed instead. */
export function askText(name, granule) {
  return `\`${name}\` answered identically on every repeat, so its Type A error is zero by ` +
    `construction and repeating it buys nothing. A resolution of ${fmt.sig(granule)} was ` +
    `INFERRED from the digits it reports, not declared. Supply what one unit of ` +
    `\`${name}\` is worth and the ladder is built from the combined uncertainty instead. ` +
    `That is a fact about the instrument, it can be checked before any fit runs, and it can ` +
    `be wrong: too fine and this observable stays silent, too coarse and the tool ` +
    `manufactures a constant that is not there.`;
}


function fromRaws(raws, truth, granule) {
  const mean = raws.reduce((a, b) => a + b, 0) / raws.length;
  if (mean === 0) return [null, null];
  const c = truth / mean;
  // NO SCATTER MEANS NO SCATTER, and the explicit test is not a shortcut. Summing N copies
  // of one float and dividing by N does not always return that float, so the two-pass
  // variance of identical readings comes out near but not at zero — invisible while every
  // error bar was Type A and dominant once u_B is a real 1e-16. It is also
  // LANGUAGE-DEPENDENT: this half and the Python one disagreed on `fit(t/7, 512, 400)` by an
  // order of magnitude for exactly this reason, and the parity suite caught it.
  const flat = raws.length > 1 && Math.min(...raws) === Math.max(...raws);
  const varr =
    raws.length > 1 && !flat
      ? raws.reduce((a, r) => a + (r - mean) ** 2, 0) / (raws.length - 1)
      : 0;
  const ua = Math.sqrt(varr) / Math.sqrt(raws.length);
  const ub = granule / SQRT12;
  const u = Math.hypot(ua, ub);
  if (!u) return [null, null];
  return [c, (Math.abs(c) * u) / Math.abs(mean)];
}

export function fit(sample, truth, trials, seed0 = 0, granule = null) {
  const raws = [];
  for (let i = 0; i < trials; i++) raws.push(sample(truth, seed0 + i));
  const g = granule === null ? granuleFor(raws) : granule;
  return fromRaws(raws, truth, g);
}

function sd(xs) {
  if (xs.length < 2) return null;
  const m = xs.reduce((a, b) => a + b, 0) / xs.length;
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
}

/** Spread across cases in units of the measurement error. Never divided by magnitude. */
export function heterogeneity(values, errors) {
  const s = sd(values);
  if (s === null) return null;
  const meanE = errors.reduce((a, b) => a + b, 0) / errors.length;
  return meanE <= 0 ? null : s / meanE;
}

/** Earliest rung from which every later rung agrees within k combined errors. */
export function plateau(ladder, k = PLATEAU_K, need = PLATEAU_RUN) {
  const rungs = [...ladder].sort((a, b) => a.truth - b.truth);
  if (rungs.length < need) {
    return { value: UNDETERMINED, se: null, from_truth: null,
             why: `ladder shorter than the required run of ${need}` };
  }
  for (let i = 0; i <= rungs.length - need; i++) {
    const tail = rungs.slice(i);
    const agrees = tail
      .slice(1)
      .every((r) => Math.abs(tail[0].c - r.c) <= k * Math.sqrt(tail[0].se ** 2 + r.se ** 2));
    if (agrees) {
      const w = tail.reduce((a, r) => a + 1 / r.se ** 2, 0);
      return {
        value: tail.reduce((a, r) => a + r.c / r.se ** 2, 0) / w,
        se: Math.sqrt(1 / w),
        from_truth: tail[0].truth,
        why: `${tail.length} rungs from truth=${fmt.sig(tail[0].truth)} agree within ` +
             `${fmt.fixed(k, 1)} sigma`,
      };
    }
  }
  return { value: UNDETERMINED, se: null, from_truth: null,
           why: `no run of ${need} rungs agrees; the constant is still moving at the top ` +
                `of the ladder` };
}

// ------------------------------------------------------------------ the report

/**
 * The ladder, with ONE granule derived across every rung's draws.
 *
 * Sampling happens once. The granule comes from the whole set rather than per rung because
 * it is a property of the instrument, not of a reading, and the whole set can only give a
 * finer answer than its coarsest member.
 */
export function ladderFor(sample, truths, trials, seed0 = 0, into = null) {
  const drawn = truths.map((t) => {
    const raws = [];
    for (let i = 0; i < trials; i++) raws.push(sample(t, seed0 + i));
    return [t, raws];
  });
  const granule = granuleFor(drawn.flatMap(([, raws]) => raws));
  // An out-parameter rather than a widened return type: the return shape is pinned against
  // the Python half and a silent widening is the drift `test_parity.py` exists to stop.
  if (into) {
    into.granule = granule;
    into.scatter_free = drawn.every(([, raws]) =>
      raws.length < 2 || Math.min(...raws) === Math.max(...raws));
  }
  const out = [];
  for (const [t, raws] of drawn) {
    const [c, se] = fromRaws(raws, t, granule);
    if (c !== null && se) out.push({ truth: t, c, se });
  }
  return out;
}

/**
 * Every observable must answer the same for the same (truth, seed), or refuse.
 *
 * THE PRECONDITION NOTHING ELSE HERE CAN SUBSTITUTE FOR. `fit` averages an observable
 * over `trials` DIFFERENT seeds, so an observable that ignores its seed and reads the
 * clock or an unseeded RNG produces a mean over noise — and a mean over noise still has
 * a standard error, still forms a ladder, and can still plateau. Every guard downstream
 * compares against that error, so a broken adapter does not produce a wrong-looking
 * answer: it produces a confident one.
 *
 * A throw, not an `undetermined`. The other refusals here describe what the program
 * would not reveal; this one says the instrument was wired up wrong.
 *
 * Its numbers go through `fmt` like every other number this package prints, at ALL_DIGITS
 * rather than six: the message exists to say that two values differed, and six
 * significant digits would render a pair that differs in the tenth as one string twice.
 */
export function reproducible(obs, truths, seed0 = 17) {
  const names = Object.keys(obs).sort();
  const rungs = truths.length ? [...new Set([truths[0], truths[truths.length - 1]])] : [];
  const whole = fmt.ALL_DIGITS;
  for (const name of names) {
    for (const truth of rungs) {
      const first = obs[name](truth, seed0);
      const second = obs[name](truth, seed0);
      if (!Object.is(first, second)) {
        throw new Error(
          `observable \`${name}\` is not reproducible: at truth=${fmt.sig(truth, whole)} ` +
          `and seed=${fmt.sig(seed0, whole)} it returned ${fmt.sig(first, whole)} and ` +
          `then ${fmt.sig(second, whole)}. Every constant below is fitted from a mean ` +
          `over seeds, so an observable that ignores its seed yields a mean over noise ` +
          `-- which still plateaus, and would be reported as an answer.`
        );
      }
    }
  }
}

/** The whole report. Nothing here knows what program it is looking at. */
export function characterize(adapter, { trials = 2500, seed0 = 17, determinism = null, granules = null } = {}) {
  const truths = [...adapter.truths()];
  const obs = adapter.observables;
  if (Object.keys(obs).length < 2) {
    throw new Error(
      "an adapter must expose at least two observables, or there is no choice to make " +
      "and the tool cannot be shown to make one"
    );
  }
  reproducible(obs, truths, seed0);

  const per = {};
  for (const [name, f] of Object.entries(obs)) {
    const seen = {};
    const lad = ladderFor(f, truths, trials, seed0, seen);
    const p = plateau(lad);
    per[name] = {
      ladder: lad, plateau: p,
      granule: seen.granule ?? null, scatter_free: seen.scatter_free ?? null,
      constant: p.value, constant_se: p.se, regime_from: p.from_truth,
      top_rung: lad.length ? lad[lad.length - 1].c : null,
      top_rung_se: lad.length ? lad[lad.length - 1].se : null,
    };
  }

  // Which observable carries information about THIS instance? Only answerable with more
  // than one instance; with one, say so rather than guessing.
  let informative = {
    choice: UNDETERMINED,
    why: "only one instance was supplied, so no constant can be shown to vary across " +
         "instances; supply >=2 to decide",
  };
  if (typeof adapter.instances === "function") {
    const vals = {}, errs = {};
    for (const name of Object.keys(obs)) {
      const vs = [], es = [];
      for (const sub of adapter.instances()) {
        const [c, se] = fit(sub.observables[name], truths[truths.length - 1], trials, seed0);
        if (c !== null && se) { vs.push(c); es.push(se); }
      }
      vals[name] = vs; errs[name] = es;
    }
    const ratios = {};
    for (const n of Object.keys(obs)) ratios[n] = heterogeneity(vals[n], errs[n]);
    informative = pick(ratios);
    informative.ratios = ratios;
  }

  // Does anything respond to perturbing the program itself?
  const response = {};
  if (adapter.knobs && typeof adapter.perturbed === "function") {
    for (const name of Object.keys(obs)) {
      response[name] = {};
      for (const [knob, values] of Object.entries(adapter.knobs)) {
        const pts = [];
        for (const v of values) {
          const [c] = fit(adapter.perturbed(knob, v)[name], truths[truths.length - 1],
                          Math.max(400, Math.floor(trials / 4)), seed0);
          if (c && c > 0) pts.push([Math.log(v), Math.log(c)]);
        }
        response[name][knob] = slope(pts);
      }
    }
  }

  const undetermined = Object.keys(obs).filter((n) => per[n].constant === UNDETERMINED);
  const seam = seamFor(obs, per, determinism || {}, granules || {});
  return {
    observables: Object.keys(obs).sort(),
    per_observable: per,
    informative,
    perturbation_response: response,
    undetermined,
    seam,
    notes: notes(per, informative, undetermined, seam),
  };
}

function slope(pts) {
  if (pts.length < 2) return null;
  const mx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const my = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  const den = pts.reduce((a, p) => a + (p[0] - mx) ** 2, 0);
  return den <= 0 ? null : pts.reduce((a, p) => a + (p[0] - mx) * (p[1] - my), 0) / den;
}

function pick(ratios) {
  const usable = Object.entries(ratios).filter(([, v]) => v !== null && v !== undefined);
  const live = usable.filter(([, v]) => v >= MIN_RATIO);
  if (!live.length) {
    return { choice: UNDETERMINED,
             why: `no constant varies beyond ${fmt.fixed(MIN_RATIO, 0)}x its own error ` +
                  `across instances` };
  }
  const rank = live.sort((a, b) => b[1] - a[1]);
  if (rank.length > 1 && rank[0][1] < MIN_MARGIN * rank[1][1]) {
    return { choice: UNDETERMINED,
             why: `${rank[0][0]} (${fmt.fixed(rank[0][1], 1)}) does not beat ` +
                  `${rank[1][0]} (${fmt.fixed(rank[1][1], 1)}) by ` +
                  `${fmt.fixed(MIN_MARGIN, 0)}x` };
  }
  return { choice: rank[0][0],
           why: `${rank[0][0]} varies ${fmt.fixed(rank[0][1], 1)}x its own error` };
}

/**
 * {observable: {route, state, verdict, why}} -- why each silence is the silence it is.
 *
 * Only an observable that came back UNDETERMINED can carry the ask. One that produced a
 * constant is not missing a resolution, and overwriting its explanation would trade a true
 * sentence for one the tool cannot support.
 */
function seamFor(obs, per, determinism, granules) {
  const out = {};
  for (const name of Object.keys(obs)) {
    const state = Object.prototype.hasOwnProperty.call(determinism, name)
      ? determinism[name] : "unprobed";
    const declared = Object.prototype.hasOwnProperty.call(granules, name);
    const where = route(state, declared);
    const entry = { route: where, state, granule_declared: declared, verdict: null, why: null };
    if (where === ASK && per[name].constant === UNDETERMINED) {
      entry.verdict = DETERMINISTIC_NO_RESOLUTION;
      entry.why = askText(name, per[name].granule);
    }
    out[name] = entry;
  }
  return out;
}

function notes(per, informative, undetermined, seam = null) {
  const out = [];
  for (const n of [...undetermined].sort()) {
    const asked = seam && seam[n] ? seam[n].verdict : null;
    if (asked) { out.push(`\`${n}\`: ${asked} -- ${seam[n].why}`); continue; }
    out.push(`\`${n}\`: no plateau -- ${per[n].plateau.why}`);
  }
  if (informative.choice === UNDETERMINED) {
    out.push(`which observable characterises the program: UNDETERMINED -- ${informative.why}`);
  }
  return out;
}
