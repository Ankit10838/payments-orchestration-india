import hashlib
import json
import time
from datetime import datetime, timezone

from .connectors import RETRYABLE, ProviderResult
from .errors import (IdempotencyConflict, NotFound, RefundError, ValidationError)
from .ledger import Ledger
from .models import Attempt, Intent, Refund, Status
from .router import Router
from .state_machine import move

METHODS = {"upi", "card", "netbanking"}
MERCHANT_PAYABLE = "merchant_payable"


class PaymentEngine:
    def __init__(self, connectors, router=None, max_attempts=3, clock=time.time, on_event=None):
        self.connectors = {c.name: c for c in connectors}
        self.router = router or Router(connectors, clock=clock)
        self.max_attempts = max_attempts
        self.clock = clock
        self.on_event = on_event
        self.intents = {}
        self.refunds = {}
        self.events = []
        self.ledger = Ledger()
        self._idem = {}
        self._refund_idem = {}
        self._seq = 0

    # ---- helpers -------------------------------------------------------
    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}_{self._seq:06d}"

    def _now(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat()

    @staticmethod
    def _hash(body):
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _emit(self, event_type, obj):
        event = {"id": self._id("evt"), "type": event_type, "created": self._now(),
                 "data": {"object": obj}}
        self.events.append(event)
        if self.on_event:
            self.on_event(event)

    def get(self, intent_id):
        if intent_id not in self.intents:
            raise NotFound(f"Payment intent {intent_id} not found")
        return self.intents[intent_id]

    # ---- create --------------------------------------------------------
    def create_payment_intent(self, idempotency_key, body):
        """Returns (intent, replayed). Same key + same body = same intent, no new charge."""
        if not idempotency_key:
            raise ValidationError("Idempotency-Key header is required",
                                  code="idempotency_key_required", param="Idempotency-Key")
        body_hash = self._hash(body)
        if idempotency_key in self._idem:
            stored_hash, intent_id = self._idem[idempotency_key]
            if stored_hash != body_hash:
                raise IdempotencyConflict("Idempotency-Key was already used with a different request body")
            return self.intents[intent_id], True

        intent = self._validate(idempotency_key, body)
        self._idem[idempotency_key] = (body_hash, intent.id)
        self.intents[intent.id] = intent
        self._process(intent)
        return intent, False

    def _validate(self, key, body):
        if not isinstance(body, dict):
            raise ValidationError("Request body must be a JSON object")
        amount = body.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 100:
            raise ValidationError("amount must be an integer in paise, minimum 100",
                                  code="amount_too_small", param="amount")
        if body.get("currency") != "INR":
            raise ValidationError("currency must be INR", code="unsupported_currency", param="currency")
        method = body.get("method")
        if method not in METHODS:
            raise ValidationError(f"method must be one of {sorted(METHODS)}", param="method")
        if not any(method in c.methods for c in self.connectors.values()):
            raise ValidationError(f"No provider supports {method}", code="method_unsupported", param="method")
        if method == "card":
            card = body.get("card") or {}
            if "number" in card or "cvv" in card:
                raise ValidationError("Raw card data is not accepted; send a card token",
                                      code="raw_card_data_rejected", param="card")
            if not card.get("token"):
                raise ValidationError("card.token is required for card payments", param="card.token")
        hint = (body.get("routing_hint") or {}).get("preferred_provider")
        return Intent(id=self._id("pi"), amount=amount, currency="INR", method=method,
                      idempotency_key=key, metadata=body.get("metadata") or {},
                      routing_hint=hint, created=self._now())

    # ---- processing with failover -------------------------------------
    def _process(self, intent):
        move(intent, Status.PENDING)
        candidates = self.router.rank(intent.method, preferred=intent.routing_hint)
        last = ProviderResult("failed", "no_provider_available")
        for connector in candidates[: self.max_attempts]:
            attempt = Attempt(id=f"{intent.id}_a{len(intent.attempts) + 1}",
                              provider=connector.name, created=self._now())
            intent.attempts.append(attempt)
            # attempt.id doubles as the provider-side reference, so provider retries stay idempotent
            result = connector.create_payment(attempt.id, intent.amount, intent.method)
            attempt.status = result.status
            attempt.error_code = result.error_code
            attempt.latency_ms = result.latency_ms
            attempt.provider_ref = result.provider_ref
            self.router.record(connector.name, result)
            if result.status == "succeeded":
                self._succeed(intent, connector.name, result.provider_ref)
                return
            if result.status == "pending":
                self._emit("payment_intent.pending", intent.to_dict())
                return
            last = result
            if result.error_code not in RETRYABLE:
                break  # customer-side decline: do not shop the payment around
        self._fail(intent, last.error_code)

    def _succeed(self, intent, provider, provider_ref):
        move(intent, Status.SUCCEEDED)
        intent.provider, intent.provider_ref = provider, provider_ref
        self.ledger.post(intent.id, [(f"provider_receivable:{provider}", intent.amount, 0),
                                     (MERCHANT_PAYABLE, 0, intent.amount)])
        self._emit("payment_intent.succeeded", intent.to_dict())

    def _fail(self, intent, code):
        move(intent, Status.FAILED)
        intent.failure_code = code
        self._emit("payment_intent.failed", intent.to_dict())

    def handle_provider_callback(self, intent_id, attempt_id, status, error_code=None):
        """Async result for a pending attempt (e.g. UPI collect). Ignored if already resolved.
        MVP: a failed callback fails the intent; it does not start a new attempt."""
        intent = self.get(intent_id)
        if intent.status != Status.PENDING:
            return intent
        attempt = next((a for a in intent.attempts if a.id == attempt_id), None)
        if attempt is None:
            raise NotFound(f"Attempt {attempt_id} not found")
        attempt.status, attempt.error_code = status, error_code
        if status == "succeeded":
            self._succeed(intent, attempt.provider, attempt.provider_ref or attempt.id)
        else:
            self._fail(intent, error_code)
        return intent

    # ---- cancel / refund ----------------------------------------------
    def cancel(self, intent_id):
        intent = self.get(intent_id)
        move(intent, Status.CANCELED)
        self._emit("payment_intent.canceled", intent.to_dict())
        return intent

    def refund(self, intent_id, amount, idempotency_key, reason="other"):
        if not idempotency_key:
            raise ValidationError("Idempotency-Key header is required",
                                  code="idempotency_key_required", param="Idempotency-Key")
        body_hash = self._hash({"intent": intent_id, "amount": amount, "reason": reason})
        if idempotency_key in self._refund_idem:
            stored_hash, refund_id = self._refund_idem[idempotency_key]
            if stored_hash != body_hash:
                raise IdempotencyConflict("Idempotency-Key was already used with a different request body")
            return self.refunds[refund_id], True

        intent = self.get(intent_id)
        if intent.status not in (Status.SUCCEEDED, Status.PARTIALLY_REFUNDED):
            raise RefundError("Only successful payments can be refunded")
        remaining = intent.amount - intent.amount_refunded
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise ValidationError("amount must be a positive integer in paise", param="amount")
        if amount > remaining:
            raise RefundError(f"Refund exceeds refundable balance ({remaining} paise left)",
                              code="amount_exceeds_balance", param="amount")

        result = self.connectors[intent.provider].refund(intent.provider_ref, amount)
        refund = Refund(id=self._id("rf"), payment_intent_id=intent.id, amount=amount,
                        status="succeeded" if result.status == "succeeded" else "failed",
                        created=self._now())
        self.refunds[refund.id] = refund
        self._refund_idem[idempotency_key] = (body_hash, refund.id)
        if refund.status == "succeeded":
            intent.amount_refunded += amount
            move(intent, Status.REFUNDED if intent.amount_refunded == intent.amount
                 else Status.PARTIALLY_REFUNDED)
            self.ledger.post(refund.id, [(MERCHANT_PAYABLE, amount, 0),
                                         (f"provider_receivable:{intent.provider}", 0, amount)])
            self._emit("refund.succeeded", refund.to_dict())
        else:
            self._emit("refund.failed", refund.to_dict())
        return refund, False
