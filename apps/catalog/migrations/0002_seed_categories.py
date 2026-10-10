from django.db import migrations
from django.utils.text import slugify

CATEGORIES = [
    "Electronics", "Computers & Laptops", "Phones & Tablets", "Audio & Headphones",
    "Cameras & Photography", "Gaming", "Home & Kitchen", "Furniture", "Home Decor",
    "Appliances", "Men's Fashion", "Women's Fashion", "Kids' Fashion", "Shoes",
    "Bags & Luggage", "Jewelry & Watches", "Beauty & Personal Care",
    "Health & Wellness", "Sports & Outdoors", "Toys & Games", "Baby Products",
    "Books", "Stationery & Office", "Music & Instruments", "Art & Crafts",
    "Tools & Home Improvement", "Garden & Outdoor", "Automotive", "Pet Supplies",
    "Groceries & Food",
]


def seed(apps, schema_editor):
    # Historical models don't run Category.save(), so the slug is set by hand.
    Category = apps.get_model("catalog", "Category")
    for name in CATEGORIES:
        slug = slugify(name)
        if Category.objects.filter(slug=slug).exists() or Category.objects.filter(name__iexact=name).exists():
            continue  # e.g. your existing "Electronics" is left alone
        Category.objects.create(name=name, slug=slug)


def unseed(apps, schema_editor):
    pass  # keep the categories on rollback; products may already use them


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
