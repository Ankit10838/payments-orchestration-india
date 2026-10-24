import unittest

from payments import webhooks
from payments.connectors import MockConnector
from payments.engine import PaymentEngine
from payments.errors import (IdempotencyConflict, InvalidTransition, RefundError, ValidationError)
from payments.models import Intent, Status
from payments.router import Router
from payments.state_machine import move

BODY = {"amount": 49900, "currency": "INR", "method": "upi"}


def good(name, priority=1):
    return MockConnector(name, reliability=1.0, customer_decline_rate=0.0, priority=priority, seed=1)


def broken(name, priority=1):
    return MockConnector(name, reliability=0.0, customer_decline_rate=0.0, priority=priority, seed=1)


def declining(name, priority=1):
    return MockConnector(name, reliability=1.0, customer_decline_rate=1.0, priority=priority, seed=1)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class EngineTests(unittest.TestCase):
    def test_success_posts_balanced_ledger(self):
        a = good("a")
        e = PaymentEngine([a])
        intent, replayed = e.create_payment_intent("k1", BODY)
        self.assertEqual(intent.status, Status.SUCCEEDED)
        self.assertFalse(replayed)
        debit, credit = e.ledger.trial_balance()
        self.assertEqual((debit, credit), (49900, 49900))
        self.assertEqual(e.ledger.balance("merchant_payable"), -49900)

    def test_idempotent_replay_does_not_charge_twice(self):
        a = good("a")
        e = PaymentEngine([a])
        first, _ = e.create_payment_intent("k1", BODY)
        second, replayed = e.create_payment_intent("k1", BODY)
        self.assertTrue(replayed)
        self.assertEqual(first.id, second.id)
        self.assertEqual(a.calls, 1)
        self.assertEqual(len(e.ledger.entries), 2)

    def test_same_key_different_body_conflicts(self):
        e = PaymentEngine([good("a")])
        e.create_payment_intent("k1", BODY)
        with self.assertRaises(IdempotencyConflict):
            e.create_payment_intent("k1", {**BODY, "amount": 100})

    def test_failover_on_provider_error(self):
        a, b = broken("a", 1), good("b", 2)
        e = PaymentEngine([a, b])
        intent, _ = e.create_payment_intent("k1", BODY)
        self.assertEqual(intent.status, Status.SUCCEEDED)
        self.assertEqual(intent.provider, "b")
        self.assertEqual([x.provider for x in intent.attempts], ["a", "b"])
        self.assertIn(intent.attempts[0].error_code, {"timeout", "issuer_unavailable"})

    def test_no_failover_on_customer_decline(self):
        a, b = declining("a", 1), good("b", 2)
        e = PaymentEngine([a, b])
        intent, _ = e.create_payment_intent("k1", BODY)
        self.assertEqual(intent.status, Status.FAILED)
        self.assertEqual(intent.failure_code, "insufficient_funds")
        self.assertEqual(len(intent.attempts), 1)
        self.assertEqual(b.calls, 0)

    def test_all_providers_fail(self):
        e = PaymentEngine([broken("a", 1), broken("b", 2)])
        intent, _ = e.create_payment_intent("k1", BODY)
        self.assertEqual(intent.status, Status.FAILED)
        self.assertEqual(len(intent.attempts), 2)
        self.assertEqual(e.ledger.entries, [])

    def test_partial_then_full_refund(self):
        e = PaymentEngine([good("a")])
        intent, _ = e.create_payment_intent("k1", BODY)
        r1, _ = e.refund(intent.id, 10000, "r1")
        self.assertEqual(r1.status, "succeeded")
        self.assertEqual(intent.status, Status.PARTIALLY_REFUNDED)
        e.refund(intent.id, 39900, "r2")
        self.assertEqual(intent.status, Status.REFUNDED)
        self.assertEqual(e.ledger.balance("merchant_payable"), 0)
        debit, credit = e.ledger.trial_balance()
        self.assertEqual(debit, credit)

    def test_refund_over_balance_and_replay(self):
        e = PaymentEngine([good("a")])
        intent, _ = e.create_payment_intent("k1", BODY)
        with self.assertRaises(RefundError):
            e.refund(intent.id, 50000, "r1")
        r, _ = e.refund(intent.id, 1000, "r2")
        again, replayed = e.refund(intent.id, 1000, "r2")
        self.assertTrue(replayed)
        self.assertEqual(r.id, again.id)
        self.assertEqual(intent.amount_refunded, 1000)

    def test_cannot_cancel_succeeded_payment(self):
        e = PaymentEngine([good("a")])
        intent, _ = e.create_payment_intent("k1", BODY)
        with self.assertRaises(InvalidTransition):
            e.cancel(intent.id)

    def test_invalid_transition_rejected(self):
        intent = Intent(id="pi_x", amount=100, currency="INR", method="upi", idempotency_key="k",
                        status=Status.FAILED)
        with self.assertRaises(InvalidTransition):
            move(intent, Status.SUCCEEDED)

    def test_validation(self):
        e = PaymentEngine([good("a")])
        with self.assertRaises(ValidationError):
            e.create_payment_intent("k1", {**BODY, "amount": 50})
        with self.assertRaises(ValidationError):
            e.create_payment_intent("k2", {**BODY, "currency": "USD"})
        with self.assertRaises(ValidationError):
            e.create_payment_intent("", BODY)
        with self.assertRaises(ValidationError) as ctx:
            e.create_payment_intent("k3", {"amount": 500, "currency": "INR", "method": "card",
                                           "card": {"number": "4111111111111111"}})
        self.assertEqual(ctx.exception.code, "raw_card_data_rejected")

    def test_pending_then_callback_succeeds(self):
        class PendingConnector(MockConnector):
            def create_payment(self, reference, amount, method):
                from payments.connectors import ProviderResult
                return ProviderResult("pending", None, f"{self.name}_p1", 50)

        e = PaymentEngine([PendingConnector("a")])
        intent, _ = e.create_payment_intent("k1", BODY)
        self.assertEqual(intent.status, Status.PENDING)
        e.handle_provider_callback(intent.id, intent.attempts[0].id, "succeeded")
        self.assertEqual(intent.status, Status.SUCCEEDED)
        e.handle_provider_callback(intent.id, intent.attempts[0].id, "failed", "timeout")
        self.assertEqual(intent.status, Status.SUCCEEDED)  # late duplicate callback is ignored


