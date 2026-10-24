"""FastAPI layer. Thin on purpose: all logic lives in PaymentEngine.

Run:  PYTHONPATH=src uvicorn payments.api:app --reload
Docs: http://localhost:8000/docs
"""
import os

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .connectors import MockConnector
from .engine import PaymentEngine
from .errors import AuthenticationError, BadRequest, PaymentError
from .router import Router

API_KEY = os.getenv("SANDBOX_API_KEY", "sk_test_sandbox")


def build_engine():
    connectors = [
        MockConnector("mock_provider_a", reliability=0.92, priority=1, cost_bps=120, seed=1),
        MockConnector("mock_provider_b", reliability=0.95, priority=2, cost_bps=150, seed=2),
    ]
    return PaymentEngine(connectors, router=Router(connectors))


engine = build_engine()
app = FastAPI(title="Payments Orchestration API (India) - Sandbox", version="0.1.0")


@app.exception_handler(PaymentError)
async def payment_error_handler(request: Request, exc: PaymentError):
    return JSONResponse(exc.to_dict(), status_code=exc.status)


def _auth(request: Request):
    if request.headers.get("authorization", "") != f"Bearer {API_KEY}":
        raise AuthenticationError("Missing or invalid API key")


async def _json(request: Request):
    try:
        return await request.json()
    except Exception:
        raise BadRequest("Body must be valid JSON", code="invalid_json")


@app.post("/v1/payment_intents")
async def create_payment_intent(request: Request,
                                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _auth(request)
    intent, replayed = engine.create_payment_intent(idempotency_key, await _json(request))
    return JSONResponse(intent.to_dict(), status_code=200 if replayed else 201)


@app.get("/v1/payment_intents/{intent_id}")
async def get_payment_intent(intent_id: str, request: Request):
    _auth(request)
    return engine.get(intent_id).to_dict()


@app.post("/v1/payment_intents/{intent_id}/cancel")
async def cancel_payment_intent(intent_id: str, request: Request):
    _auth(request)
    return engine.cancel(intent_id).to_dict()


@app.post("/v1/payment_intents/{intent_id}/refunds")
async def create_refund(intent_id: str, request: Request,
                        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _auth(request)
    body = await _json(request)
    refund, replayed = engine.refund(intent_id, body.get("amount"), idempotency_key,
                                     body.get("reason", "other"))
    return JSONResponse(refund.to_dict(), status_code=200 if replayed else 201)


# ---- sandbox-only controls for demos (not part of the public API spec) ----
@app.post("/v1/_sandbox/providers/{name}")
async def sandbox_set_provider(name: str, request: Request):
    """Body: {"down": true} or {"reliability": 0.5}. Lets you trigger failover on demand."""
    _auth(request)
    body = await _json(request)
    connector = engine.connectors.get(name)
    if connector is None:
        raise BadRequest(f"Unknown provider {name}", code="unknown_provider")
    if "down" in body:
        connector.down = bool(body["down"])
    if "reliability" in body:
        connector.reliability = float(body["reliability"])
    return {"name": name, "down": connector.down, "reliability": connector.reliability}


@app.get("/v1/_sandbox/events")
async def sandbox_events(request: Request):
    _auth(request)
    return {"data": engine.events[-50:]}


@app.get("/v1/_sandbox/ledger")
async def sandbox_ledger(request: Request):
    _auth(request)
    debit, credit = engine.ledger.trial_balance()
    return {"total_debit": debit, "total_credit": credit, "balanced": debit == credit,
            "entries": engine.ledger.entries[-50:]}
