"""
Fills the shop with a demo catalog so it never looks empty (and so the
recommendations have something to work with):

    python manage.py seed_demo

Safe to run again and again: a product whose name already exists is skipped.
On Render's free tier there is no shell, so start.sh runs this on every boot
when the SEED_DEMO environment variable is set, which also refills the shop
automatically after a database replacement.

Demo products are owned by your first superuser, so you can edit them or add
photos from the admin like any other product.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.catalog.models import Category, Product, ProductVariant

# (name, category, price, stock, description)
DEMO = [
    ("Wireless Mouse", "Computers & Laptops", "19.99", 50,
     "Compact wireless mouse with a USB receiver for laptop and desktop."),
    ("Gaming Mouse", "Computers & Laptops", "34.90", 30,
     "RGB gaming mouse with adjustable DPI and programmable buttons."),
    ("Mechanical Keyboard", "Computers & Laptops", "59.00", 25,
     "Mechanical keyboard with RGB backlight and a detachable USB cable."),
    ("USB-C Hub", "Computers & Laptops", "29.50", 40,
     "Seven-port USB-C hub with HDMI and card reader for laptop and desktop."),
    ("Laptop Stand", "Computers & Laptops", "24.00", 35,
     "Foldable aluminium laptop stand that lifts your screen to eye level."),
    ("Wireless Headphones", "Audio & Headphones", "79.00", 20,
     "Over-ear wireless bluetooth headphones with noise cancelling and long battery life."),
    ("Bluetooth Speaker", "Audio & Headphones", "45.00", 28,
     "Portable bluetooth speaker with deep bass and waterproof body."),
    ("Wireless Earbuds", "Audio & Headphones", "39.00", 45,
     "Bluetooth earbuds with a charging case and clear sound for calls and music."),
    ("Ceramic Mug", "Home & Kitchen", "12.00", 60,
     "Large ceramic mug for coffee and tea, dishwasher safe."),
    ("Stainless Steel Water Bottle", "Home & Kitchen", "18.50", 55,
     "Insulated stainless steel bottle that keeps drinks cold or hot for hours."),
    ("Non-stick Frying Pan", "Home & Kitchen", "27.00", 22,
     "Durable non-stick frying pan for everyday kitchen cooking."),
    ("Roasted Coffee Beans", "Groceries & Food", "14.00", 70,
     "Whole roasted coffee beans with a smooth medium roast for your kitchen."),
    ("Cotton T-Shirt", "Men's Fashion", "15.00", 80,
     "Soft cotton t-shirt in many colors, comfortable for everyday wear."),
    ("Running Shoes", "Shoes", "64.00", 33,
     "Lightweight running shoes with breathable mesh and a cushioned sole."),
    ("Canvas Backpack", "Bags & Luggage", "32.00", 26,
     "Canvas backpack with a padded laptop pocket and sturdy straps."),
    ("Hardcover Notebook", "Stationery & Office", "8.50", 90,
     "Hardcover notebook with thick paper for notes and sketches at your desk."),
    ("Yoga Mat", "Sports & Outdoors", "21.00", 38,
     "Non-slip yoga mat with extra cushioning for workouts at home."),
]


class Command(BaseCommand):
    help = "Create a demo catalog (skips products that already exist)."

    def handle(self, *args, **options):
        owner = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
        if owner is None:
            self.stdout.write("No superuser yet, skipping demo catalog.")
            return

        created = 0
        for name, category_name, price, stock, description in DEMO:
            if Product.objects.filter(name__iexact=name).exists():
                continue
            category = Category.objects.filter(name__iexact=category_name).first()
            if category is None:
                category = Category.objects.create(name=category_name)
            product = Product.objects.create(
                seller=owner, category=category, name=name,
                description=description, base_price=price,
                status=Product.Status.ACTIVE,
            )
            ProductVariant.objects.create(
                product=product, sku=f"{slugify(name).upper()}-01", stock=stock,
            )
            created += 1

        self.stdout.write(f"Demo catalog ready ({created} new products).")
