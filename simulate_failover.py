"""Failover simulation. All providers are mocked; results are simulated, not real traffic.

Run:  PYTHONPATH=src python demo/simulate_failover.py
Writes demo/failover-simulation.md
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from payments.connectors import MockConnector  # noqa: E402
from payments.engine import PaymentEngine  # noqa: E402
from payments.models import Status  # noqa: E402
from payments.router import Router  # noqa: E402

N = 10_000
RELIABILITY_A, RELIABILITY_B = 0.90, 0.95
DECLINE_RATE = 0.03
OUTAGE = (3_000, 6_000)  # payments during which provider A is fully down
SECONDS_PER_PAYMENT = 0.05


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def run(name, use_b, outage, breaker):
    clock = Clock()
    a = MockConnector("provider_a", RELIABILITY_A, DECLINE_RATE, priority=1, seed=11)
    b = MockConnector("provider_b", RELIABILITY_B, DECLINE_RATE, priority=2, seed=22)
    connectors = [a, b] if use_b else [a]
    router = Router(connectors, use_circuit_breaker=breaker, clock=clock)
    engine = PaymentEngine(connectors, router=router, clock=clock, max_attempts=3)
    methods = ["upi"] * 6 + ["card"] * 3 + ["netbanking"]
    ok = recovered = provider_failed = attempts = 0
    latencies = []
    for i in range(N):
        clock.t += SECONDS_PER_PAYMENT
        a.down = bool(outage and OUTAGE[0] <= i < OUTAGE[1])
        body = {"amount": 49900, "currency": "INR", "method": methods[i % 10]}
        if body["method"] == "card":
            body["card"] = {"token": "tok_test"}
        intent, _ = engine.create_payment_intent(f"sim_{i}", body)
        attempts += len(intent.attempts)
        latencies.append(sum(x.latency_ms for x in intent.attempts))
        if intent.status == Status.SUCCEEDED:
            ok += 1
            recovered += len(intent.attempts) > 1
        elif intent.failure_code in ("timeout", "issuer_unavailable", "provider_down", "no_provider_available"):
            provider_failed += 1
    latencies.sort()
    return {"name": name, "success": ok / N * 100, "recovered": recovered,
            "provider_failed": provider_failed, "attempts": attempts / N,
            "avg_ms": sum(latencies) / N, "p95_ms": latencies[int(0.95 * N)], "a_calls": a.calls}


def main():
    rows = [
        run("1. Provider A only", False, False, True),
        run("2. A + B failover", True, False, True),
        run("3. Outage of A, failover, no circuit breaker", True, True, False),
        run("4. Outage of A, failover, with circuit breaker", True, True, True),
    ]
    header = ("| Scenario | Success rate | Recovered by failover | Lost to provider errors "
              "| Avg attempts | Avg latency (ms) | p95 latency (ms) | Calls to A |\n|---|---|---|---|---|---|---|---|\n")
    table = header + "".join(
        f"| {r['name']} | {r['success']:.1f}% | {r['recovered']:,} | {r['provider_failed']:,} | "
        f"{r['attempts']:.2f} | {r['avg_ms']:.0f} | {r['p95_ms']:,} | {r['a_calls']:,} |\n" for r in rows)
    doc = f"""# Failover simulation results

> **Simulated results.** All providers are mocks with configured failure rates. These numbers show how
> the routing logic behaves under stated assumptions; they are not measurements of real payment traffic.

## Setup

- {N:,} payments per scenario (60% UPI, 30% card, 10% net banking), amount INR 499.00
- Provider A reliability {RELIABILITY_A:.0%}, provider B reliability {RELIABILITY_B:.0%} (reliability = probability the provider itself responds correctly)
- Customer-side declines (insufficient funds) at {DECLINE_RATE:.0%} on both providers; these are never retried elsewhere
- Failover only on provider-side errors (`timeout`, `issuer_unavailable`, `provider_down`); max 3 attempts, one per provider
- Scenarios 3 and 4: provider A is fully down for payments {OUTAGE[0]:,} to {OUTAGE[1]:,}
- Circuit breaker: opens when success rate over the last 50 provider outcomes falls below 50% (minimum 20 samples); 30 s cooldown, then one probe
- Fixed random seeds, so results are reproducible

## Results

{table}
## What this shows

- Adding a second provider with failover recovers payments that fail for provider-side reasons only. Customer declines stay as failures by design.
- During an outage, the circuit breaker stops wasted calls to A. Compare the "Calls to A", average attempts and latency columns for scenarios 3 and 4.

## Limits of this simulation

- Failures are independent random events; real outages are bursty and correlated across payment methods and banks.
- No real network latency, rate limits, or provider-specific error behavior.
- Costs are not modelled, so routing here is by priority rather than price.

Reproduce: `PYTHONPATH=src python demo/simulate_failover.py`
"""
    out = os.path.join(os.path.dirname(__file__), "failover-simulation.md")
    with open(out, "w") as f:
        f.write(doc)
    print(table)


if __name__ == "__main__":
    main()
