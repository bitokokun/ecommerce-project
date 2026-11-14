from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_merge_20261113_0100"),
        ("orders", "0005_reconcile_fulfilment_and_stock"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="productvariant", name="variant_reserved_not_above_stock"),
        migrations.RemoveField(model_name="productvariant", name="reserved_stock"),
    ]
