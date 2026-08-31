"""undetermined — point it at a program, get back what can and cannot be determined.

    from undetermined import characterize, to_tolerance

    report = characterize(MyAdapter(), trials=2500)
    report = to_tolerance(MyAdapter(), tolerance=0.01)   # derive the trial count instead

The name is the differentiator. Plenty of things fit a curve to measurements and hand
back a number; this one has an `undetermined` list with reasons, and will put an
observable on it rather than fit a plateau to a drift.
"""

from . import fmt
from .budget import mde, to_tolerance, trials_for
from .core import (
    UNDETERMINED,
    characterize,
    fit,
    heterogeneity,
    ladder_for,
    plateau,
    reproducible,
)

__all__ = ["characterize", "to_tolerance", "reproducible", "fit", "plateau",
           "heterogeneity", "ladder_for", "mde", "trials_for", "UNDETERMINED", "fmt"]
__version__ = "0.1.3"
