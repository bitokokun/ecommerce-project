from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('catalog', '0004_review_review_rating_between_1_and_5'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='productimage',
            constraint=models.UniqueConstraint(condition=models.Q(('is_primary', True)), fields=('product',), name='unique_primary_image_per_product'),
        ),
    ]
