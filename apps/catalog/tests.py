from django.contrib.auth import get_user_model
from django.core.files import images
from django.db import IntegrityError, transaction
from django.http import response
from django.test import TestCase
from rest_framework.test import APIClient
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Category, Product, ProductImage, ProductVariant, Review
from .models import Category, Product, ProductVariant, Review


User = get_user_model()


class CatalogAPITests(TestCase):
    from django.db import IntegrityError, transaction

    def setUp(self):
        self.client = APIClient()

        self.customer = User.objects.create_user(
            username="customer",
            password="StrongPassword!2026",
            role="customer",
        )

        self.seller = User.objects.create_user(
            username="seller",
            password="StrongPassword!2026",
            role="seller",
        )

        self.other_seller = User.objects.create_user(
            username="otherseller",
            password="StrongPassword!2026",
            role="seller",
        )

        self.category, _ = Category.objects.get_or_create(
            slug="electronics",
            defaults={"name": "Electronics"},
        )

        self.active_product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Wireless Mouse",
            base_price="25.00",
            status=Product.Status.ACTIVE,
        )

        self.draft_product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Draft Keyboard",
            base_price="50.00",
            status=Product.Status.DRAFT,
        )

    def create_test_image(self, width=100, height=100):
        image = Image.new("RGB", (width, height), color="red")
        image_file = BytesIO()
        image.save(image_file, format="PNG")
        image_file.seek(0)

        return SimpleUploadedFile(
            "test.png",
            image_file.read(),
            content_type="image/png",
        )

    def test_anonymous_users_only_see_active_products(self):
        response = self.client.get("/api/catalog/products/")
        self.assertEqual(response.status_code, 200)

        product_names = [
            product["name"] for product in response.data["results"]
        ]

        self.assertIn("Wireless Mouse", product_names)
        self.assertNotIn("Draft Keyboard", product_names)

    def test_anonymous_users_cannot_access_draft_product(self):
        response = self.client.get(
            f"/api/catalog/products/{self.draft_product.pk}/"
        )
        self.assertEqual(response.status_code, 404)

    def test_seller_can_access_own_draft_product(self):
        self.client.force_authenticate(user=self.seller)

        response = self.client.get(
            f"/api/catalog/products/{self.draft_product.pk}/"
        )
        self.assertEqual(response.status_code, 200)

    def test_customer_cannot_create_product(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/api/catalog/products/",
            {
                "name": "Unauthorized Product",
                "category": self.category.pk,
                "description": "Test product",
                "base_price": "20.00",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Product.objects.filter(name="Unauthorized Product").exists()
        )

    def test_seller_can_create_product(self):
        self.client.force_authenticate(user=self.seller)

        response = self.client.post(
            "/api/catalog/products/",
            {
                "name": "New Seller Product",
                "category": self.category.pk,
                "description": "A new product",
                "base_price": "30.00",
                "status": "active",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        product = Product.objects.get(name="New Seller Product")
        self.assertEqual(product.seller, self.seller)

    def test_seller_cannot_manage_another_sellers_variant(self):
        variant = ProductVariant.objects.create(
            product=self.active_product,
            sku="MOUSE-001",
            stock=10,
        )

        self.client.force_authenticate(user=self.other_seller)

        response = self.client.get(
            f"/api/catalog/products/{self.active_product.pk}/variants/"
        )

        self.assertEqual(response.data["count"], 0)

        response = self.client.delete(
            f"/api/catalog/products/{self.active_product.pk}/variants/{variant.pk}/"
        )

        self.assertEqual(response.status_code, 404)

    def test_review_rating_above_five_is_rejected(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/reviews/",
            {"rating": 6, "comment": "Invalid rating"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_customer_can_create_review(self):
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/reviews/",
            {"rating": 5, "comment": "Great product!"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Review.objects.filter(
                product=self.active_product,
                user=self.customer,
            ).exists()
        )

    def test_customer_cannot_review_same_product_twice(self):
        Review.objects.create(
            product=self.active_product,
            user=self.customer,
            rating=5,
            comment="First review",
        )

        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/reviews/",
            {"rating": 4, "comment": "Second review"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            Review.objects.filter(
                product=self.active_product,
                user=self.customer,
            ).count(),
            1,
        )

    def test_customer_cannot_edit_another_users_review(self):
        review = Review.objects.create(
            product=self.active_product,
            user=self.customer,
            rating=5,
            comment="Original review",
        )

        self.client.force_authenticate(user=self.other_seller)

        response = self.client.put(
            f"/api/catalog/products/{self.active_product.pk}/reviews/{review.pk}/",
            {
                "rating": 1,
                "comment": "Changed by someone else",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        review.refresh_from_db()
        self.assertEqual(review.rating, 5)

    def test_creating_variant_for_nonexistent_product_returns_404(self):
        self.client.force_authenticate(user=self.seller)

        response = self.client.post(
            "/api/catalog/products/999999/variants/",
            {
                "sku": "MISSING-001",
                "stock": 5,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
    def test_seller_can_upload_product_image(self):
        self.client.force_authenticate(user=self.seller)

        image = self.create_test_image()

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            ProductImage.objects.filter(product=self.active_product).count(),
            1,
        )

        uploaded_image = ProductImage.objects.get(product=self.active_product)
        self.assertTrue(uploaded_image.is_primary)
    def test_seller_cannot_upload_image_to_another_sellers_product(self):
        self.client.force_authenticate(user=self.other_seller)

        image = self.create_test_image()

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            ProductImage.objects.filter(product=self.active_product).count(),
            0,
        )
    def test_upload_rejects_image_with_too_many_pixels(self):
        self.client.force_authenticate(user=self.seller)

        image = self.create_test_image(
            width=5001,
            height=5000,
        )

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ProductImage.objects.filter(product=self.active_product).count(),
            0,
        )
    def test_upload_rejects_invalid_image_file(self):
        self.client.force_authenticate(user=self.seller)

        invalid_file = SimpleUploadedFile(
            "fake.jpg",
            b"This is not an actual image.",
            content_type="image/jpeg",
        )

        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": invalid_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ProductImage.objects.filter(product=self.active_product).count(),
            0,
        )
    def test_first_uploaded_image_becomes_primary(self):
        self.client.force_authenticate(user=self.seller)

        first_response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": self.create_test_image()},
            format="multipart",
        )

        second_response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": self.create_test_image()},
            format="multipart",
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

        images = ProductImage.objects.filter(
            product=self.active_product
            ).order_by("id")

        self.assertTrue(images.first().is_primary)
        self.assertFalse(images.last().is_primary)
    def test_product_cannot_have_two_primary_images(self):
        first_image = ProductImage.objects.create(
            product=self.active_product,
            image=self.create_test_image(),
            is_primary=True,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductImage.objects.create(
                    product=self.active_product,
                    image=self.create_test_image(),
                    is_primary=True,
                )

        first_image.refresh_from_db()
        self.assertTrue(first_image.is_primary)
        self.assertEqual(
            ProductImage.objects.filter(
                product=self.active_product,
                is_primary=True,
            ).count(),
            1,
        )


    def test_upload_sets_primary_when_existing_images_are_not_primary(self):
        ProductImage.objects.create(
            product=self.active_product,
            image=self.create_test_image(),
            is_primary=False,
        )
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": self.create_test_image()},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            ProductImage.objects.filter(product=self.active_product, is_primary=True).count(),
            1,
        )

    def test_upload_rejects_file_larger_than_five_megabytes(self):
        self.client.force_authenticate(user=self.seller)
        large_file = SimpleUploadedFile(
            "large.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg"
        )
        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {"image": large_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProductImage.objects.filter(product=self.active_product).exists())

    def test_upload_requires_an_image_file(self):
        self.client.force_authenticate(user=self.seller)
        response = self.client.post(
            f"/api/catalog/products/{self.active_product.pk}/images/upload/",
            {},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_latin_category_name_gets_unique_fallback_slug(self):
        first = Category.objects.create(name="دسته بندی")
        second = Category.objects.create(name="محصولات")
        self.assertTrue(first.slug.startswith("category-"))
        self.assertTrue(second.slug.startswith("category-"))
        self.assertNotEqual(first.slug, second.slug)


    def test_non_latin_product_name_gets_fallback_slug(self):
        product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="ماوس بی سیم",
            base_price="10.00",
        )
        self.assertTrue(product.slug.startswith("product-"))