class RouterTests(unittest.TestCase):
    def test_circuit_opens_then_recovers(self):
        clock = FakeClock()
        a, b = broken("a", 1), good("b", 2)
        router = Router([a, b], clock=clock, min_samples=20, threshold=0.5, cooldown_s=30)
        e = PaymentEngine([a, b], router=router, clock=clock)
        for i in range(25):
            e.create_payment_intent(f"k{i}", BODY)
        self.assertEqual(a.calls, 20)  # circuit opened after 20 failures; later payments skip a
        a.reliability = 1.0
        clock.t += 31  # cooldown elapsed -> half-open probe
        intent, _ = e.create_payment_intent("probe", BODY)
        self.assertEqual(intent.provider, "a")
        self.assertEqual(router.breakers["a"].state, "closed")

    def test_customer_declines_do_not_trip_breaker(self):
        a = declining("a")
        router = Router([a], min_samples=20)
        e = PaymentEngine([a], router=router)
        for i in range(30):
            e.create_payment_intent(f"k{i}", BODY)
        self.assertEqual(router.breakers["a"].state, "closed")


class WebhookTests(unittest.TestCase):
    def test_signature_roundtrip(self):
        body = b'{"id":"evt_1"}'
        sig = webhooks.sign("whsec_test", body)
        self.assertTrue(webhooks.verify("whsec_test", body, sig))
        self.assertFalse(webhooks.verify("whsec_test", b'{"id":"evt_2"}', sig))
        self.assertFalse(webhooks.verify("other", body, sig))

    def test_retry_schedule_ends(self):
        self.assertEqual(webhooks.next_delay(0), 60)
        self.assertIsNone(webhooks.next_delay(5))


if __name__ == "__main__":
    unittest.main()
