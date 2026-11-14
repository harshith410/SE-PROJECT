"""Registration, login and the token_required decorator (JWT, HS256)."""
import re
from datetime import datetime, timedelta, timezone
from functools import wraps
import sqlite3

import jwt
from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .utils import ApiError, json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = generate_password_hash("not-a-real-password")   # equalises login timing


def make_token(user_id):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now,
               "exp": now + timedelta(hours=current_app.config["TOKEN_HOURS"])}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise ApiError(401, "Missing or invalid Authorization header")
        try:
            data = jwt.decode(header[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
            user_id = int(data["sub"])
        except jwt.ExpiredSignatureError:
            raise ApiError(401, "Token has expired, please log in again")
        except (jwt.InvalidTokenError, KeyError, ValueError):
            raise ApiError(401, "Invalid token")
        user = get_db().execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            raise ApiError(401, "Account no longer exists")
        g.user_id = user_id
        return view(*args, **kwargs)
    return wrapper


def public_user(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "currency": row["currency"]}


@bp.post("/register")
def register():
    data = json_body()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    if not 1 <= len(name) <= 60:
        raise ApiError(400, "name is required (max 60 characters)")
    if not EMAIL_RE.match(email) or len(email) > 120:
        raise ApiError(400, "a valid email is required")
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ApiError(400, "password must be 8 to 128 characters")
   db = get_db()
    try:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
            (name, email, generate_password_hash(password)),
        )
        db.commit()
    except Exception:
        raise ApiError(409, "An account with this email already exists")
    cur.execute("SELECT * FROM users WHERE id = %s", (cur.lastrowid,))
    row = cur.fetchone()
    return jsonify(user=public_user(row), token=make_token(row["id"])), 201
    password = data.get("password", "")
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    stored = row["password_hash"] if row else _DUMMY_HASH
    ok = isinstance(password, str) and check_password_hash(stored, password)
    if not row or not ok:
        raise ApiError(401, "Invalid email or password")
    return jsonify(user=public_user(row), token=make_token(row["id"]))


@bp.get("/me")
@token_required
def me():
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return jsonify(user=public_user(row))
