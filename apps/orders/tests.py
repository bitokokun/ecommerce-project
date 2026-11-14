from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant
from .models import Order, OrderItem

User = get_user_model()


class OrderAPITests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(username="buyer", password="StrongPassword!2026")
        self.other_buyer = User.objects.create_user(username="other-buyer", password="StrongPassword!2026")
        self.seller = User.objects.create_user(
            username="seller-one", password="StrongPassword!2026", role=User.Role.SELLER
        )
        self.other_seller = User.objects.create_user(
            username="seller-two", password="StrongPassword!2026", role=User.Role.SELLER
        )
        self.category = Category.objects.create(name="Order Test Category")
        self.product = Product.objects.create(
            seller=self.seller, category=self.category, name="Order Test Product",
            base_price="10.00", status=Product.Status.ACTIVE,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, sku="ORDER-001", stock=5,
        )
        self.address = Address.objects.create(
            user=self.buyer, full_name="Buyer Name", line1="1 Test Street",
            city="Test City", postal_code="12345", country="United States",
        )
        self.cart = Cart.objects.create(user=self.buyer)
        self.client = APIClient()
        self.client.force_authenticate(user=self.buyer)

    def add_to_cart(self, quantity=2, variant=None):
        return CartItem.objects.create(
            cart=self.cart, variant=variant or self.variant, quantity=quantity
        )

    def checkout(self, address=None):
        return self.client.post(
            "/api/orders/checkout/",
            {"shipping_address_id": (address or self.address).pk},
            format="json",
        )

    def test_checkout_creates_pending_order_and_decrements_stock(self):
        self.add_to_cart(quantity=2)
        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(user=self.buyer)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total_amount, Decimal("20.00"))
        self.assertEqual(order.items.get().quantity, 2)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)
        self.assertFalse(CartItem.objects.filter(cart=self.cart).exists())

    def test_checkout_rejects_empty_cart(self):
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_checkout_rejects_insufficient_stock_without_mutation(self):
        self.add_to_cart(quantity=6)
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)
        self.assertTrue(CartItem.objects.filter(cart=self.cart).exists())

    def test_checkout_rejects_inactive_product(self):
        self.add_to_cart()
        self.product.status = Product.Status.ARCHIVED
        self.product.save(update_fields=["status"])
        response = self.checkout()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_checkout_cannot_use_another_users_address(self):
        foreign_address = Address.objects.create(
            user=self.other_buyer, full_name="Other Buyer", line1="2 Other Street",
            city="Other City", postal_code="54321", country="United States",
        )
        self.add_to_cart()
        response = self.checkout(foreign_address)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Order.objects.exists())

    def test_checkout_snapshots_product_name_and_price(self):
        self.add_to_cart(quantity=1)
        response = self.checkout()
        self.assertEqual(response.status_code, 201)
        line = OrderItem.objects.get()
        self.product.name = "Renamed Product"
        self.product.base_price = Decimal("99.00")
        self.product.save()
        self.assertEqual(line.product_name, "Order Test Product")
        self.assertEqual(line.unit_price, Decimal("10.00"))

    def test_order_history_only_contains_current_users_orders(self):
        self.add_to_cart()
        self.checkout()
        Order.objects.create(
            user=self.other_buyer, shipping_address=Address.objects.create(
                user=self.other_buyer, full_name="Other", line1="3 Other St", city="Other",
                postal_code="00000", country="United States",
            ), total_amount=Decimal("0.00"),
        )
        response = self.client.get("/api/orders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_buyer_cannot_retrieve_another_users_order(self):
        other_address = Address.objects.create(
            user=self.other_buyer, full_name="Other", line1="3 Other St", city="Other",
            postal_code="00000", country="United States",
        )
        other_order = Order.objects.create(
            user=self.other_buyer, shipping_address=other_address, total_amount=Decimal("0.00")
        )
        response = self.client.get(f"/api/orders/{other_order.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_seller_received_orders_only_include_their_own_items(self):
        other_product = Product.objects.create(
            seller=self.other_seller, category=self.category, name="Other Seller Product",
            base_price="20.00", status=Product.Status.ACTIVE,
        )
        other_variant = ProductVariant.objects.create(
            product=other_product, sku="ORDER-OTHER-001", stock=5,
        )
        order = Order.objects.create(
            user=self.buyer, shipping_address=self.address, total_amount=Decimal("30.00")
        )
        OrderItem.objects.create(
            order=order, variant=self.variant, product_name=self.product.name,
            sku=self.variant.sku, unit_price=Decimal("10.00"), quantity=1,
        )
        OrderItem.objects.create(
            order=order, variant=other_variant, product_name=other_product.name,
            sku=other_variant.sku, unit_price=Decimal("20.00"), quantity=1,
        )
        seller_client = APIClient()
        seller_client.force_authenticate(user=self.seller)
        response = seller_client.get("/api/orders/received/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        result = response.data["results"][0]
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["sku"], self.variant.sku)
        self.assertEqual(result["seller_total"], "10.00")
        self.assertNotIn("email", result["ship_to"])
        self.assertNotIn("phone_number", result["ship_to"])

    def test_received_order_count_can_be_filtered_by_since(self):
        order = Order.objects.create(
            user=self.buyer, shipping_address=self.address, total_amount=Decimal("0.00")
        )
        OrderItem.objects.create(
            order=order, variant=self.variant, product_name=self.product.name,
            sku=self.variant.sku, unit_price=Decimal("10.00"), quantity=1,
        )
        seller_client = APIClient()
        seller_client.force_authenticate(user=self.seller)
        before = (timezone.now() - timedelta(days=1)).isoformat()
        after = (timezone.now() + timedelta(days=1)).isoformat()
        self.assertEqual(seller_client.get("/api/orders/received/count/", {"since": before}).data["count"], 1)
        self.assertEqual(seller_client.get("/api/orders/received/count/", {"since": after}).data["count"], 0)
