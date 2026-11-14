from django.db import migrations, models
import django.db.models


def merge_duplicate_guest_carts(apps, schema_editor):
    Cart = apps.get_model("cart", "Cart")
    CartItem = apps.get_model("cart", "CartItem")
    db = schema_editor.connection.alias
    session_keys = (
        Cart.objects.using(db).exclude(session_key__isnull=True).exclude(session_key="")
        .values_list("session_key", flat=True).distinct()
    )
    for session_key in session_keys:
        carts = list(Cart.objects.using(db).filter(session_key=session_key).order_by("id"))
        if len(carts) < 2:
            continue
        primary = carts[0]
        for duplicate in carts[1:]:
            for item in CartItem.objects.using(db).filter(cart_id=duplicate.pk):
                existing = CartItem.objects.using(db).filter(
                    cart_id=primary.pk, variant_id=item.variant_id
                ).first()
                if existing:
                    existing.quantity += item.quantity
                    existing.save(update_fields=["quantity"])
                    item.delete()
                else:
                    item.cart_id = primary.pk
                    item.save(update_fields=["cart"])
            duplicate.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cart", "0001_initial"),
        ("catalog", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(merge_duplicate_guest_carts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(session_key__isnull=False) & ~django.db.models.Q(session_key=""),
                fields=("session_key",), name="unique_guest_cart_session",
            ),
        ),
    ]
