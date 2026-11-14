from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_legacy_fulfillments(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Fulfillment = apps.get_model("orders", "OrderFulfillment")
    ProductVariant = apps.get_model("catalog", "ProductVariant")

    for order in Order.objects.all().iterator():
        seller_ids = set(
            OrderItem.objects.filter(order_id=order.pk, variant__isnull=False)
            .values_list("variant__product__seller_id", flat=True)
        )
        legacy_status = order.status
        if legacy_status == "paid":
            Order.objects.filter(pk=order.pk).update(status="processing")
        fulfillment_status = {
            "pending": "pending",
            "paid": "processing",
            "shipped": "shipped",
            "delivered": "delivered",
            "cancelled": "cancelled",
        }.get(legacy_status, "pending")

        for seller_id in seller_ids:
            fulfillment, _ = Fulfillment.objects.get_or_create(
                order_id=order.pk, seller_id=seller_id,
                defaults={"status": fulfillment_status},
            )
            lines = OrderItem.objects.filter(
                order_id=order.pk, variant__product__seller_id=seller_id
            )
            lines.update(fulfillment_id=fulfillment.pk)

        if legacy_status in ("pending", "paid"):
            pending_lines = OrderItem.objects.filter(
                order_id=order.pk, variant__isnull=False
            ).values("variant_id", "quantity")
            for line in pending_lines:
                ProductVariant.objects.filter(pk=line["variant_id"]).update(
                    stock=models.F("stock") + line["quantity"],
                    reserved_stock=models.F("reserved_stock") + line["quantity"],
                )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0007_variant_reserved_stock_lte_stock"),
        ("orders", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderFulfillment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "New"), ("processing", "Processing"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="pending", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fulfillments", to="orders.order")),
                ("seller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fulfillments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="orderfulfillment",
            constraint=models.UniqueConstraint(fields=("order", "seller"), name="unique_order_seller_fulfillment"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="fulfillment",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="items", to="orders.orderfulfillment"),
        ),
        migrations.RunPython(create_legacy_fulfillments, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(choices=[("pending", "Placed"), ("processing", "Processing"), ("shipped", "Shipped"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="pending", max_length=20),
        ),
    ]
