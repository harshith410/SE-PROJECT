# Spendly Backend (Python / Flask)

REST API for the Spendly personal expense tracker. It adds what the browser-only version lacks:
**user accounts (JWT login), a real database (SQLite) and data that follows the user across devices.**

## What you get
A complete full-stack project: a Flask REST API, an SQLite database and a responsive web app with login.

## Tech
Flask 3, SQLite (built into Python), PyJWT, Werkzeug password hashing. Only two pip packages are needed.

## Setup
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
export SECRET_KEY="change-this-to-a-long-random-string"     # Windows: set SECRET_KEY=...
python run.py
```
Then open **http://127.0.0.1:5000/** in your browser. The backend serves the web app (`web/index.html`), so
the page and the API share one address. Create an account on the login screen and start tracking.
Run the tests: `python -m unittest discover -s tests -v`

## Configuration (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| SECRET_KEY | dev-only-change-me | Signs login tokens. **Always set your own.** |
| DATABASE | instance/spendly.db | SQLite file path |
| CORS_ORIGINS | * | Allowed website origins, comma separated (use your real site in production) |
| TOKEN_HOURS | 24 | Login token lifetime |
| PORT / FLASK_DEBUG | 5000 / off | Dev server options |

## Endpoints
All endpoints except `/api/health`, `/api/categories`, register and login need the header
`Authorization: Bearer <token>`. Amounts are numbers (stored internally as integer cents). Dates are `YYYY-MM-DD`, months `YYYY-MM`.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /api/auth/register | `{name, email, password}` creates an account, returns token |
| POST | /api/auth/login | `{email, password}` returns token |
| GET | /api/auth/me | Current user |
| GET | /api/transactions | List. Filters: `month`, `category`, `type`, `q` (note search), `limit`, `offset` |
| POST | /api/transactions | `{type, amount, category, date, note?}` |
| GET / PUT / DELETE | /api/transactions/{id} | Read, replace, delete one transaction |
| GET | /api/transactions/export | Same filters, downloads CSV |
| GET / PUT | /api/budgets/{month} | `{amount}`; amount 0 clears the budget |
| GET / PUT | /api/settings | `{currency}` one of the four symbols |
| GET | /api/summary?month= | Income, spent, balance, budget status, spending by category |
| GET | /api/categories | Categories and currencies |
| GET | /api/health | Health check |

Budget status values: `no_budget`, `on_track` (below 80%), `close_to_limit` (80 to 100%), `over_budget` (above 100%, `over_by` gives the excess).

### Quick test with curl
```bash
curl -X POST localhost:5000/api/auth/register -H "Content-Type: application/json" \
  -d '{"name":"Asha","email":"asha@example.com","password":"password123"}'
TOKEN=<paste token here>
curl -X POST localhost:5000/api/transactions -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"type":"expense","amount":450,"category":"Food","date":"2026-11-12","note":"Lunch"}'
curl "localhost:5000/api/summary?month=2026-11" -H "Authorization: Bearer $TOKEN"
```

### Calling it from the web app (JavaScript)
```js
const API = "http://127.0.0.1:5000/api";
const login = await fetch(API + "/auth/login", {method: "POST",
  headers: {"Content-Type": "application/json"}, body: JSON.stringify({email, password})}).then(r => r.json());
const list = await fetch(API + "/transactions?month=2026-11",
  {headers: {Authorization: "Bearer " + login.token}}).then(r => r.json());
```

## Project structure
```
spendly_backend/
  run.py                 starts the server
  requirements.txt
  spendly/
    __init__.py          app factory, CORS, error handlers
    db.py                SQLite connection and schema (users, transactions, budgets)
    auth.py              register, login, JWT and token_required
    transactions.py      CRUD, search/filter, CSV export
    budgets.py           budgets, settings, categories, monthly summary
    utils.py             validation helpers and constants
  web/index.html         the Spendly web app (login, then all data stored via this API)
  tests/test_api.py      15 tests
```

## Design notes (useful for your report)
- **Layered design:** routes (blueprints) -> validation helpers -> database. Each module has one job.
- **Security:** passwords hashed (never stored plainly); every query filters by the logged-in user, so one user cannot read or change another's data (tested); parameterised SQL prevents SQL injection; CSV export neutralises spreadsheet formulas; request size is capped.
- **Money** is stored as integer cents to avoid floating-point errors.
- **Database tables** match Section 7 of the project document: USER, TRANSACTION, BUDGET (currency lives on the user).

## Known limitations / next steps
- No rate limiting on login (add Flask-Limiter before public deployment).
- Tokens last 24 hours and there is no refresh or logout-revocation.
- SQLite suits a single server; move to PostgreSQL for many users.
- For production use HTTPS and a real server: `gunicorn "run:app"`.
- The web app keeps the login token in the browser's localStorage; use HTTPS in production.
- The standalone `spendly.html` (browser-only, no login) still works separately; `web/index.html` is the connected version.
