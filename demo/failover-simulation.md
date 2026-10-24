# Failover simulation results

> **Simulated results.** All providers are mocks with configured failure rates. These numbers show how
> the routing logic behaves under stated assumptions; they are not measurements of real payment traffic.

## Setup

- 10,000 payments per scenario (60% UPI, 30% card, 10% net banking), amount INR 499.00
- Provider A reliability 90%, provider B reliability 95% (reliability = probability the provider itself responds correctly)
- Customer-side declines (insufficient funds) at 3% on both providers; these are never retried elsewhere
- Failover only on provider-side errors (`timeout`, `issuer_unavailable`, `provider_down`); max 3 attempts, one per provider
- Scenarios 3 and 4: provider A is fully down for payments 3,000 to 6,000
- Circuit breaker: opens when success rate over the last 50 provider outcomes falls below 50% (minimum 20 samples); 30 s cooldown, then one probe
- Fixed random seeds, so results are reproducible

## Results

| Scenario | Success rate | Recovered by failover | Lost to provider errors | Avg attempts | Avg latency (ms) | p95 latency (ms) | Calls to A |
|---|---|---|---|---|---|---|---|
| 1. Provider A only | 87.0% | 0 | 1,021 | 1.00 | 242 | 2,500 | 10,000 |
| 2. A + B failover | 96.4% | 941 | 53 | 1.10 | 261 | 2,556 | 10,000 |
| 3. Outage of A, failover, no circuit breaker | 95.1% | 3,420 | 183 | 1.37 | 1135 | 3,162 | 10,000 |
| 4. Outage of A, failover, with circuit breaker | 95.1% | 676 | 185 | 1.07 | 243 | 303 | 7,005 |

## What this shows

- Adding a second provider with failover recovers payments that fail for provider-side reasons only. Customer declines stay as failures by design.
- During an outage, the circuit breaker stops wasted calls to A. Compare the "Calls to A", average attempts and latency columns for scenarios 3 and 4.

## Limits of this simulation

- Failures are independent random events; real outages are bursty and correlated across payment methods and banks.
- No real network latency, rate limits, or provider-specific error behavior.
- Costs are not modelled, so routing here is by priority rather than price.

Reproduce: `PYTHONPATH=src python demo/simulate_failover.py`
