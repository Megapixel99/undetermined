import test from "node:test";
import assert from "node:assert/strict";

import {
  UNDETERMINED, characterize, fit, heterogeneity, ladderFor, mde, plateau,
  toTolerance, trialsFor,
} from "../src/index.js";

/** A tiny seeded RNG, so the fixtures are reproducible by construction. */
function rng(seed) {
  let s = (seed >>> 0) || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5;  s >>>= 0;
    return s / 4294967296;
  };
}

const coin = {
  truths: () => [64, 256, 1024, 4096],
  get observables() {
    return {
      // E[heads] = truth/2, so c = truth / E[heads] = 2 by construction.
      heads: (truth, seed) => {
        const r = rng(seed * 7919 + truth);
        let n = 0;
        for (let i = 0; i < truth; i++) if (r() < 0.5) n++;
        return n || 1;
      },
      // Expectation ~6 whatever the truth is, so c = truth/6 climbs the ladder and
      // never settles. This is the case the tool must refuse.
      flat: (truth, seed) => rng(seed * 104729 + truth)() * 10 + 1,
    };
  },
};

const unseeded = {
  truths: () => [64, 256],
  get observables() {
    return { heads: coin.observables.heads, unseeded: (truth) => Math.random() * truth + 1 };
  },
};

test("a fair coin gives exactly two", () => {
  const r = characterize(coin, { trials: 400 });
  assert.ok(Math.abs(r.per_observable.heads.constant - 2.0) < 0.1,
            `got ${r.per_observable.heads.constant}`);
  assert.ok(r.per_observable.heads.constant_se > 0);
  assert.notEqual(r.per_observable.heads.regime_from, null);
});

test("an observable with no constant is UNDETERMINED, and the other one is not", () => {
  const r = characterize(coin, { trials: 400 });
  assert.ok(r.undetermined.includes("flat"));
  assert.equal(r.per_observable.flat.constant, UNDETERMINED);
  assert.match(r.per_observable.flat.plateau.why, /still moving/);
  // THE CONTROL: a tool that called everything undetermined would pass the line above.
  assert.ok(!r.undetermined.includes("heads"));
});

test("one observable is refused outright", () => {
  assert.throws(
    () => characterize({ truths: () => [1, 2, 3], observables: { a: () => 1 } }),
    /cannot be shown to make one/
  );
});

test("an unseeded observable is refused, and a seeded one is not", () => {
  assert.throws(() => characterize(unseeded, { trials: 50 }),
                /not reproducible[\s\S]*mean over noise/);
  characterize(coin, { trials: 50 });   // the control
});

test("an unseeded observable would otherwise have produced a full ladder", () => {
  // Shown so the precondition is not mistaken for a nicety: without it, THIS is what
  // would have been reported — three rungs, each with a standard error.
  const lad = ladderFor((truth) => Math.random() * truth + 1, [64, 256, 1024], 200);
  assert.equal(lad.length, 3);
  for (const rung of lad) assert.ok(rung.se > 0);
});

test("choosing between instances is UNDETERMINED from one instance", () => {
  const r = characterize(coin, { trials: 200 });
  assert.equal(r.informative.choice, UNDETERMINED);
  assert.match(r.informative.why, /only one instance/);
});

test("heterogeneity is in units of error, never magnitude", () => {
  const small = heterogeneity([1, 2, 3], [0.1, 0.1, 0.1]);
  const large = heterogeneity([1001, 1002, 1003], [0.1, 0.1, 0.1]);
  assert.ok(Math.abs(small - large) < 1e-9);
});

test("a ladder shorter than the run is UNDETERMINED", () => {
  const p = plateau([{ truth: 1, c: 1, se: 0.1 }]);
  assert.equal(p.value, UNDETERMINED);
  assert.match(p.why, /shorter than the required run/);
});

test("fit returns nothing when the mean is zero", () => {
  assert.deepEqual(fit(() => 0, 10, 5), [null, null]);
});

test("the budget: k times too coarse costs k squared trials", () => {
  assert.equal(trialsFor(0.02, 0.01, 1000), 4001);
  assert.equal(trialsFor(0.005, 0.01, 1000), null);
  assert.ok(Math.abs(mde(0.01, 2.0) - 0.015) < 1e-12);
});

test("a tolerance must be supplied", () => {
  assert.throws(() => toTolerance(coin, 0), /will not choose it for you/);
});

test("to_tolerance reports support rather than only a number", () => {
  const r = toTolerance(coin, 0.05, { floor: 200, cap: 1600 });
  assert.ok("supported" in r.per_observable.heads);
  assert.ok("mde" in r.per_observable.heads);
  assert.ok("all_supported" in r.budget);
  assert.ok(r.budget.history.length >= 1);
  // An UNDETERMINED observable is never chased with more trials.
  assert.ok(!r.budget.unsupported.includes("flat"));
});
