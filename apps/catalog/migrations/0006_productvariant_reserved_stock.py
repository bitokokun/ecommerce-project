from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_productimage_unique_primary_image_per_product")]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="reserved_stock",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
