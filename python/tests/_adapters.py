"""Adapters with a known answer, so the tool is graded rather than admired."""

import random


class CoinAdapter:
    """Two observables over a fair coin: one carries a constant, one is pure noise.

    `heads` has expectation truth/2, so c = truth / E[heads] = 2 exactly.

    `flat` has an expectation that does NOT depend on the truth, so c = truth / E[flat]
    grows with every rung and never settles. That is the case the tool must report as
    UNDETERMINED rather than fit. The first version of this fixture used
    `random() * truth`, whose expectation is truth/2 -- which carries the SAME constant
    as `heads`, so the refusal path was never exercised and the test proved half of what
    it claimed.
    """

    def truths(self):
        return [64, 256, 1024, 4096]

    @property
    def observables(self):
        return {"heads": self._heads, "flat": self._flat}

    @staticmethod
    def _heads(truth, seed):
        rng = random.Random(seed * 7919 + truth)
        return sum(rng.random() < 0.5 for _ in range(truth)) or 1

    @staticmethod
    def _flat(truth, seed):
        # Expectation ~6 whatever the truth is, so c = truth/6 climbs the ladder.
        rng = random.Random(seed * 104729 + truth)
        return rng.random() * 10.0 + 1.0


class UnseededAdapter(CoinAdapter):
    """One observable ignores its seed. The whole report would be a mean over noise."""

    @property
    def observables(self):
        return {"heads": self._heads, "unseeded": self._unseeded}

    @staticmethod
    def _unseeded(truth, seed):
        return random.random() * truth + 1.0      # note: no seed used


class SingleObservableAdapter(CoinAdapter):
    @property
    def observables(self):
        return {"heads": self._heads}


class DeterministicAdapter:
    """The case 0.1.0 could not answer at all, with the control that keeps it honest.

    `exact` answers the same number for every seed and carries the constant 7 by
    construction. `drifting` is equally deterministic and carries NO constant of this form:
    its expectation grows as truth**0.37, so `truth / E[drifting]` climbs every rung.

    The pair is the point. A fix that makes `exact` recoverable by widening error bars would
    make `drifting` recoverable too, and a tool that reports a plateau for `drifting` is a
    way of finding constants that are not there.
    """

    def truths(self):
        return [64, 256, 1024, 4096]

    @property
    def observables(self):
        return {"exact": self._exact, "drifting": self._drifting}

    @staticmethod
    def _exact(truth, seed):
        return truth / 7.0

    @staticmethod
    def _drifting(truth, seed):
        return 1000.0 * truth ** 0.37
