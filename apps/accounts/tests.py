from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .countries import COUNTRY_LOOKUP
from .models import Address


User = get_user_model()


class AccountAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = "StrongPassword!2026"

        self.user = User.objects.create_user(
            username="customer1",
            email="customer@example.com",
            password=self.password,
            role=User.Role.CUSTOMER,
        )

        self.other_user = User.objects.create_user(
            username="customer2",
            email="other@example.com",
            password=self.password,
            role=User.Role.CUSTOMER,
        )

    @patch("apps.accounts.views.verify_turnstile", return_value=True)
    def test_customer_registration(self, mock_captcha):
        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "newcustomer",
                "email": "new@example.com",
                "password": self.password,
                "role": "customer",
            },
        )

        self.assertEqual(response.status_code, 201)

        new_user = User.objects.get(username="newcustomer")
        self.assertTrue(new_user.check_password(self.password))
        self.assertNotEqual(new_user.password, self.password)
        mock_captcha.assert_called_once()

    @patch("apps.accounts.views.verify_turnstile", return_value=True)
    def test_registration_rejects_admin_role(self, mock_captcha):
        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "adminattempt",
                "email": "adminattempt@example.com",
                "password": self.password,
                "role": "admin",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            User.objects.filter(username="adminattempt").exists()
        )

    @patch("apps.accounts.views.verify_turnstile", return_value=False)
    def test_registration_rejects_failed_captcha(self, mock_captcha):
        response = self.client.post(
            "/api/accounts/register/",
            {
                "username": "captchauser",
                "email": "captcha@example.com",
                "password": self.password,
                "role": "customer",
                "captcha_token": "invalid-token",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            User.objects.filter(username="captchauser").exists()
        )

    def test_profile_requires_authentication(self):
        response = self.client.get("/api/accounts/me/")

        self.assertEqual(response.status_code, 401)

    def test_user_cannot_change_own_role(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            "/api/accounts/me/",
            {"role": "admin"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.Role.CUSTOMER)

    def test_user_can_update_own_phone_number(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            "/api/accounts/me/",
            {"phone_number": "1234567890"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "1234567890")

    def test_user_cannot_access_another_users_address(self):
        address = Address.objects.create(
            user=self.other_user,
            full_name="Other Customer",
            line1="123 Example Street",
            city="Example City",
            postal_code="12345",
            country=next(iter(COUNTRY_LOOKUP.values())),
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            f"/api/accounts/addresses/{address.pk}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_user_can_only_see_own_addresses(self):
        Address.objects.create(
            user=self.user,
            full_name="Customer One",
            line1="123 First Street",
            city="Example City",
            postal_code="11111",
            country=next(iter(COUNTRY_LOOKUP.values())),
        )

        Address.objects.create(
            user=self.other_user,
            full_name="Customer Two",
            line1="456 Second Street",
            city="Example City",
            postal_code="22222",
            country=next(iter(COUNTRY_LOOKUP.values())),
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/accounts/addresses/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_only_one_default_address_per_user(self):
        self.client.force_authenticate(user=self.user)

        country = next(iter(COUNTRY_LOOKUP.values()))

        first_response = self.client.post(
            "/api/accounts/addresses/",
            {
                "full_name": "Customer One",
                "line1": "123 First Street",
                "city": "Example City",
                "postal_code": "11111",
                "country": country,
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(first_response.status_code, 201)

        second_response = self.client.post(
            "/api/accounts/addresses/",
            {
                "full_name": "Customer One",
                "line1": "456 Second Street",
                "city": "Example City",
                "postal_code": "22222",
                "country": country,
                "is_default": True,
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, 201)

        default_addresses = Address.objects.filter(
            user=self.user,
            is_default=True,
        )

        self.assertEqual(default_addresses.count(), 1)


    def test_address_used_by_order_cannot_be_deleted(self):
        from decimal import Decimal
        from apps.orders.models import Order

        address = Address.objects.create(
            user=self.user,
            full_name="Customer One",
            line1="123 First Street",
            city="Example City",
            postal_code="11111",
            country=next(iter(COUNTRY_LOOKUP.values())),
        )
        Order.objects.create(user=self.user, shipping_address=address, total_amount=Decimal("0.00"))
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(f"/api/accounts/addresses/{address.pk}/")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Address.objects.filter(pk=address.pk).exists())
