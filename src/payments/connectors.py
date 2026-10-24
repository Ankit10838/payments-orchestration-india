import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# Provider-side problems: safe to retry on another provider.
RETRYABLE = {"provider_down", "timeout", "issuer_unavailable"}
# Customer-side outcomes: retrying elsewhere would not help (and may annoy the customer).
NON_RETRYABLE = {"insufficient_funds"}


@dataclass
class ProviderResult:
    status: str  # succeeded | failed | pending
    error_code: Optional[str] = None
    provider_ref: Optional[str] = None
    latency_ms: int = 0


class Connector(ABC):
    """Contract every provider adapter implements."""

    name: str
    methods: set
    priority: int = 1
    cost_bps: int = 100

    @abstractmethod
    def create_payment(self, reference: str, amount: int, method: str) -> ProviderResult: ...

    @abstractmethod
    def refund(self, provider_ref: str, amount: int) -> ProviderResult: ...


class MockConnector(Connector):
    """Simulated provider.

    reliability: probability the provider itself works (not down, no timeout).
    customer_decline_rate: probability a reachable provider returns a customer-side decline.
    Overall success probability = reliability * (1 - customer_decline_rate).
    Calls are idempotent on `reference`, like a real provider would be.
    """

    def __init__(self, name, reliability=0.95, customer_decline_rate=0.03,
                 methods=("upi", "card", "netbanking"), latency=(120, 40),
                 priority=1, cost_bps=100, seed=None):
        self.name = name
        self.reliability = reliability
        self.customer_decline_rate = customer_decline_rate
        self.methods = set(methods)
        self.latency = latency
        self.priority = priority
        self.cost_bps = cost_bps
        self.down = False
        self.calls = 0
        self._rng = random.Random(seed)
        self._seen = {}

    def create_payment(self, reference, amount, method):
        if reference in self._seen:
            return self._seen[reference]
        self.calls += 1
        r_provider = self._rng.random()
        r_decline = self._rng.random()
        latency = max(10, int(self._rng.gauss(*self.latency)))
        ref = f"{self.name}_txn_{self.calls}"
        if self.down:
            result = ProviderResult("failed", "provider_down", None, 3000)
        elif r_provider >= self.reliability:
            slow = (r_provider - self.reliability) / max(1e-9, 1 - self.reliability) < 0.5
            result = ProviderResult(
                "failed", "timeout" if slow else "issuer_unavailable", None,
                2500 if slow else latency,
            )
        elif r_decline < self.customer_decline_rate:
            result = ProviderResult("failed", "insufficient_funds", None, latency)
        else:
            result = ProviderResult("succeeded", None, ref, latency)
        self._seen[reference] = result
        return result

    def refund(self, provider_ref, amount):
        if self.down:
            return ProviderResult("failed", "provider_down", None, 3000)
        return ProviderResult("succeeded", None, f"rf_{provider_ref}", 100)
