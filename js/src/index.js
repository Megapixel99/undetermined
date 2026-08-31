/**
 * undetermined — point it at a program, get back what can and cannot be determined.
 *
 * The name is the differentiator. Plenty of things fit a curve to measurements and hand
 * back a number; this one has an `undetermined` list with reasons, and will put an
 * observable on it rather than fit a plateau to a drift.
 */

export {
  UNDETERMINED, MIN_RATIO, MIN_MARGIN, PLATEAU_K, PLATEAU_RUN,
  characterize, fit, plateau, heterogeneity, ladderFor, granuleFor, reproducible,
} from "./core.js";

// The shared formatter. Both halves print every user-visible number through it, and
// `python/tests/test_parity.py` compares them digit for digit.
export * as fmt from "./fmt.js";

export {
  SIGMAS, FLOOR_TRIALS, CAP_TRIALS, GROWTH, mde, trialsFor, toTolerance,
} from "./budget.js";
