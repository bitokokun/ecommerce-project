from collections import defaultdict

from django.db import migrations

KNOWN_ORDER_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled"}
OPEN_ORDER_STATUSES = ("pending", "paid")


def reconcile(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    OrderItem = apps.get_model("orders", "OrderItem")
    Fulfillment = apps.get_model("orders", "OrderFulfillment")
    Variant = apps.get_model("catalog", "ProductVariant")
    problems = []

    odd_orders = (
        Order.objects.exclude(status__in=KNOWN_ORDER_STATUSES).values_list("pk", "status")
    )
    for pk, status in odd_orders:
        problems.append(f"Order {pk} has status '{status}', which the final model does not have.")
    for f in Fulfillment.objects.filter(status="processing"):
        problems.append(
            f"Fulfillment {f.pk} (order {f.order_id}, seller {f.seller_id}) is 'processing'; "
            "per-item fulfilment has no such state."
        )

    linked = OrderItem.objects.filter(fulfillment__isnull=False).select_related(
        "fulfillment", "variant__product"
    )
    for item in linked:
        if item.variant_id is None:
            problems.append(
                f"OrderItem {item.pk} belongs to seller {item.fulfillment.seller_id} via a "
                "fulfillment but has no variant, so the seller would be lost."
            )
        elif item.variant.product.seller_id != item.fulfillment.seller_id:
            problems.append(
                f"OrderItem {item.pk}: fulfillment seller {item.fulfillment.seller_id} != "
                f"product seller {item.variant.product.seller_id}."
            )

    expected = defaultdict(int)
    open_lines = OrderItem.objects.filter(
        order__status__in=OPEN_ORDER_STATUSES, variant__isnull=False, fulfilment_status="pending"
    ).values_list("variant_id", "quantity")
    for variant_id, qty in open_lines:
        expected[variant_id] += qty
    variants = list(Variant.objects.select_for_update().order_by("pk"))
    for v in variants:
        if v.reserved_stock != expected.get(v.pk, 0):
            problems.append(
                f"Variant {v.pk} ({v.sku}): reserved_stock={v.reserved_stock} but open orders "
                f"contain {expected.get(v.pk, 0)} unit(s)."
            )
        elif v.reserved_stock > v.stock:
            problems.append(f"Variant {v.pk} ({v.sku}): reserved_stock exceeds stock.")

    if problems:
        raise RuntimeError(
            "Repair aborted, nothing was changed. Resolve these by hand, then re-run:\n  - "
            + "\n  - ".join(problems)
        )

    copied = 0
    for f in Fulfillment.objects.filter(status__in=("shipped", "delivered")):
        lines = OrderItem.objects.filter(fulfillment_id=f.pk, fulfilment_status="pending")
        for item in lines:
            item.fulfilment_status = f.status
            item.shipped_at = item.shipped_at or f.updated_at
            if f.status == "delivered":
                item.delivered_at = item.delivered_at or f.updated_at
            item.save(update_fields=["fulfilment_status", "shipped_at", "delivered_at"])
            copied += 1

    released = 0
    for v in variants:
        if v.reserved_stock:
            v.stock = v.stock - v.reserved_stock
            released += v.reserved_stock
            v.reserved_stock = 0
            v.save(update_fields=["stock", "reserved_stock"])

    print(
        f"\n  [repair] seller links verified for {linked.count()} order item(s); "
        f"{copied} item(s) took shipped/delivered state from fulfilments; "
        f"{released} reserved unit(s) deducted from stock."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_merge_20261113_0100"),
        ("catalog", "0008_merge_20261113_0100"),
    ]
    operations = [migrations.RunPython(reconcile, migrations.RunPython.noop)]
