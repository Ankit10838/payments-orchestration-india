# Payments Orchestration Platform for India

A product case study and reference implementation of a unified payments layer for Indian merchants: one API across UPI, cards, net banking and mandates, with automatic failover and reconciliation.

> **Scope note:** all payment providers are mocked. No real money, credentials or customer data are used. This is a self-driven case study, not a production system.

## The problem

Merchants integrate several payment providers to cover UPI, cards and net banking. When one fails, payments are lost. Each provider has a different API and settlement format, so finance reconciles by hand. _(Link to full problem statement in [docs/PRD.md](docs/PRD.md).)_

## What this project demonstrates

- **Product thinking:** PRD, personas, competitive analysis, regulatory scoping (orchestration layer vs. payment aggregator under RBI rules)
- **API product design:** OpenAPI spec, idempotency, webhooks, error model
- **Payments domain depth:** UPI, card and NACH/mandate flows, settlement and reconciliation
- **Working sandbox:** state machine, routing with failover, ledger, reconciliation job

## Key result

> **Simulated:** with a primary provider at 90% reliability and a 95% backup, failover raised overall payment success from **87.0% to 96.4%** over 10,000 simulated payments. In a simulated 3,000-payment outage of the primary, a circuit breaker cut average latency from **1,135 ms to 243 ms** and calls to the failed provider by about 30%.
> Providers are mocks with stated failure rates, so these are simulation results, not real-traffic measurements. Method, assumptions and limits: [demo/failover-simulation.md](demo/failover-simulation.md).

## Architecture

![Architecture](docs/architecture.png)

Layers: Merchants, API gateway, Core services (payment engine, routing, ledger and reconciliation, webhooks), Connector layer, Providers. See [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
git clone https://github.com/<your-username>/payments-orchestration-india
cd payments-orchestration-india

# Run the tests and the failover simulation (standard library only)
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python demo/simulate_failover.py

# Run the API (needs: pip install -r requirements.txt)
PYTHONPATH=src uvicorn payments.api:app --reload
# or: docker compose up
# Interactive docs: http://localhost:8000/docs   (API key: sk_test_sandbox)
```

## Example

```bash
curl -X POST http://localhost:8000/v1/payment_intents \
  -H "Authorization: Bearer sk_test_sandbox" \
  -H "Idempotency-Key: order_1001" \
  -H "Content-Type: application/json" \
  -d '{"amount": 49900, "currency": "INR", "method": "upi"}'
```

## Repository layout

```
docs/       PRD, regulatory scoping, architecture, flow diagrams, wireframes
api/        OpenAPI spec, Postman collection
src/payments/  engine, state machine, router + circuit breaker, mock connectors, ledger, webhooks, FastAPI layer
tests/         unit tests (idempotency, failover, refunds, ledger, circuit breaker, webhook signing)
demo/          failover simulation script and results
recon/         (planned) settlement files and reconciliation job
```

## Key product decisions

1. **Orchestration, not aggregation:** avoids holding funds and the RBI payment aggregator capital requirements.
2. **Idempotency first:** retries must never double-charge.
3. **Append-only events and ledger:** every state change is auditable.
4. **MVP cuts:** no real providers, no raw card storage, no cross-border.

## Roadmap

- [x] PRD and regulatory scoping (draft; TODOs need sourced research)
- [x] OpenAPI spec
- [x] Sandbox: payment intents, state machine, mock connectors
- [x] Routing, circuit breaker and failover simulation
- [x] Ledger (double-entry)
- [ ] Reconciliation against settlement files
- [ ] UPI AutoPay / NACH mandate flows
- [ ] Dashboard wireframes

## About

Built by [Ankit Sharma](https://www.linkedin.com/in/your-profile) _(add your link)_. Background: digital banking product and API integration.
