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
    ASK,
    DETERMINISTIC_NO_RESOLUTION,
    TYPE_A,
    TYPE_B,
    UNDETERMINED,
    UNPROBED,
    ask_text,
    characterize,
    fit,
    granule_by_probe, granule_for,
    heterogeneity,
    ladder_for,
    plateau,
    reproducible,
    route,
)

__all__ = ["characterize", "to_tolerance", "reproducible", "fit", "plateau",
           "heterogeneity", "ladder_for", "granule_for", "granule_by_probe",
           "mde", "trials_for",
           "UNDETERMINED", "fmt",
           # The determinism seam. A caller supplies the verdict this routes on, so these
           # are the interface rather than internals behind `characterize`.
           "route", "ask_text", "DETERMINISTIC_NO_RESOLUTION",
           "TYPE_A", "TYPE_B", "ASK", "UNPROBED"]
__version__ = "0.2.0"
