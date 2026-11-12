"""CRUD, search/filter and CSV export for transactions."""
import csv
import io

from flask import Blueprint, Response, g, jsonify, request

from .auth import token_required
from .db import get_db
from .utils import (ApiError, CATEGORIES, TYPES, from_cents, json_body, month_range,
                    to_cents, valid_date, valid_month)

bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


def serialize(row):
    return {"id": row["id"], "type": row["type"], "amount": from_cents(row["amount_cents"]),
            "category": row["category"], "date": row["date"], "note": row["note"]}


def validate(data):
    if data.get("type") not in TYPES:
        raise ApiError(400, "type must be 'income' or 'expense'")
    if data.get("category") not in CATEGORIES:
        raise ApiError(400, "category must be one of: " + ", ".join(CATEGORIES))
    note = data.get("note") or ""
    if not isinstance(note, str) or len(note.strip()) > 80:
        raise ApiError(400, "note must be text of at most 80 characters")
    return {"type": data["type"], "amount_cents": to_cents(data.get("amount")),
            "category": data["category"], "date": valid_date(data.get("date")),
            "note": note.strip()}


def build_query(select):
    """Shared filter logic for the list and export endpoints (always scoped to the user)."""
    sql = f"{select} FROM transactions WHERE user_id = ?"
    params = [g.user_id]
    month = request.args.get("month")
    if month:
        lo, hi = month_range(valid_month(month))
        sql += " AND date BETWEEN ? AND ?"
        params += [lo, hi]
    category = request.args.get("category")
    if category:
        if category not in CATEGORIES:
            raise ApiError(400, "unknown category")
        sql += " AND category = ?"
        params.append(category)
    ttype = request.args.get("type")
    if ttype:
        if ttype not in TYPES:
            raise ApiError(400, "type must be 'income' or 'expense'")
        sql += " AND type = ?"
        params.append(ttype)
    q = request.args.get("q", "").strip()
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND note LIKE ? ESCAPE '\\'"
        params.append(f"%{escaped}%")
    return sql + " ORDER BY date DESC, id DESC", params


@bp.get("")
@token_required
def list_transactions():
    try:
        limit = min(int(request.args.get("limit", 500)), 1000)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ApiError(400, "limit and offset must be integers")
    sql, params = build_query("SELECT *")
    rows = get_db().execute(sql + " LIMIT ? OFFSET ?", params + [max(limit, 1), offset]).fetchall()
    return jsonify(transactions=[serialize(r) for r in rows], count=len(rows))


@bp.post("")
@token_required
def create_transaction():
    t = validate(json_body())
    db = get_db()
    cur = db.execute(
        "INSERT INTO transactions (user_id, type, amount_cents, category, date, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (g.user_id, t["type"], t["amount_cents"], t["category"], t["date"], t["note"]))
    db.commit()
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(transaction=serialize(row)), 201


def own_transaction(tx_id):
    row = get_db().execute("SELECT * FROM transactions WHERE id = ? AND user_id = ?",
                           (tx_id, g.user_id)).fetchone()
    if row is None:                       # same answer for "missing" and "someone else's"
        raise ApiError(404, "Transaction not found")
    return row


@bp.get("/<int:tx_id>")
@token_required
def get_transaction(tx_id):
    return jsonify(transaction=serialize(own_transaction(tx_id)))


@bp.put("/<int:tx_id>")
@token_required
def update_transaction(tx_id):
    own_transaction(tx_id)
    t = validate(json_body())
    db = get_db()
    db.execute("UPDATE transactions SET type=?, amount_cents=?, category=?, date=?, note=? "
               "WHERE id=? AND user_id=?",
               (t["type"], t["amount_cents"], t["category"], t["date"], t["note"], tx_id, g.user_id))
    db.commit()
    return jsonify(transaction=serialize(own_transaction(tx_id)))


@bp.delete("/<int:tx_id>")
@token_required
def delete_transaction(tx_id):
    own_transaction(tx_id)
    db = get_db()
    db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, g.user_id))
    db.commit()
    return "", 204


def safe_cell(value):
    """Stop spreadsheet formula injection when the CSV is opened in Excel or Sheets."""
    s = str(value)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@bp.get("/export")
@token_required
def export_csv():
    sql, params = build_query("SELECT *")
    rows = get_db().execute(sql, params).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "type", "category", "amount", "note"])
    for r in rows:
        writer.writerow([r["date"], r["type"], r["category"],
                         f"{from_cents(r['amount_cents']):.2f}", safe_cell(r["note"])])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="spendly-transactions.csv"'})
