import hashlib
import re

from django.db import IntegrityError, transaction

from apps.cart.views import get_or_create_cart
from apps.catalog.models import Product, ProductVariant

from .models import IdempotencyKey, Order, OrderItem

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class CheckoutError(Exception):
    def __init__(self, detail, status=400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def fingerprint_for(address_id):
    return hashlib.sha256(f"address:{address_id}".encode()).hexdigest()


def claim_key(user, key, fingerprint):
    try:
        with transaction.atomic():
            return IdempotencyKey.objects.create(user=user, key=key, fingerprint=fingerprint), None
    except IntegrityError:
        existing = IdempotencyKey.objects.select_related("order").get(user=user, key=key)
        if existing.fingerprint != fingerprint:
            raise CheckoutError("This Idempotency-Key was already used with a different request.", 422)
        if existing.order_id is None:
            raise CheckoutError("A request with this Idempotency-Key is still being processed.", 409)
        return existing, existing.order


def place_order(request, address, key=None):
    user = request.user
    with transaction.atomic():
        record = None
        if key:
            record, replay = claim_key(user, key, fingerprint_for(address.pk))
            if replay is not None:
                return replay, True

        cart = get_or_create_cart(request)
        cart = type(cart).objects.select_for_update().get(pk=cart.pk)
        items = list(cart.items.select_for_update().select_related("variant", "variant__product"))
        if not items:
            raise CheckoutError("Cart is empty.")

        variant_ids = sorted({i.variant_id for i in items})
        variants = {
            v.id: v
            for v in ProductVariant.objects.select_for_update()
            .select_related("product")
            .filter(id__in=variant_ids)
            .order_by("id")
        }
        if len(variants) != len(variant_ids):
            raise CheckoutError("A product option in your cart is no longer available.")

        for item in items:
            variant = variants[item.variant_id]
            if variant.product.status != Product.Status.ACTIVE:
                raise CheckoutError(f"{variant.product.name} is no longer available. Remove it from your cart.")
            if item.quantity > variant.stock:
                raise CheckoutError(f"Only {variant.stock} unit(s) of {variant.sku} left.")

        order = Order.objects.create(user=user, shipping_address=address, total_amount=0)
        lines = []
        total = 0
        for item in items:
            variant = variants[item.variant_id]
            lines.append(
                OrderItem(
                    order=order,
                    variant=variant,
                    product_name=variant.product.name,
                    sku=variant.sku,
                    unit_price=variant.price,
                    quantity=item.quantity,
                )
            )
            total += variant.price * item.quantity
            variant.stock -= item.quantity
        OrderItem.objects.bulk_create(lines)
        ProductVariant.objects.bulk_update(variants.values(), ["stock"])
        order.total_amount = total
        order.save(update_fields=["total_amount"])
        cart.items.all().delete()

        if record is not None:
            record.order = order
            record.save(update_fields=["order"])
    return order, False
