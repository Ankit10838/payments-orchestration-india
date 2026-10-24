import time
from collections import deque

from .connectors import NON_RETRYABLE, RETRYABLE


class CircuitBreaker:
    """Stops sending traffic to a provider that keeps failing.

    closed -> open when success rate over the last `window` provider-side outcomes
    drops below `threshold` (after `min_samples`). After `cooldown_s` it goes half_open;
    the next outcome closes it (success) or re-opens it (failure).
    """

    def __init__(self, window=50, min_samples=20, threshold=0.5, cooldown_s=30, clock=time.time):
        self.results = deque(maxlen=window)
        self.min_samples = min_samples
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.clock = clock
        self.state = "closed"
        self.opened_at = 0.0

    def available(self):
        if self.state == "open" and self.clock() - self.opened_at >= self.cooldown_s:
            self.state = "half_open"
        return self.state != "open"

    def record(self, ok):
        if self.state == "half_open":
            if ok:
                self.state = "closed"
                self.results.clear()
            else:
                self._open()
            return
        self.results.append(ok)
        if len(self.results) >= self.min_samples and self.success_rate() < self.threshold:
            self._open()

    def success_rate(self):
        return sum(self.results) / len(self.results) if self.results else 1.0

    def _open(self):
        self.state = "open"
        self.opened_at = self.clock()


class Router:
    """Chooses provider order for a payment.

    mode "priority": configured priority first (predictable, good for demos and contracts).
    mode "success_rate": rolling success rate first, cost as tie-break.
    Providers with an open circuit are skipped in both modes.
    """

    def __init__(self, connectors, mode="priority", use_circuit_breaker=True,
                 clock=time.time, **breaker_kwargs):
        self.connectors = list(connectors)
        self.mode = mode
        self.use_circuit_breaker = use_circuit_breaker
        self.breakers = {c.name: CircuitBreaker(clock=clock, **breaker_kwargs) for c in self.connectors}

    def rank(self, method, preferred=None):
        candidates = [c for c in self.connectors if method in c.methods]
        if self.use_circuit_breaker:
            candidates = [c for c in candidates if self.breakers[c.name].available()]
        if self.mode == "success_rate":
            key = lambda c: (c.name != preferred, -self.breakers[c.name].success_rate(), c.cost_bps)
        else:
            key = lambda c: (c.name != preferred, c.priority, c.cost_bps)
        return sorted(candidates, key=key)

    def record(self, provider, result):
        """Feed provider-side health only. Customer declines mean the provider is healthy."""
        if result.status == "succeeded" or result.error_code in NON_RETRYABLE:
            self.breakers[provider].record(True)
        elif result.error_code in RETRYABLE:
            self.breakers[provider].record(False)
