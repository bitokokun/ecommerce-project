from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Address
from apps.catalog.models import Product, ProductVariant
from apps.orders.models import Order, OrderItem
from config.errors import api_exception_handler

User = get_user_model()
PASSWORD = "StrongPassword!2026"


class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.customer = User.objects.create_user("customer", "c@example.com", PASSWORD)
        self.seller_a = User.objects.create_user("seller_a", "a@example.com", PASSWORD, role="seller")
        self.seller_b = User.objects.create_user("seller_b", "b@example.com", PASSWORD, role="seller")
        self.staff = User.objects.create_user("staff", "s@example.com", PASSWORD, is_staff=True)
        self.product_a = Product.objects.create(seller=self.seller_a, name="A", base_price="10.00")
        self.variant_a = ProductVariant.objects.create(product=self.product_a, sku="A-1", stock=5)
        self.product_b = Product.objects.create(seller=self.seller_b, name="B", base_price="10.00")
        self.variant_b = ProductVariant.objects.create(product=self.product_b, sku="B-1", stock=5)

    def as_user(self, user=None):
        client = APIClient()
        if user:
            client.force_authenticate(user)
        return client

    def place_order(self, variant, quantity=1):
        address = Address.objects.create(
            user=self.customer, full_name="C", line1="1", city="c", postal_code="1", country="Portugal"
        )
        order = Order.objects.create(user=self.customer, shipping_address=address, total_amount="10.00")
        OrderItem.objects.create(
            order=order, variant=variant, product_name="x", sku=variant.sku, unit_price="10.00", quantity=quantity
        )
        return order


class AuthenticationRequiredTests(ApiTestCase):
    def test_protected_endpoints_reject_anonymous_users(self):
        order = self.place_order(self.variant_a)
        protected = [
            ("get", "/api/accounts/me/"),
            ("patch", "/api/accounts/me/"),
            ("get", "/api/accounts/addresses/"),
            ("post", "/api/accounts/me/avatar/"),
            ("post", "/api/accounts/password/"),
            ("post", "/api/accounts/delete/"),
            ("get", "/api/accounts/store/"),
            ("patch", "/api/accounts/store/"),
            ("get", "/api/orders/"),
            ("get", f"/api/orders/{order.pk}/"),
            ("post", f"/api/orders/{order.pk}/cancel/"),
            ("post", "/api/orders/checkout/"),
            ("get", "/api/orders/received/"),
            ("post", f"/api/orders/received/{order.pk}/fulfil/"),
            ("get", "/api/orders/seller-stats/"),
            ("get", "/api/orders/admin-stats/"),
            ("get", "/api/catalog/wishlist/"),
            ("post", "/api/catalog/wishlist/"),
            ("get", "/api/catalog/wishlist/ids/"),
            ("post", "/api/catalog/products/"),
            ("patch", f"/api/catalog/products/{self.product_a.pk}/"),
            ("delete", f"/api/catalog/products/{self.product_a.pk}/"),
            ("post", f"/api/catalog/products/{self.product_a.pk}/variants/"),
            ("get", f"/api/catalog/products/{self.product_a.pk}/variants/"),
            ("post", f"/api/catalog/products/{self.product_a.pk}/images/upload/"),
            ("get", "/api/catalog/products/mine/"),
        ]
        client = self.as_user()
        for method, url in protected:
            response = getattr(client, method)(url)
            self.assertEqual(response.status_code, 401, f"{method.upper()} {url} -> {response.status_code}")

    def test_public_endpoints_are_open(self):
        client = self.as_user()
        for url in (
            "/api/catalog/products/",
            f"/api/catalog/products/{self.product_a.pk}/",
            "/api/catalog/categories/",
            "/api/cart/",
            "/api/accounts/countries/",
        ):
            self.assertEqual(client.get(url).status_code, 200, url)


