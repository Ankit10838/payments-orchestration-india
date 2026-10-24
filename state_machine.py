from .errors import InvalidTransition
from .models import Status

TRANSITIONS = {
    Status.CREATED: {Status.PENDING, Status.CANCELED, Status.FAILED},
    Status.PENDING: {Status.SUCCEEDED, Status.FAILED, Status.CANCELED},
    Status.SUCCEEDED: {Status.PARTIALLY_REFUNDED, Status.REFUNDED},
    Status.PARTIALLY_REFUNDED: {Status.PARTIALLY_REFUNDED, Status.REFUNDED},
    Status.FAILED: set(),
    Status.CANCELED: set(),
    Status.REFUNDED: set(),
}


def move(intent, new_status):
    """Apply a transition or raise. Every status change goes through here."""
    if new_status not in TRANSITIONS[intent.status]:
        raise InvalidTransition(
            f"Cannot move payment from {intent.status.value} to {new_status.value}"
        )
    intent.status = new_status
