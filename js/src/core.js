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
export function fit(sample, truth, trials, seed0 = 0) {
  const raws = [];
  for (let i = 0; i < trials; i++) raws.push(sample(truth, seed0 + i));
  const mean = raws.reduce((a, b) => a + b, 0) / raws.length;
  if (mean === 0) return [null, null];
  const c = truth / mean;
  const varr =
    raws.length > 1
      ? raws.reduce((a, r) => a + (r - mean) ** 2, 0) / (raws.length - 1)
      : 0;
  const cv = Math.sqrt(varr) / Math.abs(mean);
  return [c, (Math.abs(c) * cv) / Math.sqrt(raws.length)];
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

export function ladderFor(sample, truths, trials, seed0 = 0) {
  const out = [];
  for (const t of truths) {
    const [c, se] = fit(sample, t, trials, seed0);
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
 */
export function reproducible(obs, truths, seed0 = 17) {
  const names = Object.keys(obs).sort();
  const rungs = truths.length ? [...new Set([truths[0], truths[truths.length - 1]])] : [];
  for (const name of names) {
    for (const truth of rungs) {
      const first = obs[name](truth, seed0);
      const second = obs[name](truth, seed0);
      if (!Object.is(first, second)) {
        throw new Error(
          `observable ${JSON.stringify(name)} is not reproducible: at truth=${truth} and ` +
          `seed=${seed0} it returned ${first} and then ${second}. Every constant below is ` +
          `fitted from a mean over seeds, so an observable that ignores its seed yields a ` +
          `mean over noise — which still plateaus, and would be reported as an answer.`
        );
      }
    }
  }
}

/** The whole report. Nothing here knows what program it is looking at. */
export function characterize(adapter, { trials = 2500, seed0 = 17 } = {}) {
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
    const lad = ladderFor(f, truths, trials, seed0);
    const p = plateau(lad);
    per[name] = {
      ladder: lad, plateau: p,
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
  return {
    observables: Object.keys(obs).sort(),
    per_observable: per,
    informative,
    perturbation_response: response,
    undetermined,
    notes: notes(per, informative, undetermined),
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

function notes(per, informative, undetermined) {
  const out = [];
  for (const n of [...undetermined].sort()) {
    out.push(`\`${n}\`: no plateau -- ${per[n].plateau.why}`);
  }
  if (informative.choice === UNDETERMINED) {
    out.push(`which observable characterises the program: UNDETERMINED -- ${informative.why}`);
  }
  return out;
}
