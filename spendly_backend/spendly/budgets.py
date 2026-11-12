"""Monthly budgets, user settings (currency), categories and the monthly summary."""
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify

from .auth import token_required
from .db import get_db
from .utils import (ApiError, CATEGORIES, CURRENCIES, from_cents, json_body, month_range,
                    to_cents, valid_month)
from flask import request

bp = Blueprint("budgets", __name__, url_prefix="/api")


def budget_cents(db, month):
    row = db.execute("SELECT amount_cents FROM budgets WHERE user_id = ? AND month = ?",
                     (g.user_id, month)).fetchone()
    return row["amount_cents"] if row else 0


@bp.get("/categories")
def categories():
    return jsonify(categories=CATEGORIES, currencies=CURRENCIES)


@bp.get("/budgets/<month>")
@token_required
def get_budget(month):
    valid_month(month)
    return jsonify(month=month, amount=from_cents(budget_cents(get_db(), month)))


@bp.put("/budgets/<month>")
@token_required
def set_budget(month):
    valid_month(month)
    cents = to_cents(json_body().get("amount"), allow_zero=True)
    db = get_db()
    if cents == 0:                                   # 0 clears the budget (same as the web app)
        db.execute("DELETE FROM budgets WHERE user_id = ? AND month = ?", (g.user_id, month))
    else:
        db.execute("INSERT INTO budgets (user_id, month, amount_cents) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id, month) DO UPDATE SET amount_cents = excluded.amount_cents",
                   (g.user_id, month, cents))
    db.commit()
    return jsonify(month=month, amount=from_cents(cents))


@bp.get("/settings")
@token_required
def get_settings():
    row = get_db().execute("SELECT currency FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return jsonify(currency=row["currency"])


@bp.put("/settings")
@token_required
def set_settings():
    currency = json_body().get("currency")
    if currency not in CURRENCIES:
        raise ApiError(400, "currency must be one of: " + " ".join(CURRENCIES))
    db = get_db()
    db.execute("UPDATE users SET currency = ? WHERE id = ?", (currency, g.user_id))
    db.commit()
    return jsonify(currency=currency)


@bp.get("/summary")
@token_required
def summary():
    month = request.args.get("month") or datetime.now(timezone.utc).strftime("%Y-%m")
    valid_month(month)
    lo, hi = month_range(month)
    db = get_db()
    totals = {"income": 0, "expense": 0}
    for r in db.execute("SELECT type, SUM(amount_cents) AS s FROM transactions "
                        "WHERE user_id = ? AND date BETWEEN ? AND ? GROUP BY type",
                        (g.user_id, lo, hi)):
        totals[r["type"]] = r["s"]
    by_cat = [{"category": r["category"], "total": from_cents(r["s"])} for r in db.execute(
        "SELECT category, SUM(amount_cents) AS s FROM transactions "
        "WHERE user_id = ? AND type = 'expense' AND date BETWEEN ? AND ? "
        "GROUP BY category ORDER BY s DESC", (g.user_id, lo, hi))]
    budget = budget_cents(db, month)
    spent = totals["expense"]
    if not budget:
        status, pct = "no_budget", None
    else:
        pct = round(spent / budget * 100, 1)
        status = "over_budget" if spent > budget else "close_to_limit" if pct >= 80 else "on_track"
    return jsonify(month=month, income=from_cents(totals["income"]), spent=from_cents(spent),
                   balance=from_cents(totals["income"] - spent), budget=from_cents(budget),
                   budget_used_percent=pct, budget_status=status,
                   over_by=from_cents(spent - budget) if budget and spent > budget else 0,
                   by_category=by_cat)
