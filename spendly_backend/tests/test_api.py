"""API tests. Run with:  python -m unittest discover -s tests -v   (pytest also works)"""
import os
import tempfile
import unittest

from spendly import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app({"TESTING": True, "DATABASE": self.path, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()

    def tearDown(self):
        os.remove(self.path)

    # helpers
    def register(self, email="a@example.com", name="Asha", password="password123"):
        r = self.client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
        self.assertEqual(r.status_code, 201, r.get_json())
        return {"Authorization": "Bearer " + r.get_json()["token"]}

    def add(self, h, **kw):
        body = {"type": "expense", "amount": 100, "category": "Food", "date": "2026-10-05", "note": "x"}
        body.update(kw)
        return self.client.post("/api/transactions", json=body, headers=h)


class AuthTests(ApiTestCase):
    def test_register_login_me(self):
        h = self.register()
        self.assertEqual(self.client.get("/api/auth/me", headers=h).get_json()["user"]["email"], "a@example.com")
        r = self.client.post("/api/auth/login", json={"email": "A@Example.com", "password": "password123"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.get_json())

    def test_duplicate_email(self):
        self.register()
        r = self.client.post("/api/auth/register", json={"name": "B", "email": "a@example.com", "password": "password123"})
        self.assertEqual(r.status_code, 409)

    def test_bad_registration(self):
        for body in ({"name": "", "email": "a@b.co", "password": "password123"},
                     {"name": "A", "email": "nope", "password": "password123"},
                     {"name": "A", "email": "a@b.co", "password": "short"}):
            self.assertEqual(self.client.post("/api/auth/register", json=body).status_code, 400)

    def test_wrong_password_and_unknown_user(self):
        self.register()
        for body in ({"email": "a@example.com", "password": "wrongpass1"},
                     {"email": "ghost@example.com", "password": "password123"}):
            r = self.client.post("/api/auth/login", json=body)
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.get_json()["error"], "Invalid email or password")

    def test_protected_routes_need_token(self):
        self.assertEqual(self.client.get("/api/transactions").status_code, 401)
        r = self.client.get("/api/transactions", headers={"Authorization": "Bearer garbage"})
        self.assertEqual(r.status_code, 401)

    def test_expired_token(self):
        self.app.config["TOKEN_HOURS"] = -1
        h = self.register()
        self.assertEqual(self.client.get("/api/auth/me", headers=h).status_code, 401)


class TransactionTests(ApiTestCase):
    def test_crud(self):
        h = self.register()
        r = self.add(h, amount=250.5, note="Lunch")
        self.assertEqual(r.status_code, 201)
        tx = r.get_json()["transaction"]
        self.assertEqual(tx["amount"], 250.5)
        tid = tx["id"]
        r = self.client.put(f"/api/transactions/{tid}", headers=h, json={
            "type": "expense", "amount": 300, "category": "Bills", "date": "2026-10-06", "note": "Edited"})
        self.assertEqual(r.get_json()["transaction"]["category"], "Bills")
        self.assertEqual(self.client.get(f"/api/transactions/{tid}", headers=h).get_json()["transaction"]["amount"], 300)
        self.assertEqual(self.client.delete(f"/api/transactions/{tid}", headers=h).status_code, 204)
        self.assertEqual(self.client.get(f"/api/transactions/{tid}", headers=h).status_code, 404)

    def test_validation(self):
        h = self.register()
        bad = [dict(amount=0), dict(amount=-5), dict(amount="abc"), dict(amount=True), dict(amount=1e20),
               dict(type="gift"), dict(category="Pets"), dict(date="2026-13-40"), dict(date="05/10/2026"),
               dict(note="x" * 81)]
        for change in bad:
            self.assertEqual(self.add(h, **change).status_code, 400, change)

    def test_amount_rounds_to_cents(self):
        h = self.register()
        self.assertEqual(self.add(h, amount="10.005").get_json()["transaction"]["amount"], 10.01)

    def test_users_are_isolated(self):
        a = self.register("a@example.com")
        b = self.register("b@example.com")
        tid = self.add(a).get_json()["transaction"]["id"]
        self.assertEqual(self.client.get("/api/transactions", headers=b).get_json()["count"], 0)
        self.assertEqual(self.client.get(f"/api/transactions/{tid}", headers=b).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/transactions/{tid}", headers=b).status_code, 404)
        self.assertEqual(self.client.put(f"/api/transactions/{tid}", headers=b, json={
            "type": "expense", "amount": 1, "category": "Food", "date": "2026-10-01"}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/transactions/{tid}", headers=a).status_code, 200)

    def test_filters_and_search(self):
        h = self.register()
        self.add(h, date="2026-10-02", category="Food", note="Groceries")
        self.add(h, date="2026-10-03", category="Rent", note="100% rent_due")
        self.add(h, date="2026-09-30", category="Food", note="Old")
        self.add(h, date="2026-10-04", type="income", category="Other", amount=5000)
        get = lambda q: self.client.get("/api/transactions" + q, headers=h).get_json()
        self.assertEqual(get("?month=2026-10")["count"], 3)
        self.assertEqual(get("?month=2026-10&category=Food")["count"], 1)
        self.assertEqual(get("?q=grocer")["count"], 1)
        self.assertEqual(get("?q=%25")["count"], 1)            # a literal % is not a wildcard
        self.assertEqual(get("?type=income")["count"], 1)
        self.assertEqual(get("?month=2026-10")["transactions"][0]["date"], "2026-10-04")  # newest first
        self.assertEqual(self.client.get("/api/transactions?month=2026-1", headers=h).status_code, 400)

    def test_csv_export_and_formula_guard(self):
        h = self.register()
        self.add(h, note="=HYPERLINK(1)", amount=12.5)
        r = self.client.get("/api/transactions/export?month=2026-10", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.mimetype == "text/csv")
        lines = r.get_data(as_text=True).strip().splitlines()
        self.assertEqual(lines[0], "date,type,category,amount,note")
        self.assertIn("12.50", lines[1])
        self.assertIn("'=HYPERLINK(1)", lines[1])


class BudgetSummaryTests(ApiTestCase):
    def test_summary_and_budget_status(self):
        h = self.register()
        m = "2026-10"
        self.add(h, type="income", category="Other", amount=25000)
        self.add(h, amount=1800, category="Food")
        self.add(h, amount=9000, category="Rent")
        s = self.client.get(f"/api/summary?month={m}", headers=h).get_json()
        self.assertEqual((s["income"], s["spent"], s["balance"]), (25000, 10800, 14200))
        self.assertEqual(s["budget_status"], "no_budget")
        self.assertEqual(s["by_category"][0], {"category": "Rent", "total": 9000})

        def status(budget):
            self.client.put(f"/api/budgets/{m}", headers=h, json={"amount": budget})
            return self.client.get(f"/api/summary?month={m}", headers=h).get_json()
        self.assertEqual(status(20000)["budget_status"], "on_track")        # 54%
        self.assertEqual(status(12000)["budget_status"], "close_to_limit")  # 90%
        self.assertEqual(status(10800)["budget_status"], "close_to_limit")  # exactly 100%
        over = status(10000)
        self.assertEqual(over["budget_status"], "over_budget")
        self.assertEqual(over["over_by"], 800)
        self.assertEqual(status(0)["budget_status"], "no_budget")           # 0 clears it

    def test_budget_validation_and_settings(self):
        h = self.register()
        self.assertEqual(self.client.put("/api/budgets/2026-10", headers=h, json={"amount": -1}).status_code, 400)
        self.assertEqual(self.client.put("/api/budgets/bad", headers=h, json={"amount": 5}).status_code, 400)
        self.assertEqual(self.client.put("/api/settings", headers=h, json={"currency": "$"}).get_json()["currency"], "$")
        self.assertEqual(self.client.put("/api/settings", headers=h, json={"currency": "X"}).status_code, 400)
        self.assertEqual(self.client.get("/api/settings", headers=h).get_json()["currency"], "$")


class MiscTests(ApiTestCase):
    def test_health_categories_errors_cors(self):
        self.assertEqual(self.client.get("/api/health").get_json(), {"status": "ok"})
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Spendly", page.data)
        self.assertEqual(len(self.client.get("/api/categories").get_json()["categories"]), 9)
        r = self.client.get("/api/nothing")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.get_json())
        r = self.client.post("/api/auth/login", data="not json", content_type="text/plain")
        self.assertEqual(r.status_code, 400)
        r = self.client.options("/api/transactions", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(r.headers["Access-Control-Allow-Origin"], "*")


if __name__ == "__main__":
    unittest.main()
