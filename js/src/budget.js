/**
 * Spend trials until the answer is supportable, and refuse to report one that is not.
 *
 * `characterize(adapter, {trials})` takes a trial count the caller has to guess. What a
 * derived budget buys is not accuracy — a good guess is just as accurate — it is that
 * there is no guess: the count is computed from the size of effect you said you cared
 * about and the variance actually observed.
 *
 * THE SECOND HALF MATTERS MORE. Every constant carries its MDE — the smallest relative
 * effect a measurement of that precision could have detected — and one whose MDE exceeds
 * the tolerance is reported `supported: false` with what it would cost, instead of being
 * reported as a number. A verdict reached by a measurement that could not have detected
 * the effect deciding it is not a verdict.
 *
 * `tolerance` is a statement of what difference matters. Like a significance level it is
 * part of the question, and it is the one number this module will not choose for you.
 */

import { characterize, UNDETERMINED } from "./core.js";
import * as fmt from "./fmt.js";

export const SIGMAS = 3.0;          // an MDE is this many standard errors
export const FLOOR_TRIALS = 400;
export const CAP_TRIALS = 40000;
export const GROWTH = 2.0;

/** The smallest RELATIVE effect a measurement of this precision could have detected. */
export function mde(se, value) {
  if (se === null || se === undefined) return null;
  if (value === null || value === undefined || value === 0) return null;
  return SIGMAS * Math.abs(se / value);
}

/**
 * How many trials would bring the MDE down to the tolerance.
 *
 * `se` falls as 1/sqrt(N), so being k times too coarse costs k^2 the trials. Returns null
 * when the measurement already supports the claim.
 */
export function trialsFor(currentMde, tolerance, spent) {
  if (currentMde === null || currentMde === undefined) return null;
  if (spent <= 0 || tolerance <= 0) return null;
  if (currentMde <= tolerance) return null;
  return Math.floor(spent * (currentMde / tolerance) ** 2) + 1;
}

function annotate(report, tolerance) {
  let worst = null;
  for (const row of Object.values(report.per_observable)) {
    const m = mde(row.constant_se, row.constant);
    row.mde = m;
    row.tolerance = tolerance;
    row.supported = m !== null && m <= tolerance;
    if (!row.supported) {
      row.why_unsupported =
        m === null
          ? "no constant was determined"
          : `the constant is ${fmt.sig(row.constant)} but this measurement could not ` +
            `have detected a ${fmt.sig(tolerance, 3)} relative effect ` +
            `(MDE ${fmt.sig(m, 3)}), so it does not support a claim at that tolerance`;
      if (m !== null && (worst === null || m > worst)) worst = m;
    }
  }
  return worst;
}

/**
 * Run `characterize`, raising the trial count until every constant it determined is
 * supported at `tolerance`, or the budget is spent.
 *
 * An observable that comes back UNDETERMINED is left alone: no amount of precision turns
 * a ladder that never flattens into a constant, and pretending otherwise is the failure
 * this module exists to avoid.
 */
export function toTolerance(adapter, tolerance, {
  seed0 = 17, floor = FLOOR_TRIALS, cap = CAP_TRIALS, onStep = null,
} = {}) {
  if (!(tolerance > 0)) {
    throw new Error(
      "tolerance must be positive: it is the size of effect you care about, and this " +
      "module will not choose it for you"
    );
  }
  let trials = floor;
  const history = [];
  for (;;) {
    const report = characterize(adapter, { trials, seed0 });
    const worst = annotate(report, tolerance);
    const determined = Object.entries(report.per_observable)
      .filter(([, r]) => r.constant !== UNDETERMINED).map(([n]) => n);
    const unsupported = determined.filter((n) => !report.per_observable[n].supported).sort();
    history.push({ trials, worst_mde: worst, unsupported });
    if (onStep) onStep(history[history.length - 1]);

    const want = unsupported.length ? trialsFor(worst, tolerance, trials) : null;
    if (!unsupported.length || want === null || trials >= cap) {
      report.budget = {
        tolerance, trials, floor, cap,
        all_supported: unsupported.length === 0,
        unsupported, worst_mde: worst, history,
        would_need: want === null ? null : Math.min(want, 1e12),
        shortfall: want === null ? null : Math.round((want / cap) * 100) / 100,
      };
      return report;
    }
    trials = Math.min(cap, Math.max(Math.floor(trials * GROWTH), want));
  }
}
