from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.accounts.models import Address, SellerProfile
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Category, Product, ProductVariant, Review, WishlistItem
from apps.orders.models import Order, OrderItem

User = get_user_model()
PASSWORD = "StrongPassword!2026"


def count_queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return len(ctx)


class QueryCountTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Home goods")
        self.seller = User.objects.create_user("seller", "s@example.com", PASSWORD, role="seller")
        SellerProfile.objects.create(user=self.seller, store_name="Kiln")
        self.buyer = User.objects.create_user("buyer", "b@example.com", PASSWORD)
        self.client = APIClient()
        self.client.force_authenticate(self.buyer)
        self.seller_client = APIClient()
        self.seller_client.force_authenticate(self.seller)
        self.counter = 0

    def product(self, stock=5):
        self.counter += 1
        product = Product.objects.create(
            seller=self.seller, name=f"Item {self.counter}", base_price="10.00", category=self.category
        )
        variant = ProductVariant.objects.create(product=product, sku=f"SKU-{self.counter}", stock=stock)
        return product, variant

    def assertConstant(self, url, grow, client=None, slack=0):
        client = client or self.client
        grow(2)
        count_queries(client, url)
        small = count_queries(client, url)
        grow(6)
        large = count_queries(client, url)
        self.assertLessEqual(large, small + slack, f"{url}: {small} queries grew to {large}")

    def test_product_list_does_not_grow_with_rows(self):
        self.assertConstant("/api/catalog/products/", lambda n: [self.product() for _ in range(n)])

    def test_my_products_does_not_grow_with_rows(self):
        self.assertConstant(
            "/api/catalog/products/mine/", lambda n: [self.product() for _ in range(n)], self.seller_client
        )

    def test_product_detail_does_not_grow_with_reviews(self):
        product, _ = self.product()

        def grow(n):
            for i in range(n):
                user = User.objects.create_user(f"rev{product.pk}-{i}-{Review.objects.count()}", "r@example.com", PASSWORD)
                Review.objects.create(product=product, user=user, rating=4, comment="Good")

        self.assertConstant(f"/api/catalog/products/{product.pk}/", grow)

    def test_cart_does_not_grow_with_lines(self):
        cart = Cart.objects.create(user=self.buyer)

        def grow(n):
            for _ in range(n):
                _, variant = self.product()
                CartItem.objects.create(cart=cart, variant=variant, quantity=1)

        self.assertConstant("/api/cart/", grow)

    def test_wishlist_does_not_grow(self):
        def grow(n):
            for _ in range(n):
                product, _ = self.product()
                WishlistItem.objects.create(user=self.buyer, product=product)

        self.assertConstant("/api/catalog/wishlist/", grow)

    def test_order_history_does_not_grow(self):
        address = Address.objects.create(
            user=self.buyer, full_name="B", line1="1", city="c", postal_code="1", country="Portugal"
        )

        def grow(n):
            for _ in range(n):
                _, variant = self.product()
                order = Order.objects.create(user=self.buyer, shipping_address=address, total_amount="10.00")
                OrderItem.objects.create(
                    order=order, variant=variant, product_name="x", sku=variant.sku, unit_price="10.00", quantity=1
                )

        self.assertConstant("/api/orders/", grow)

    def test_seller_received_orders_do_not_grow(self):
        address = Address.objects.create(
            user=self.buyer, full_name="B", line1="1", city="c", postal_code="1", country="Portugal"
        )

        def grow(n):
            for _ in range(n):
                _, variant = self.product()
                order = Order.objects.create(user=self.buyer, shipping_address=address, total_amount="10.00")
                OrderItem.objects.create(
                    order=order, variant=variant, product_name="x", sku=variant.sku, unit_price="10.00", quantity=1
                )

        self.assertConstant("/api/orders/received/", grow, self.seller_client)
