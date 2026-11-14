from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address
from apps.catalog.models import Product, ProductVariant
from .models import Order, OrderItem

User = get_user_model()
PW = "StrongPassword!2026"


class FulfilmentTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user("buyer", "b@example.com", PW)
        self.s1 = User.objects.create_user("s1", "s1@example.com", PW, role="seller")
        self.s2 = User.objects.create_user("s2", "s2@example.com", PW, role="seller")
        p1 = Product.objects.create(seller=self.s1, name="One", base_price="10.00")
        p2 = Product.objects.create(seller=self.s2, name="Two", base_price="20.00")
        self.v1 = ProductVariant.objects.create(product=p1, sku="S1-A", stock=8)
        self.v1b = ProductVariant.objects.create(product=p1, sku="S1-B", stock=8)
        self.v2 = ProductVariant.objects.create(product=p2, sku="S2-A", stock=8)
        addr = Address.objects.create(user=self.buyer, full_name="B", line1="1", city="c", postal_code="1", country="Portugal")
        self.order = Order.objects.create(user=self.buyer, shipping_address=addr, total_amount="50.00")
        self.i1 = OrderItem.objects.create(order=self.order, variant=self.v1, product_name="One", sku="S1-A", unit_price="10.00", quantity=1)
        self.i1b = OrderItem.objects.create(order=self.order, variant=self.v1b, product_name="One", sku="S1-B", unit_price="10.00", quantity=1)
        self.i2 = OrderItem.objects.create(order=self.order, variant=self.v2, product_name="Two", sku="S2-A", unit_price="20.00", quantity=1)
        self.api = APIClient()

    def test_seller_ships_only_own_lines(self):
        self.api.force_authenticate(self.s1)
        r = self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/",
                          {"status": "shipped", "carrier": "DHL", "tracking_number": "123"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        for i in (self.i1, self.i1b, self.i2):
            i.refresh_from_db()
        self.assertEqual(self.i1.fulfilment_status, "shipped")
        self.assertEqual(self.i1b.tracking_number, "123")
        self.assertEqual(self.i2.fulfilment_status, "pending")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")

    def test_order_delivered_only_when_every_seller_delivered(self):
        for seller in (self.s1, self.s2):
            self.api.force_authenticate(seller)
            self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "delivered"}, format="json")
            self.order.refresh_from_db()
            if seller == self.s1:
                self.assertEqual(self.order.status, "shipped")
        self.assertEqual(self.order.status, "delivered")

    def test_seller_without_products_in_order_gets_404(self):
        s3 = User.objects.create_user("s3", "s3@example.com", PW, role="seller")
        self.api.force_authenticate(s3)
        r = self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "shipped"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_buyer_cannot_fulfil(self):
        self.api.force_authenticate(self.buyer)
        r = self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "shipped"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_cannot_move_backwards(self):
        self.api.force_authenticate(self.s1)
        self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "delivered"}, format="json")
        r = self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "shipped"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cancel_restocks(self):
        self.api.force_authenticate(self.buyer)
        r = self.api.post(f"/api/orders/{self.order.pk}/cancel/")
        self.assertEqual(r.status_code, 200, r.content)
        self.v1.refresh_from_db()
        self.assertEqual(self.v1.stock, 9)
        self.assertEqual(self.api.post(f"/api/orders/{self.order.pk}/cancel/").status_code, 400)
        self.assertEqual(self.v1.stock, 9)

    def test_cannot_cancel_after_shipping_or_others_orders(self):
        self.api.force_authenticate(self.s1)
        self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "shipped"}, format="json")
        self.api.force_authenticate(self.buyer)
        self.assertEqual(self.api.post(f"/api/orders/{self.order.pk}/cancel/").status_code, 409)
        other = User.objects.create_user("other", "o@example.com", PW)
        self.api.force_authenticate(other)
        self.assertEqual(self.api.post(f"/api/orders/{self.order.pk}/cancel/").status_code, 404)

    def test_seller_cannot_fulfil_cancelled_order(self):
        self.api.force_authenticate(self.buyer)
        self.api.post(f"/api/orders/{self.order.pk}/cancel/")
        self.api.force_authenticate(self.s1)
        r = self.api.post(f"/api/orders/received/{self.order.pk}/fulfil/", {"status": "shipped"}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_stats_are_scoped_to_seller(self):
        self.api.force_authenticate(self.s1)
        r = self.api.get("/api/orders/seller-stats/").json()
        self.assertEqual(r["revenue"], "20.00")
        self.assertEqual(r["units_sold"], 2)
        self.api.force_authenticate(self.s2)
        self.assertEqual(self.api.get("/api/orders/seller-stats/").json()["revenue"], "20.00")
        self.api.force_authenticate(self.buyer)
        self.assertEqual(self.api.get("/api/orders/seller-stats/").status_code, 403)

    def test_admin_stats_staff_only(self):
        self.api.force_authenticate(self.s1)
        self.assertEqual(self.api.get("/api/orders/admin-stats/").status_code, 403)
        staff = User.objects.create_user("staff", "st@example.com", PW, is_staff=True)
        self.api.force_authenticate(staff)
        r = self.api.get("/api/orders/admin-stats/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["gross_sales"], "40.00")
