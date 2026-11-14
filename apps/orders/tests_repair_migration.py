from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [
    ("accounts", "0003_profile_avatar_preferences_sellerprofile"),
    ("orders", "0004_merge_20261113_0100"),
    ("catalog", "0008_merge_20261113_0100"),
]
AFTER = [
    ("orders", "0006_finish_per_item_fulfilment"),
    ("catalog", "0009_drop_reserved_stock"),
]


class RepairMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def setUp(self):
        self.apps_before = self.migrate(BEFORE)

    def tearDown(self):
        if "orders_orderfulfillment" in connection.introspection.table_names():
            a = self.apps_before
            for app, name in [
                ("orders", "OrderItem"), ("orders", "OrderFulfillment"), ("orders", "Order"),
                ("catalog", "ProductVariant"), ("catalog", "Product"),
                ("accounts", "Address"), ("accounts", "User"),
            ]:
                a.get_model(app, name).objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def build(self, *, reserved=3, qty=3, seller_mismatch=False, fulfilment_status="pending"):
        a = self.apps_before
        User, Address = a.get_model("accounts", "User"), a.get_model("accounts", "Address")
        Product, Variant = a.get_model("catalog", "Product"), a.get_model("catalog", "ProductVariant")
        Order, Item = a.get_model("orders", "Order"), a.get_model("orders", "OrderItem")
        Fulfillment = a.get_model("orders", "OrderFulfillment")

        seller = User.objects.create(username="seller")
        other = User.objects.create(username="other-seller")
        buyer = User.objects.create(username="buyer")
        product = Product.objects.create(seller=seller, name="Mouse", slug="mouse", base_price="10.00")
        variant = Variant.objects.create(product=product, sku="MOUSE-1", stock=50, reserved_stock=reserved)
        addr = Address.objects.create(user=buyer, full_name="B", line1="1", city="c", postal_code="1", country="X")
        order = Order.objects.create(user=buyer, shipping_address=addr, total_amount="30.00", status="pending")
        f = Fulfillment.objects.create(
            order=order, seller=other if seller_mismatch else seller, status=fulfilment_status
        )
        item = Item.objects.create(
            order=order, variant=variant, product_name="Mouse", sku="MOUSE-1",
            unit_price="10.00", quantity=qty, fulfillment=f,
        )
        return variant, item, seller

    def test_repair_moves_data_and_cleans_schema(self):
        variant, item, seller = self.build()
        apps = self.migrate(AFTER)
        Variant, Item = apps.get_model("catalog", "ProductVariant"), apps.get_model("orders", "OrderItem")
        self.assertEqual(Variant.objects.get(pk=variant.pk).stock, 47)
        self.assertFalse(any(f.name == "reserved_stock" for f in Variant._meta.get_fields()))
        item = Item.objects.get(pk=item.pk)
        self.assertEqual(item.fulfilment_status, "pending")
        self.assertEqual(item.variant.product.seller_id, seller.pk)
        with self.assertRaises(LookupError):
            apps.get_model("orders", "OrderFulfillment")

    def test_shipped_state_is_copied_to_items(self):
        _, item, _ = self.build(fulfilment_status="shipped")
        apps = self.migrate(AFTER)
        self.assertEqual(apps.get_model("orders", "OrderItem").objects.get(pk=item.pk).fulfilment_status, "shipped")

    def test_aborts_when_reserved_stock_does_not_match_open_orders(self):
        self.build(reserved=2, qty=3)
        with self.assertRaisesMessage(RuntimeError, "reserved_stock=2"):
            self.migrate(AFTER)

    def test_aborts_when_seller_would_be_lost(self):
        self.build(seller_mismatch=True)
        with self.assertRaisesMessage(RuntimeError, "fulfillment seller"):
            self.migrate(AFTER)

    def test_aborts_on_processing_fulfilment(self):
        self.build(fulfilment_status="processing")
        with self.assertRaisesMessage(RuntimeError, "processing"):
            self.migrate(AFTER)