class RoleTests(ApiTestCase):
    def test_customers_cannot_use_seller_or_staff_endpoints(self):
        client = self.as_user(self.customer)
        self.assertEqual(client.get("/api/accounts/store/").status_code, 403)
        self.assertEqual(client.get("/api/orders/seller-stats/").status_code, 403)
        self.assertEqual(client.get("/api/orders/admin-stats/").status_code, 403)
        response = client.post("/api/catalog/products/", {"name": "X", "base_price": "5.00"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_sellers_cannot_use_staff_endpoints(self):
        self.assertEqual(self.as_user(self.seller_a).get("/api/orders/admin-stats/").status_code, 403)

    def test_staff_can_read_platform_stats(self):
        self.assertEqual(self.as_user(self.staff).get("/api/orders/admin-stats/").status_code, 200)

    def test_role_cannot_be_changed_through_the_profile_endpoint(self):
        client = self.as_user(self.customer)
        client.patch("/api/accounts/me/", {"role": "seller", "is_staff": True, "is_superuser": True}, format="json")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.role, "customer")
        self.assertFalse(self.customer.is_staff)
        self.assertFalse(self.customer.is_superuser)


class OwnershipTests(ApiTestCase):
    def test_seller_cannot_modify_another_sellers_product(self):
        client = self.as_user(self.seller_a)
        url = f"/api/catalog/products/{self.product_b.pk}/"
        self.assertEqual(client.patch(url, {"name": "Hacked"}, format="json").status_code, 403)
        self.assertEqual(client.delete(url).status_code, 403)
        self.product_b.refresh_from_db()
        self.assertEqual(self.product_b.name, "B")

    def test_seller_cannot_touch_another_sellers_variants(self):
        client = self.as_user(self.seller_a)
        base = f"/api/catalog/products/{self.product_b.pk}/variants/"
        self.assertEqual(client.get(base).json().get("results", client.get(base).json()), [])
        self.assertEqual(client.post(base, {"sku": "NEW-1", "stock": 9}, format="json").status_code, 403)
        detail = f"{base}{self.variant_b.pk}/"
        self.assertEqual(client.patch(detail, {"stock": 999}, format="json").status_code, 404)
        self.assertEqual(client.delete(detail).status_code, 404)
        self.variant_b.refresh_from_db()
        self.assertEqual(self.variant_b.stock, 5)

    def test_seller_cannot_upload_images_to_another_sellers_product(self):
        response = self.as_user(self.seller_a).post(
            f"/api/catalog/products/{self.product_b.pk}/images/upload/", {}, format="multipart"
        )
        self.assertIn(response.status_code, (403, 404))

    def test_product_images_must_be_jpeg_png_or_webp(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        def upload(fmt):
            buffer = io.BytesIO()
            Image.new("RGB", (10, 10)).save(buffer, fmt)
            name = f"x.{fmt.lower()}"
            file = SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")
            return self.as_user(self.seller_a).post(
                f"/api/catalog/products/{self.product_a.pk}/images/upload/", {"image": file}, format="multipart"
            )

        self.assertEqual(upload("GIF").status_code, 400)
        self.assertEqual(upload("BMP").status_code, 400)
        self.assertEqual(upload("PNG").status_code, 201)

    def test_buyers_only_see_their_own_orders(self):
        order = self.place_order(self.variant_a)
        other = User.objects.create_user("other", "o@example.com", PASSWORD)
        client = self.as_user(other)
        self.assertEqual(client.get(f"/api/orders/{order.pk}/").status_code, 404)
        self.assertEqual(client.post(f"/api/orders/{order.pk}/cancel/").status_code, 404)
        listing = client.get("/api/orders/").json()
        self.assertEqual(listing.get("results", listing), [])

    def test_sellers_only_see_orders_containing_their_products(self):
        order = self.place_order(self.variant_a)
        self.assertEqual(len(self.as_user(self.seller_a).get("/api/orders/received/").json()["results"]), 1)
        self.assertEqual(self.as_user(self.seller_b).get("/api/orders/received/").json()["results"], [])
        response = self.as_user(self.seller_b).post(
            f"/api/orders/received/{order.pk}/fulfil/", {"status": "shipped"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(OrderItem.objects.get().fulfilment_status, "pending")

    def test_seller_stats_never_include_other_sellers_sales(self):
        self.place_order(self.variant_a, 2)
        stats = self.as_user(self.seller_b).get("/api/orders/seller-stats/").json()
        self.assertEqual(stats["units_sold"], 0)
        self.assertEqual(stats["revenue"], "0.00")


class CatalogIntegrityTests(ApiTestCase):
    def test_deleting_an_ordered_product_archives_it_and_keeps_the_order_link(self):
        order = self.place_order(self.variant_a)
        response = self.as_user(self.seller_a).delete(f"/api/catalog/products/{self.product_a.pk}/")
        self.assertEqual(response.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.status, Product.Status.ARCHIVED)
        self.assertEqual(OrderItem.objects.get(order=order).variant_id, self.variant_a.pk)
        self.assertEqual(len(self.as_user(self.seller_a).get("/api/orders/received/").json()["results"]), 1)

    def test_deleting_an_unordered_product_removes_it(self):
        response = self.as_user(self.seller_a).delete(f"/api/catalog/products/{self.product_a.pk}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Product.objects.filter(pk=self.product_a.pk).exists())

    def test_ordered_variants_cannot_be_deleted(self):
        self.place_order(self.variant_a)
        url = f"/api/catalog/products/{self.product_a.pk}/variants/{self.variant_a.pk}/"
        self.assertEqual(self.as_user(self.seller_a).delete(url).status_code, 409)
        self.assertTrue(ProductVariant.objects.filter(pk=self.variant_a.pk).exists())

    def test_unordered_variants_can_be_deleted(self):
        url = f"/api/catalog/products/{self.product_a.pk}/variants/{self.variant_a.pk}/"
        self.assertEqual(self.as_user(self.seller_a).delete(url).status_code, 204)

    def test_negative_stock_is_rejected(self):
        url = f"/api/catalog/products/{self.product_a.pk}/variants/{self.variant_a.pk}/"
        self.assertEqual(self.as_user(self.seller_a).patch(url, {"stock": -3}, format="json").status_code, 400)


class ErrorHandlingTests(ApiTestCase):
    def test_unknown_api_paths_return_json(self):
        response = self.as_user().get("/api/does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": "Not found."})

    def test_protected_errors_become_conflicts(self):
        response = api_exception_handler(ProtectedError("x", []), {})
        self.assertEqual(response.status_code, 409)

    def test_wrong_methods_return_json(self):
        response = self.as_user(self.customer).delete("/api/orders/checkout/")
        self.assertEqual(response.status_code, 405)
        self.assertIn("detail", response.json())

    def test_malformed_json_is_a_client_error(self):
        response = self.as_user(self.customer).post(
            "/api/orders/checkout/", data="{not json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


class ApiDocumentationTests(ApiTestCase):
    def test_schema_describes_checkout_and_idempotency(self):
        response = self.as_user().get("/api/schema/?format=json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("/api/orders/checkout/", schema["paths"])
        parameters = schema["paths"]["/api/orders/checkout/"]["post"]["parameters"]
        self.assertIn("Idempotency-Key", [p["name"] for p in parameters])
        for path in ("/api/auth/token/", "/api/auth/logout/", "/api/catalog/wishlist/", "/api/cart/"):
            self.assertIn(path, schema["paths"])

    def test_swagger_ui_is_served(self):
        self.assertEqual(self.as_user().get("/api/docs/").status_code, 200)
