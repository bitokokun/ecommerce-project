from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_productvariant_reserved_stock")]

    operations = [
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=models.Q(reserved_stock__lte=models.F("stock")),
                name="variant_reserved_not_above_stock",
            ),
        ),
    ]
