import hashlib
import hmac

# Seconds to wait before retry 1, 2, 3... then move to a dead-letter queue.
RETRY_DELAYS = [60, 300, 1800, 7200, 43200]


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(secret: str, body: bytes, signature: str) -> bool:
    return hmac.compare_digest(sign(secret, body), signature)


def next_delay(failed_attempts: int):
    """Delay before the next delivery try, or None when retries are exhausted."""
    return RETRY_DELAYS[failed_attempts] if failed_attempts < len(RETRY_DELAYS) else None
