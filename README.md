# undetermined

[![PyPI](https://img.shields.io/pypi/v/undetermined?label=PyPI&color=3775A9)](https://pypi.org/project/undetermined/)
[![npm](https://img.shields.io/npm/v/undetermined?label=npm&color=CB3837)](https://www.npmjs.com/package/undetermined)
[![ci](https://github.com/Megapixel99/undetermined/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Megapixel99/undetermined/actions/workflows/ci.yml)
[![license MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Point it at a program; get back what can and cannot be determined about it.**

Plenty of libraries fit a curve to measurements and hand you back a number. This one
hands back a number *with the error bar it was decided by*, plus an explicit
`undetermined` list with a reason on each entry — and it will put an observable on that
list rather than fit a plateau to a drift.

```
heads: 1.9978 +/- 0.0032   4 rungs from truth=8 agree within 2.0 sigma
flat:  UNDETERMINED        no run of 3 rungs agrees; the constant is still moving
                           at the top of the ladder
```

The second line is the point. A tool that always produced the first line would be
useless and would still pass every test that checks it produces one.

Ships as `undetermined` on **PyPI** and on **npm**, from one tree, at one version. No
dependencies in either half.

---

## Install

```bash
pip install undetermined
```

```bash
npm install undetermined
```

## Use

You supply an **adapter**: an object that knows how to run the thing you are measuring
at a controllable input size, and nothing else. This library never knows what program it
is looking at.

```python
import random
from undetermined import characterize

class Coin:
    def truths(self):
        # The controllable input values, known by construction. A ladder, not a point:
        # a constant that is only measured at one size cannot be shown to have settled.
        return [8, 32, 128, 512]

    @property
    def observables(self):
        def heads(truth, seed):
            r = random.Random(seed)
            return sum(1 for _ in range(truth) if r.random() < 0.5)

        def flat(truth, seed):
            r = random.Random(seed)
            return sum(1 for _ in range(12) if r.random() < 0.5) + 0.5

        return {"heads": heads, "flat": flat}

report = characterize(Coin(), trials=2500)

report["per_observable"]["heads"]["constant"]      # 1.9978...
report["per_observable"]["heads"]["constant_se"]   # 0.0032...
report["undetermined"]                             # ['flat']
report["notes"]                                    # why each one is on the list
```

```js
import { characterize } from "undetermined";

const report = characterize(adapter, { trials: 2500 });
report.per_observable.heads.constant;   // 1.9978...
report.undetermined;                    // ['flat']
```

### The adapter protocol

| member | required | meaning |
| --- | --- | --- |
| `truths()` | yes | the controllable input values, known by construction |
| `observables` | yes | `{name: (truth, seed) -> number}`, at least two |
| `instances()` | no | sibling instances of the same family |
| `knobs` | no | `{name: [values]}` — parameters of the program itself |
| `perturbed(knob, v)` | with `knobs` | the observables with that knob set to that value |

At least two observables, always. With one there is no choice to make, so the library
cannot be shown to make one — it raises rather than reporting a confident single answer.

### Deriving the trial count instead of guessing it

`characterize` takes a `trials` count. If you would rather state the precision you need
and have the budget derived:

```python
from undetermined import to_tolerance
report = to_tolerance(MyAdapter(), tolerance=0.01)   # 1% on the constant
```

It doubles the trial count until every determined constant is inside the tolerance or the
cap is reached, and reports which ones never got there. `tolerance=0` raises: a tolerance
is a decision about your problem, and this library will not choose it for you.

---

## What it refuses, and why

Three refusals, and each is the answer to a way of being confidently wrong.

**An observable that ignores its seed** raises immediately. `fit` averages an observable
over `trials` *different* seeds, so an observable that reads the clock or an unseeded RNG
produces a mean over noise. A mean over noise still has a standard error, still forms a
ladder, and can still plateau — every guard downstream compares against that error, so a
broken adapter does not produce a wrong-looking answer, it produces a **confident** one.
Each observable is called twice with the same `(truth, seed)` at the first and last rung;
a disagreement is a wiring error, not a finding, so it throws.

**A constant that never settles** is reported as `UNDETERMINED` with the reason. A run of
three consecutive rungs must agree within two combined standard errors before any
plateau is reported; the value is then the inverse-variance-weighted mean over that run,
and the report says which rung it started from.

**A choice between observables that is not earned** is reported as `UNDETERMINED`. With
`instances()`, an observable is only called informative if its constant varies at least
3x its own measurement error across instances, and it is only *chosen* over the runner-up
if it beats it by 3x. Two observables that both vary a lot are not a choice.

### The rule underneath all of it

> Compare against the **noise**, never against the **size**.

A spread only means something in units of the error on the thing that spread. Dividing by
the magnitude instead is how a large number gets mistaken for a real one, and it is the
single mistake this library is shaped around not making.

### The thresholds

They are the contract, and `python/tests/test_parity.py` asserts both halves hold the
same ones and produce the same output on the same numbers — including the same
explanatory strings.

| constant | value | what it gates |
| --- | --- | --- |
| `PLATEAU_K` | 2.0 | sigma within which rungs must agree |
| `PLATEAU_RUN` | 3 | consecutive agreeing rungs required |
| `MIN_RATIO` | 3.0 | error-multiples an observable must vary by to be informative |
| `MIN_MARGIN` | 3.0 | factor by which the winner must beat the runner-up |
| `SIGMAS` | 3.0 | standard errors in a minimum detectable effect |
| `FLOOR_TRIALS` / `CAP_TRIALS` | 400 / 40000 | the budget search bounds |

### One formatter

The `why` strings are part of that contract — a consumer that quotes one is quoting both
halves — so every number they carry is rendered by a rule this package writes out rather
than by whatever each language's `printf` does. `%g` and `toPrecision(6)` agree only on
integers below 10^6 and non-integers in `[1e-4, 1e6)`; `%.1f` and `toFixed(1)` round
halves in opposite directions. The rule lives in `undetermined.fmt` (Python) and
`undetermined/fmt` (npm), and both halves are also pinned to the same expected strings
independently, because two halves that had drifted together would still agree with each
other:

| | |
| --- | --- |
| the digits | the shortest decimal that round-trips to the double — `repr` and `String` both produce exactly that, and agree |
| rounding | half **away from zero**, applied to those digits |
| an exact integer | written out in full, never rounded and never in exponent form: a rung at `16777216` is not clarified by calling it `1.67772e+07` |
| anything else | 6 significant digits, trailing zeros stripped, exponent notation outside `[1e-4, 1e6)` with the exponent padded to two places |

---

## This is a library, not a CLI

An adapter is a code object with closures in it. There is nothing to pass on a command
line that would not amount to naming a Python or JavaScript symbol and importing it, so
the package ships an import and no console script.

## Where it sits

**Layer 0**: no dependencies inside or outside this network of packages, by design.

The `nondet` edge was considered and **rejected**. `nondet` addresses a function as
`FILE::NAME` so it can re-run it in fresh processes; this library's observables are
closures inside an adapter object and have no such address, so `nondet` cannot probe
them. Wiring it in would have meant either a fake file path or a check that never ran —
a dependency that looks like a guarantee and is not. The reproducibility precondition is
implemented natively in both halves instead, and it is checked in the same call that
would have needed the guarantee. `nondet` remains the right tool for the *functions your
adapter calls*, which do have addresses; running it on those is a good idea and is not
something this package can do on your behalf.

## Development

```bash
python3 -m unittest discover -s python/tests -v   # PYTHONPATH=python
node --test js/test/*.test.js
```

The parity suite skips when `node` is not on PATH, so a Python-only contributor can still
run everything else. CI asserts it was **not** skipped — a skipped test and a passing one
look identical in a tally.

## License

MIT
