import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address
from apps.cart.models import Cart, CartItem
from apps.catalog.models import Product, ProductVariant

from .models import IdempotencyKey, Order, OrderItem

User = get_user_model()
PASSWORD = "StrongPassword!2026"
KEY = "key-0123456789"


class World:
    def __init__(self):
        self.seller = User.objects.create_user("seller", "seller@example.com", PASSWORD, role="seller")
        self.product = Product.objects.create(seller=self.seller, name="Mouse", base_price="10.00")
        self.counter = 0

    def variant(self, stock, sku=None, price=None):
        self.counter += 1
        return ProductVariant.objects.create(
            product=self.product, sku=sku or f"SKU-{self.counter}", stock=stock, price_override=price
        )

    def buyer(self, name, lines):
        user = User.objects.create_user(name, f"{name}@example.com", PASSWORD)
        address = Address.objects.create(
            user=user, full_name=name, line1="1 Road", city="Lisbon", postal_code="1000", country="Portugal"
        )
        cart = Cart.objects.create(user=user)
        for variant, quantity in lines:
            CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)
        return user, address

    @staticmethod
    def client(user):
        client = APIClient()
        client.force_authenticate(user)
        return client


def checkout(client, address, key=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post("/api/orders/checkout/", {"shipping_address_id": address.pk}, format="json", **headers)


class CheckoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.world = World()

    def test_creates_order_deducts_stock_and_snapshots_prices(self):
        v1 = self.world.variant(5)
        v2 = self.world.variant(4, price="12.50")
        user, address = self.world.buyer("ana", [(v1, 2), (v2, 1)])
        response = checkout(self.world.client(user), address)
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual(order.total_amount, Decimal("32.50"))
        self.assertEqual(order.items.count(), 2)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual((v1.stock, v2.stock), (3, 3))
        self.assertFalse(CartItem.objects.filter(cart__user=user).exists())
        v1.product.base_price = Decimal("99.00")
        v1.product.save()
        self.assertEqual(OrderItem.objects.get(variant=v1).unit_price, Decimal("10.00"))

    def test_empty_cart_is_rejected(self):
        user, address = self.world.buyer("ana", [])
        self.assertEqual(checkout(self.world.client(user), address).status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_insufficient_stock_changes_nothing(self):
        v1 = self.world.variant(5)
        v2 = self.world.variant(1)
        user, address = self.world.buyer("ana", [(v1, 2), (v2, 3)])
        response = checkout(self.world.client(user), address)
        self.assertEqual(response.status_code, 400)
        v1.refresh_from_db()
        self.assertEqual(v1.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(CartItem.objects.filter(cart__user=user).count(), 2)

    def test_inactive_product_is_rejected(self):
        v = self.world.variant(5)
        user, address = self.world.buyer("ana", [(v, 1)])
        self.world.product.status = Product.Status.ARCHIVED
        self.world.product.save()
        self.assertEqual(checkout(self.world.client(user), address).status_code, 400)
        v.refresh_from_db()
        self.assertEqual(v.stock, 5)

    def test_cannot_ship_to_someone_elses_address(self):
        v = self.world.variant(5)
        user, _ = self.world.buyer("ana", [(v, 1)])
        _, foreign = self.world.buyer("bob", [])
        self.assertEqual(checkout(self.world.client(user), foreign).status_code, 404)
        self.assertEqual(Order.objects.count(), 0)

    def test_anonymous_cannot_checkout(self):
        response = APIClient().post("/api/orders/checkout/", {"shipping_address_id": 1}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_malformed_payload_is_a_validation_error(self):
        user, _ = self.world.buyer("ana", [])
        client = self.world.client(user)
        self.assertEqual(client.post("/api/orders/checkout/", {}, format="json").status_code, 400)
        self.assertEqual(
            client.post("/api/orders/checkout/", {"shipping_address_id": "abc"}, format="json").status_code, 400
        )


class IdempotencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.world = World()
        self.variant = self.world.variant(5)
        self.user, self.address = self.world.buyer("ana", [(self.variant, 2)])
        self.client = self.world.client(self.user)

    def test_replay_returns_the_original_order(self):
        first = checkout(self.client, self.address, KEY)
        second = checkout(self.client, self.address, KEY)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_replay_does_not_touch_a_refilled_cart(self):
        checkout(self.client, self.address, KEY)
        CartItem.objects.create(cart=Cart.objects.get(user=self.user), variant=self.variant, quantity=1)
        second = checkout(self.client, self.address, KEY)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3)

    def test_same_key_with_a_different_address_conflicts(self):
        checkout(self.client, self.address, KEY)
        other = Address.objects.create(
            user=self.user, full_name="Ana", line1="2 Road", city="Porto", postal_code="4000", country="Portugal"
        )
        response = checkout(self.client, other, KEY)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Order.objects.count(), 1)

    def test_keys_are_scoped_per_user(self):
        other_variant = self.world.variant(5)
        bob, bob_address = self.world.buyer("bob", [(other_variant, 1)])
        self.assertEqual(checkout(self.client, self.address, KEY).status_code, 201)
        self.assertEqual(checkout(self.world.client(bob), bob_address, KEY).status_code, 201)
        self.assertEqual(Order.objects.count(), 2)

    def test_malformed_keys_are_rejected(self):
        for bad in ("short", "has spaces in it", "x" * 65, "bad/key/chars!!"):
            response = checkout(self.client, self.address, bad)
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(Order.objects.count(), 0)

    def test_failed_attempt_does_not_burn_the_key(self):
        self.variant.stock = 1
        self.variant.save()
        self.assertEqual(checkout(self.client, self.address, KEY).status_code, 400)
        self.assertEqual(IdempotencyKey.objects.count(), 0)
        self.variant.stock = 5
        self.variant.save()
        self.assertEqual(checkout(self.client, self.address, KEY).status_code, 201)

    def test_works_without_a_key(self):
        self.assertEqual(checkout(self.client, self.address).status_code, 201)
        self.assertEqual(IdempotencyKey.objects.count(), 0)

    def test_prune_command_removes_only_old_keys(self):
        checkout(self.client, self.address, KEY)
        old = IdempotencyKey.objects.create(user=self.user, key="old-key-12345", fingerprint="x")
        IdempotencyKey.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(hours=72))
        call_command("prune_idempotency_keys", "--hours", "48")
        self.assertEqual(list(IdempotencyKey.objects.values_list("key", flat=True)), [KEY])


class ConcurrentCheckoutTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.world = World()

    def run_parallel(self, calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)
        failures = []

        def worker(index, call):
            try:
                barrier.wait(timeout=15)
                results[index] = call()
            except Exception as exc:
                failures.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        self.assertEqual(failures, [])
        return results

    def test_last_unit_is_sold_exactly_once(self):
        variant = self.world.variant(1)
        buyers = [self.world.buyer(f"user{i}", [(variant, 1)]) for i in range(2)]
        results = self.run_parallel(
            [lambda u=u, a=a: checkout(self.world.client(u), a) for u, a in buyers]
        )
        self.assertEqual(sorted(r.status_code for r in results), [201, 400])
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)
        self.assertEqual(Order.objects.count(), 1)

    def test_many_buyers_never_oversell(self):
        variant = self.world.variant(3)
        buyers = [self.world.buyer(f"user{i}", [(variant, 1)]) for i in range(6)]
        results = self.run_parallel(
            [lambda u=u, a=a: checkout(self.world.client(u), a) for u, a in buyers]
        )
        codes = sorted(r.status_code for r in results)
        self.assertEqual(codes, [201, 201, 201, 400, 400, 400])
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 0)
        self.assertEqual(OrderItem.objects.filter(variant=variant).count(), 3)

    def test_same_key_in_parallel_creates_one_order(self):
        variant = self.world.variant(5)
        user, address = self.world.buyer("ana", [(variant, 1)])
        results = self.run_parallel(
            [lambda: checkout(self.world.client(user), address, KEY) for _ in range(4)]
        )
        codes = sorted(r.status_code for r in results)
        self.assertEqual(codes, [200, 200, 200, 201])
        self.assertEqual(len({r.json()["id"] for r in results}), 1)
        self.assertEqual(Order.objects.count(), 1)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 4)

    def test_double_submit_without_a_key_creates_one_order(self):
        variant = self.world.variant(5)
        user, address = self.world.buyer("ana", [(variant, 2)])
        results = self.run_parallel(
            [lambda: checkout(self.world.client(user), address) for _ in range(3)]
        )
        codes = sorted(r.status_code for r in results)
        self.assertEqual(codes, [201, 400, 400])
        self.assertEqual(Order.objects.count(), 1)
        variant.refresh_from_db()
        self.assertEqual(variant.stock, 3)

    def test_opposite_cart_orders_do_not_deadlock(self):
        v1 = self.world.variant(5)
        v2 = self.world.variant(5)
        a = self.world.buyer("ana", [(v1, 1), (v2, 1)])
        b = self.world.buyer("bob", [(v2, 1), (v1, 1)])
        results = self.run_parallel(
            [lambda u=u, ad=ad: checkout(self.world.client(u), ad) for u, ad in (a, b)]
        )
        self.assertEqual([r.status_code for r in results], [201, 201])
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual((v1.stock, v2.stock), (3, 3))

    def test_cancel_and_checkout_race_keeps_stock_consistent(self):
        variant = self.world.variant(2)
        ana, ana_address = self.world.buyer("ana", [(variant, 2)])
        first = checkout(self.world.client(ana), ana_address)
        self.assertEqual(first.status_code, 201)
        order_id = first.json()["id"]
        bob, bob_address = self.world.buyer("bob", [(variant, 2)])
        results = self.run_parallel(
            [
                lambda: self.world.client(ana).post(f"/api/orders/{order_id}/cancel/"),
                lambda: checkout(self.world.client(bob), bob_address),
            ]
        )
        variant.refresh_from_db()
        sold = sum(
            i.quantity for i in OrderItem.objects.filter(variant=variant, order__status__in=["pending", "paid"])
        )
        self.assertEqual(variant.stock + sold, 2)
        self.assertGreaterEqual(variant.stock, 0)
