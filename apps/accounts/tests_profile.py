import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Address, SellerProfile
from apps.catalog.models import Product, ProductVariant, WishlistItem
from apps.orders.models import Order, OrderItem

User = get_user_model()
PW = "StrongPassword!2026"


def png_bytes(size=(20, 20), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, (156, 175, 136)).save(buf, fmt)
    return buf.getvalue()


@override_settings(MEDIA_ROOT="/tmp/souk-test-media")
class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", "ana@example.com", PW)
        self.other = User.objects.create_user("bob", "bob@example.com", PW)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_edit_profile_persists(self):
        r = self.client.patch(
            "/api/accounts/me/",
            {"first_name": "Ana", "last_name": "Lima", "phone_number": "+1 555 123 4567",
             "email": "ana2@example.com", "username": "ana-l"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Ana", "Lima"))
        self.assertEqual(self.user.username, "ana-l")
        self.assertEqual(self.user.email, "ana2@example.com")

    def test_cannot_take_someone_elses_username_or_email(self):
        r = self.client.patch("/api/accounts/me/", {"username": "BOB"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch("/api/accounts/me/", {"email": "Bob@example.com"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cannot_escalate_role_or_staff(self):
        self.client.patch("/api/accounts/me/", {"role": "admin", "is_staff": True}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "customer")
        self.assertFalse(self.user.is_staff)

    def test_me_never_exposes_password(self):
        r = self.client.get("/api/accounts/me/")
        self.assertNotIn("password", r.json())

    def test_bad_phone_rejected(self):
        r = self.client.patch("/api/accounts/me/", {"phone_number": "call me maybe"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_avatar_upload_replace_remove(self):
        f = SimpleUploadedFile("a.png", png_bytes(), content_type="image/png")
        r = self.client.post("/api/accounts/me/avatar/", {"image": f}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["avatar_url"])
        f2 = SimpleUploadedFile("b.png", png_bytes((30, 30)), content_type="image/png")
        r = self.client.post("/api/accounts/me/avatar/", {"image": f2}, format="multipart")
        self.assertEqual(r.status_code, 200)
        r = self.client.delete("/api/accounts/me/avatar/")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["avatar_url"])

    def test_avatar_rejects_non_image_and_big_files(self):
        fake = SimpleUploadedFile("a.png", b"<script>alert(1)</script>", content_type="image/png")
        r = self.client.post("/api/accounts/me/avatar/", {"image": fake}, format="multipart")
        self.assertEqual(r.status_code, 400)
        big = SimpleUploadedFile("big.png", b"0" * (2 * 1024 * 1024 + 1), content_type="image/png")
        r = self.client.post("/api/accounts/me/avatar/", {"image": big}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_avatar_requires_login(self):
        r = APIClient().post("/api/accounts/me/avatar/", {}, format="multipart")
        self.assertEqual(r.status_code, 401)

    def test_change_password(self):
        r = self.client.post(
            "/api/accounts/password/",
            {"current_password": "wrong", "new_password": "AnotherStrong!2027"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            "/api/accounts/password/",
            {"current_password": PW, "new_password": "123"}, format="json",
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.post(
            "/api/accounts/password/",
            {"current_password": PW, "new_password": "AnotherStrong!2027"}, format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("AnotherStrong!2027"))

    def test_delete_account_without_history_removes_user(self):
        r = self.client.post("/api/accounts/delete/", {"password": "nope", "confirmation": "ana"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/accounts/delete/", {"password": PW, "confirmation": "wrong"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/accounts/delete/", {"password": PW, "confirmation": "ana"}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_delete_account_with_orders_anonymises(self):
        seller = User.objects.create_user("shop", "s@example.com", PW, role="seller")
        p = Product.objects.create(seller=seller, name="Mug", base_price="5.00")
        v = ProductVariant.objects.create(product=p, sku="MUG-1", stock=3)
        addr = Address.objects.create(user=self.user, full_name="Ana", line1="1 St", city="X", postal_code="1", country="Portugal")
        o = Order.objects.create(user=self.user, shipping_address=addr, total_amount="5.00")
        OrderItem.objects.create(order=o, variant=v, product_name="Mug", sku="MUG-1", unit_price="5.00", quantity=1)
        r = self.client.post("/api/accounts/delete/", {"password": PW, "confirmation": "ana"}, format="json")
        self.assertEqual(r.status_code, 204)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.email, "")
        self.assertTrue(Order.objects.filter(pk=o.pk).exists())

    def test_staff_cannot_self_delete(self):
        self.user.is_staff = True
        self.user.save()
        r = self.client.post("/api/accounts/delete/", {"password": PW, "confirmation": "ana"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_addresses_are_private_and_single_default(self):
        a = Address.objects.create(user=self.other, full_name="B", line1="1", city="c", postal_code="1", country="Portugal")
        self.assertEqual(self.client.get(f"/api/accounts/addresses/{a.pk}/").status_code, 404)
        for n in (1, 2):
            self.client.post("/api/accounts/addresses/", {
                "full_name": "Ana", "line1": f"{n} St", "city": "Lisbon", "postal_code": "1000",
                "country": "Portugal", "is_default": True}, format="json")
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)


@override_settings(MEDIA_ROOT="/tmp/souk-test-media")
class StoreTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user("shop1", "s1@example.com", PW, role="seller")
        self.customer = User.objects.create_user("cust", "c@example.com", PW)
        self.client = APIClient()

    def test_customer_has_no_store(self):
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.get("/api/accounts/store/").status_code, 403)

    def test_seller_store_create_edit_logo(self):
        self.client.force_authenticate(self.seller)
        r = self.client.get("/api/accounts/store/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["store_name"], "shop1")
        r = self.client.patch("/api/accounts/store/", {"store_name": "Linen & Sage", "description": "Hand made"}, format="json")
        self.assertEqual(r.status_code, 200)
        f = SimpleUploadedFile("l.png", png_bytes(), content_type="image/png")
        r = self.client.post("/api/accounts/store/logo/", {"image": f}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["logo_url"])
        self.assertEqual(SellerProfile.objects.get(user=self.seller).store_name, "Linen & Sage")

    def test_store_name_unique(self):
        other = User.objects.create_user("shop2", "s2@example.com", PW, role="seller")
        SellerProfile.objects.create(user=other, store_name="Taken")
        self.client.force_authenticate(self.seller)
        r = self.client.patch("/api/accounts/store/", {"store_name": "taken"}, format="json")
        self.assertEqual(r.status_code, 400)


class WishlistTests(TestCase):
    def setUp(self):
        seller = User.objects.create_user("sel", "x@example.com", PW, role="seller")
        self.active = Product.objects.create(seller=seller, name="A", base_price="1.00")
        self.draft = Product.objects.create(seller=seller, name="D", base_price="1.00", status="draft")
        self.u1 = User.objects.create_user("u1", "u1@example.com", PW)
        self.u2 = User.objects.create_user("u2", "u2@example.com", PW)
        self.client = APIClient()

    def test_requires_login(self):
        self.assertEqual(self.client.get("/api/catalog/wishlist/").status_code, 401)

    def test_add_list_remove_idempotent(self):
        self.client.force_authenticate(self.u1)
        r = self.client.post("/api/catalog/wishlist/", {"product": self.active.pk}, format="json")
        self.assertEqual(r.status_code, 201)
        r = self.client.post("/api/catalog/wishlist/", {"product": self.active.pk}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(WishlistItem.objects.filter(user=self.u1).count(), 1)
        self.assertEqual(len(self.client.get("/api/catalog/wishlist/").json()), 1)
        self.assertEqual(self.client.get("/api/catalog/wishlist/ids/").json(), [self.active.pk])
        self.assertEqual(self.client.delete(f"/api/catalog/wishlist/{self.active.pk}/").status_code, 204)
        self.assertEqual(WishlistItem.objects.count(), 0)

    def test_lists_are_private(self):
        WishlistItem.objects.create(user=self.u2, product=self.active)
        self.client.force_authenticate(self.u1)
        self.assertEqual(self.client.get("/api/catalog/wishlist/").json(), [])
        self.client.delete(f"/api/catalog/wishlist/{self.active.pk}/")
        self.assertEqual(WishlistItem.objects.filter(user=self.u2).count(), 1)

    def test_cannot_save_draft_or_garbage(self):
        self.client.force_authenticate(self.u1)
        self.assertEqual(self.client.post("/api/catalog/wishlist/", {"product": self.draft.pk}, format="json").status_code, 404)
        self.assertEqual(self.client.post("/api/catalog/wishlist/", {"product": "x"}, format="json").status_code, 400)
