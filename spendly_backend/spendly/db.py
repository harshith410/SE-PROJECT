"""PostgreSQL connection handling and schema."""
import os
import psycopg2
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    currency      TEXT NOT NULL DEFAULT '\u20b9',
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         TEXT NOT NULL CHECK (type IN ('income','expense')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    category     TEXT NOT NULL,
    date         TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, date);

CREATE TABLE IF NOT EXISTS budgets (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month        TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    PRIMARY KEY (user_id, month)
);
"""

def get_db():
    if "db" not in g:
        # Construct connection string from individual variables
        host = os.environ.get("POSTGRES_HOST")
        database = os.environ.get("POSTGRES_DATABASE")
        user = os.environ.get("POSTGRES_USER")
        password = os.environ.get("POSTGRES_PASSWORD")
        port = os.environ.get("POSTGRES_PORT", "5432")
        
        conn_str = f"host={host} dbname={database} user={user} password={password} port={port}"
        g.db = psycopg2.connect(conn_str)
        g.db.autocommit = True
    return g.db

def init_db():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(SCHEMA)
    db.commit()
    cursor.close()

def init_app(app):
    app.teardown_appcontext(close_db)
