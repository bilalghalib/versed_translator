"""The harness result type, defined outside ``adapters/`` on purpose.

``TranslationResult`` started life in ``adapters/base.py``, which was right
while adapters were its only producer. The structured-block contract
(``harness.structured``) now produces them too, and importing
``adapters.base`` from there is not free: it initialises the ``adapters``
package, which imports every adapter, each of which imports
``harness.structured`` -- a circular import that fails at run time while
passing under pytest, because pytest happens to import the modules in a
luckier order. (It did exactly that here.)

So the type lives here, depending on nothing, and ``adapters/base.py``
re-exports it: every existing ``from ...adapters.base import
TranslationResult`` keeps working, and the cycle is gone.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TranslationResult:
    item_id: str
    translation: str | None
    source_tokens: int | None
    output_tokens: int | None
    latency_s: float | None
    error: str | None = None
    # Adapters that know their provider's prices fill this in (see each
    # adapter's PRICE_TABLE); local/self-hosted adapters leave it None and
    # the run's GPU-hour cost is accounted for separately in throughput/.
    cost_estimate: float | None = None


class AdapterError(RuntimeError):
    """Raised for adapter-level setup failures (e.g. missing API key).

    Adapters should fail loudly (raise) for configuration problems that
    block the whole run, but capture per-item failures (a single bad
    response, a network hiccup on one call) as an ``error`` string on that
    item's TranslationResult instead of raising, so one bad item doesn't
    abort an entire batch.
    """
