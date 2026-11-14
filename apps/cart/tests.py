import unittest

from .validation import MAX_QUANTITY, parse_id, parse_quantity


class QuantityTests(unittest.TestCase):
    def test_normal_values(self):
        self.assertEqual(parse_quantity(3), 3)
        self.assertEqual(parse_quantity("3"), 3)
        self.assertEqual(parse_quantity(3.0), 3)
        self.assertEqual(parse_quantity(MAX_QUANTITY), MAX_QUANTITY)

    def test_missing_means_one(self):
        self.assertEqual(parse_quantity(None), 1)
        self.assertEqual(parse_quantity(""), 1)

    def test_rejects_zero_negative_and_too_many(self):
        for bad in (0, -1, -5, "-2", MAX_QUANTITY + 1, 10**9):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_quantity(bad)

    def test_rejects_non_whole_and_non_numbers(self):
        for bad in (2.7, "2.5", "abc", "1e3", True, [], {}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_quantity(bad)

    def test_error_message_is_human(self):
        with self.assertRaises(ValueError) as ctx:
            parse_quantity(-1)
        self.assertIn("1 to 99", str(ctx.exception))


class IdTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_id(7), 7)
        self.assertEqual(parse_id("7"), 7)

    def test_rejects_junk(self):
        for bad in (None, "", "abc", 0, -3, 1.5, True, [], "1; DROP TABLE"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_id(bad, "variant")


if __name__ == "__main__":
    unittest.main()


from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.catalog.models import Category, Product, ProductVariant
from .models import Cart, CartItem


class CartAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cart-user", password="StrongPassword!2026")
        self.other_user = User.objects.create_user(username="other-cart-user", password="StrongPassword!2026")
        self.seller = User.objects.create_user(
            username="cart-seller", password="StrongPassword!2026", role="seller"
        )
        self.category = Category.objects.create(name="Cart Test Category")
        self.product = Product.objects.create(
            seller=self.seller, category=self.category, name="Cart Test Product",
            base_price="12.50", status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, sku="CART-TEST-001", stock=5
        )
        self.other_variant = ProductVariant.objects.create(
            product=self.product, sku="CART-TEST-002", stock=8
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_add_item_creates_cart_and_item(self):
        response = self.client.post(
            "/api/cart/items/", {"variant": self.variant.pk, "quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["item_count"], 2)
        self.assertEqual(response.data["total"], "25.00")
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_adding_same_variant_increments_existing_line(self):
        for quantity in (1, 2):
            response = self.client.post(
                "/api/cart/items/", {"variant": self.variant.pk, "quantity": quantity}, format="json"
            )
            self.assertEqual(response.status_code, 201)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(CartItem.objects.get().quantity, 3)

    def test_add_rejects_quantity_above_stock(self):
        response = self.client.post(
            "/api/cart/items/", {"variant": self.variant.pk, "quantity": 6}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CartItem.objects.exists())

    def test_add_rejects_invalid_variant_id(self):
        response = self.client.post(
            "/api/cart/items/", {"variant": "not-an-id", "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_add_rejects_inactive_product(self):
        self.product.status = Product.Status.ARCHIVED
        self.product.save(update_fields=["status"])
        response = self.client.post(
            "/api/cart/items/", {"variant": self.variant.pk, "quantity": 1}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CartItem.objects.exists())

    def test_update_changes_quantity(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        response = self.client.patch(
            f"/api/cart/items/{item.pk}/", {"quantity": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)

    def test_update_cannot_change_variant(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        response = self.client.patch(
            f"/api/cart/items/{item.pk}/", {"variant": self.other_variant.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.variant_id, self.variant.pk)

    def test_update_rejects_quantity_above_stock(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, variant=self.variant, quantity=1)
        response = self.client.patch(
            f"/api/cart/items/{item.pk}/", {"quantity": 6}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_user_cannot_update_another_users_cart_item(self):
        other_cart = Cart.objects.create(user=self.other_user)
        item = CartItem.objects.create(cart=other_cart, variant=self.variant, quantity=1)
        response = self.client.patch(
            f"/api/cart/items/{item.pk}/", {"quantity": 2}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_user_cannot_delete_another_users_cart_item(self):
        other_cart = Cart.objects.create(user=self.other_user)
        item = CartItem.objects.create(cart=other_cart, variant=self.variant, quantity=1)
        response = self.client.delete(f"/api/cart/items/{item.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())

    def test_guest_sessions_receive_separate_carts(self):
        guest_one = APIClient()
        guest_two = APIClient()
        first = guest_one.get("/api/cart/")
        second = guest_two.get("/api/cart/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.data["id"], second.data["id"])
