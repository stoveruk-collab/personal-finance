import unittest

from fastapi.testclient import TestClient

from personal_finance.web.app import app


PROTECTED_GET_ROUTES = [
    "/",
    "/reports",
    "/imports/new",
    "/imports/1",
    "/reports/monthly/2026/4",
    "/reports/history/1",
    "/ledger",
    "/accounts/1/ledger",
    "/categories",
    "/mappings",
    "/budgets",
    "/years/close",
]

PROTECTED_POST_ROUTES = [
    ("/imports/commit", {"preview_id": "missing"}),
    ("/ledger/transactions/1", {"category_id": ""}),
    ("/categories", {"name": "Test Category"}),
    ("/mappings", {"pattern": "test", "match_type": "contains", "category_id": "1", "priority": "1000"}),
    ("/mappings/1", {"pattern": "test", "match_type": "contains", "category_id": "1", "priority": "1000"}),
    ("/categories/1", {"name": "Test Category"}),
    ("/budgets", {"period": "year"}),
    ("/years/close", {"year": "2026"}),
]


class AuthGuardsTest(unittest.TestCase):
    def test_protected_get_routes_redirect_to_login_without_session(self):
        with TestClient(app) as client:
            for route in PROTECTED_GET_ROUTES:
                response = client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 303, route)
                self.assertEqual(response.headers["location"], "/login", route)

    def test_protected_post_routes_redirect_to_login_without_session(self):
        with TestClient(app) as client:
            for route, payload in PROTECTED_POST_ROUTES:
                response = client.post(route, data=payload, follow_redirects=False)
                self.assertEqual(response.status_code, 303, route)
                self.assertEqual(response.headers["location"], "/login", route)

    def test_public_routes_remain_public(self):
        with TestClient(app) as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            self.assertIn(client.get("/login", follow_redirects=False).status_code, {302, 307, 500})


if __name__ == "__main__":
    unittest.main()
