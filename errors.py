import uuid


class PaymentError(Exception):
    """Base error. Maps 1:1 to the Error schema in api/openapi.yaml."""

    status = 400
    type = "invalid_request"
    code = "invalid_request"

    def __init__(self, message, code=None, param=None):
        super().__init__(message)
        self.message = message
        self.param = param
        if code:
            self.code = code

    def to_dict(self):
        return {
            "error": {
                "type": self.type,
                "code": self.code,
                "message": self.message,
                "param": self.param,
                "request_id": "req_" + uuid.uuid4().hex[:12],
            }
        }


class BadRequest(PaymentError):
    status = 400


class AuthenticationError(PaymentError):
    status = 401
    type = "authentication_error"
    code = "invalid_api_key"


class NotFound(PaymentError):
    status = 404
    code = "not_found"


class IdempotencyConflict(PaymentError):
    status = 409
    type = "idempotency_error"
    code = "idempotency_key_reused"


class InvalidTransition(PaymentError):
    status = 409
    code = "invalid_state"


class ValidationError(PaymentError):
    status = 422
    code = "validation_error"


class RefundError(PaymentError):
    status = 422
    code = "refund_not_allowed"
