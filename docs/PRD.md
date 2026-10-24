# PRD: Payments Orchestration Platform for India

> Self-driven product case study. All providers are mocked; no real money, keys or merchant data are used.
> Items marked **TODO** need your own research or numbers. Don't invent figures; cite sources or label them as assumptions.

| | |
|---|---|
| Author | Ankit Sharma |
| Status | Draft v0.1 |
| Last updated | _(date)_ |

---

## 1. Problem statement

Indian merchants and fintechs accept payments through UPI, cards, net banking, wallets and NACH mandates. Each method is reached through one or more payment aggregators, gateways or banks, each with its own API, error codes, settlement files and uptime.

Teams that integrate directly with several providers face:

- **Lost revenue:** when one provider or bank is down, payments fail with no automatic fallback.
- **Integration cost:** every new provider means new code, testing and maintenance.
- **Reconciliation pain:** settlement files differ per provider, so finance teams match payments manually.
- **Vendor lock-in:** switching providers means re-integrating.

**TODO:** add 2-3 sourced data points (e.g. UPI success-rate or downtime reports, merchant survey, public articles). Cite the source for each.

## 2. Target users (personas)

| Persona | Needs | Pain today |
|---|---|---|
| Merchant developer | One clean API and SDK for all methods | Integrating and maintaining multiple providers |
| Merchant finance/ops | Single view of payments, settlements, refunds | Manual reconciliation across providers |
| Product/payments head | Higher success rate, lower cost, provider flexibility | No data-driven routing, vendor dependence |

**TODO:** pick one primary persona and say why (suggestion: mid-size D2C/SaaS merchant already using 2+ providers).

## 3. Goals and non-goals

**Goals (MVP)**
1. One unified API for UPI, card and net banking payments, plus mandate creation.
2. Automatic failover between providers when one fails.
3. Idempotent, auditable payment lifecycle.
4. Daily reconciliation against provider settlement files.
5. Webhooks to merchants with signed, retried events.

**Non-goals (MVP)**
- Holding or settling merchant funds (we are **not** a payment aggregator).
- Storing raw card data (tokenised only; PCI scope kept minimal).
- Lending, BNPL, cross-border payments.
- Real provider integrations (mock connectors only).

## 4. Regulatory scoping

The key product decision: **orchestration layer, not aggregator.**

- A payment aggregator that collects and settles funds needs RBI authorisation and minimum net worth (₹15 crore at application, ₹25 crore by the third financial year).
- An orchestration layer routes requests to licensed providers; funds flow provider to merchant directly.
- Trade-off: lower capital and compliance burden, but we depend on providers' licences and cannot control settlement timing.

**TODO:** confirm the classification wording with a source (RBI Master Directions on Payment Aggregators, 2025) and note that production use would need legal review.

## 5. Competitive landscape

**TODO:** fill from public sources (websites, docs, pricing pages).

| Player | Type | What they do well | Gap this product targets |
|---|---|---|---|
| Juspay | Orchestration | _(fill)_ | _(fill)_ |
| Razorpay | PA + smart routing | _(fill)_ | _(fill)_ |
| Cashfree | PA | _(fill)_ | _(fill)_ |
| PayU | PA | _(fill)_ | _(fill)_ |

**Positioning hypothesis (edit to your view):** a lightweight, developer-first orchestration layer with first-class reconciliation for mid-size merchants.

## 6. User stories (MVP)

1. As a developer, I create a payment with one API call and an idempotency key, so retries never double-charge.
2. As a developer, I get a webhook when the payment succeeds or fails, so my order system stays in sync.
3. As a merchant, if my primary provider fails, the payment is retried on a backup automatically.
4. As finance, I see daily matched and unmatched settlements, so I only investigate exceptions.
5. As a merchant, I can issue full or partial refunds through the same API.
6. As a merchant, I can create a recurring mandate (UPI AutoPay / NACH) and see its status.

## 7. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | `POST /payment_intents` with required `Idempotency-Key` | Must |
| FR-2 | Payment state machine: CREATED, PENDING, SUCCESS, FAILED, REFUNDED | Must |
| FR-3 | Routing by method, amount and provider health, with circuit breaker | Must |
| FR-4 | Failover creates a new attempt on another provider | Must |
| FR-5 | Append-only event log and double-entry ledger | Must |
| FR-6 | Signed webhooks with exponential-backoff retries | Must |
| FR-7 | Reconciliation job against settlement CSVs | Must |
| FR-8 | Refund API (full and partial) | Should |
| FR-9 | Mandate creation and status (UPI AutoPay / NACH) | Should |
| FR-10 | Merchant dashboard | Could |

## 8. Success metrics

| Metric | Definition | Target (assumption) |
|---|---|---|
| Payment success rate | successful / attempted | **TODO** set baseline vs. failover result from simulation |
| Failover recovery rate | failed on primary, succeeded on backup / failed on primary | **TODO** |
| p95 API latency | gateway to response | **TODO** |
| Reconciliation match rate | matched / total settled | **TODO** |
| Time to add a new provider | engineering days | **TODO** |

State clearly that all results come from simulated providers.

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Duplicate charges on timeouts | Idempotency keys plus our own reference sent to providers |
| Provider status stuck in "pending" | Polling job plus webhook reconciliation |
| Regulatory misclassification | Keep funds out of scope; get legal review before production |
| Data localisation | Hosting and storage in India regions |

## 10. Roadmap

| Phase | Scope |
|---|---|
| MVP | Unified API, 3 mock connectors, routing and failover, ledger, reconciliation |
| v1 | Mandates, refunds, dashboard, more connectors |
| v2 | Cost-based routing, smart retries, analytics, multi-merchant onboarding |

## 11. Open questions

- **TODO:** which merchant segment first?
- **TODO:** pricing model (per-transaction fee vs. SaaS tier)?
- **TODO:** build vs. partner for UPI access?
