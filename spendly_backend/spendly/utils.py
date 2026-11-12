"""Shared constants, validation helpers and the ApiError exception."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

from flask import request

CATEGORIES = ["Food", "Transport", "Rent", "Shopping", "Bills",
              "Health", "Entertainment", "Education", "Other"]
CURRENCIES = ["\u20b9", "$", "\u20ac", "\u00a3"]          # rupee, dollar, euro, pound
TYPES = ("income", "expense")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_CENTS = 100_000_000 * 100                              # 100 million


class ApiError(Exception):
    """Raised anywhere in a request; converted to a JSON error response."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return data


def valid_month(value):
    if not isinstance(value, str) or not MONTH_RE.match(value):
        raise ApiError(400, "month must be in YYYY-MM format")
    return value


def valid_date(value):
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ApiError(400, "date must be in YYYY-MM-DD format")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, "date is not a real calendar date")
    return value


def to_cents(value, allow_zero=False):
    """Convert a user amount to integer cents (money is never stored as float)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ApiError(400, "amount must be a number")
    try:
        d = Decimal(str(value).strip())
    except InvalidOperation:
        raise ApiError(400, "amount must be a number")
    if not d.is_finite():
        raise ApiError(400, "amount must be a number")
    if d * 100 > MAX_CENTS:
        raise ApiError(400, "amount is too large")
    cents = int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if cents < 0 or (cents == 0 and not allow_zero):
        raise ApiError(400, "amount must be greater than 0")
    return cents


def from_cents(cents):
    return round(cents / 100, 2)


def month_range(month):
    """ISO date strings sort correctly, so a simple BETWEEN works and uses the index."""
    return f"{month}-01", f"{month}-31"
