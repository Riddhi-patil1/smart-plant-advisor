"""API errors and small input-validation helpers."""
import math


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message, fields=None, status=None, code=None):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code

    def to_dict(self):
        body = {"code": self.code, "message": self.message}
        if self.fields:
            body["fields"] = self.fields
        return {"error": body}


class ValidationError(ApiError):
    status = 422
    code = "validation_error"

    def __init__(self, message="Validation failed.", fields=None):
        super().__init__(message, fields)


class NotFoundError(ApiError):
    status = 404
    code = "not_found"


class ConflictError(ApiError):
    status = 409
    code = "conflict"


_MISSING = object()


def to_number(value):
    """Return a finite float for int/float/numeric-string input, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def read_number(data, key, errors, label, lo=None, hi=None, default=_MISSING):
    """Read a bounded number from ``data``; record a field error on failure."""
    if key not in data or data[key] is None or data[key] == "":
        if default is _MISSING:
            errors[key] = f"{label} is required."
            return None
        return default
    number = to_number(data[key])
    if number is None:
        errors[key] = f"{label} must be a number."
        return None
    if lo is not None and number < lo:
        errors[key] = f"{label} must be at least {lo:g}."
        return None
    if hi is not None and number > hi:
        errors[key] = f"{label} must be at most {hi:g}."
        return None
    return number


def read_text(data, key, errors, label, max_len, required=False, default=""):
    value = data.get(key)
    if value is None:
        value = default
    if not isinstance(value, str):
        errors[key] = f"{label} must be text."
        return None
    value = value.strip()
    if required and not value:
        errors[key] = f"{label} is required."
        return None
    if len(value) > max_len:
        errors[key] = f"{label} must be {max_len} characters or fewer."
        return None
    return value
