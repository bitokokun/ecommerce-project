from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import SellerProfile
from .models import Category, Product

User = get_user_model()


class ListingFieldsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(name="Home goods")

    def rows(self):
        data = self.client.get("/api/catalog/products/").json()
        return data.get("results", data)

    def test_list_shows_store_name_category_and_ids(self):
        seller = User.objects.create_user("kiln", "k@example.com", "StrongPassword!2026", role="seller")
        SellerProfile.objects.create(user=seller, store_name="Kiln Studio")
        Product.objects.create(seller=seller, name="Mug", base_price="14.00", category=self.category)
        row = self.rows()[0]
        self.assertEqual(row["seller_name"], "Kiln Studio")
        self.assertEqual(row["category_name"], "Home goods")
        self.assertEqual(row["category"], self.category.pk)
        self.assertIsNone(row["store_logo"])

    def test_seller_without_store_falls_back_to_username(self):
        seller = User.objects.create_user("plain", "p@example.com", "StrongPassword!2026", role="seller")
        Product.objects.create(seller=seller, name="Cup", base_price="9.00")
        row = self.rows()[0]
        self.assertEqual(row["seller_name"], "plain")
        self.assertEqual(row["category_name"], "")
