from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

User = get_user_model()
PASSWORD = "StrongPassword!2026"
NEW_PASSWORD = "AnotherStrong!2027"


class TokenFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)
        self.client = APIClient()

    def login(self, client=None):
        return (client or self.client).post(
            "/api/auth/token/", {"username": "ana", "password": PASSWORD}, format="json"
        )

    def test_login_returns_both_tokens_by_default(self):
        data = self.login().json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertNotIn("refresh_token", self.login().cookies)

    def test_wrong_password_is_rejected(self):
        response = self.client.post("/api/auth/token/", {"username": "ana", "password": "nope"}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_refresh_rotates_and_revokes_the_old_token(self):
        old = self.login().json()["refresh"]
        rotated = self.client.post("/api/auth/token/refresh/", {"refresh": old}, format="json")
        self.assertEqual(rotated.status_code, 200, rotated.content)
        self.assertNotEqual(rotated.json()["refresh"], old)
        reused = self.client.post("/api/auth/token/refresh/", {"refresh": old}, format="json")
        self.assertEqual(reused.status_code, 401)

    def test_logout_revokes_the_refresh_token(self):
        refresh = self.login().json()["refresh"]
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json").status_code, 204)
        after = self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(after.status_code, 401)

    def test_logout_with_garbage_is_harmless(self):
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": "garbage"}, format="json").status_code, 204)
        self.assertEqual(self.client.post("/api/auth/logout/", {}, format="json").status_code, 204)

    def test_password_change_revokes_every_session(self):
        first = self.login().json()
        second = self.login(APIClient()).json()
        authed = APIClient()
        authed.credentials(HTTP_AUTHORIZATION=f"Bearer {first['access']}")
        response = authed.post(
            "/api/accounts/password/",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        for refresh in (first["refresh"], second["refresh"]):
            self.assertEqual(
                self.client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json").status_code, 401
            )

    def test_deactivated_user_cannot_use_an_existing_access_token(self):
        access = self.login().json()["access"]
        self.user.is_active = False
        self.user.save()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(client.get("/api/accounts/me/").status_code, 401)

    def test_tampered_access_token_is_rejected(self):
        access = self.login().json()["access"]
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access[:-4]}abcd")
        self.assertEqual(client.get("/api/accounts/me/").status_code, 401)


@override_settings(AUTH_REFRESH_COOKIE=True)
class CookieModeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("ana", "ana@example.com", PASSWORD)
        self.client = APIClient()

    def login(self):
        return self.client.post("/api/auth/token/", {"username": "ana", "password": PASSWORD}, format="json")

    def test_refresh_token_lives_in_an_httponly_cookie_only(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("refresh", response.json())
        cookie = response.cookies["refresh_token"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], "/api/auth/")
        self.assertEqual(cookie["samesite"], "Lax")

    def test_refresh_uses_the_cookie_and_rotates_it(self):
        first = self.login().cookies["refresh_token"].value
        response = self.client.post("/api/auth/token/refresh/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("access", response.json())
        self.assertNotIn("refresh", response.json())
        self.assertNotEqual(response.cookies["refresh_token"].value, first)

    def test_refresh_without_a_cookie_fails(self):
        self.assertEqual(self.client.post("/api/auth/token/refresh/", {}, format="json").status_code, 400)

    def test_logout_clears_the_cookie_and_revokes_the_token(self):
        stolen = self.login().cookies["refresh_token"].value
        response = self.client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies["refresh_token"].value, "")
        replay = APIClient().post("/api/auth/token/refresh/", {"refresh": stolen}, format="json")
        self.assertEqual(replay.status_code, 401)
