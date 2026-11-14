from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_seed_categories")]
    operations = [
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=models.Q(base_price__gte=0), name="product_base_price_nonnegative"
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=models.Q(price_override__isnull=True) | models.Q(price_override__gte=0),
                name="variant_price_override_nonnegative",
            ),
        ),
    ]
