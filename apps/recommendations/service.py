import time
from collections import defaultdict

from apps.cart.models import CartItem
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem

from .engine import Recommender

CACHE_SECONDS = 300
_cache = {"model": None, "built_at": 0.0}


def _real_orders():
    return OrderItem.objects.exclude(order__status=Order.Status.CANCELLED).filter(
        variant__isnull=False
    )


def _build_model():
    products = [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category.name if p.category else "",
            "description": p.description,
        }
        for p in Product.objects.filter(status=Product.Status.ACTIVE).select_related("category")
    ]
    by_order = defaultdict(list)
    for order_id, product_id in _real_orders().values_list("order_id", "variant__product_id"):
        by_order[order_id].append(product_id)
    return Recommender(products, list(by_order.values()))


def get_model():
    now = time.monotonic()
    if _cache["model"] is None or now - _cache["built_at"] > CACHE_SECONDS:
        _cache["model"] = _build_model()
        _cache["built_at"] = now
    return _cache["model"]


def similar_products(product_id, limit=4):
    return get_model().similar(product_id, limit)


def products_for_user(user, limit=4):
    bought = list(
        _real_orders().filter(order__user=user).values_list("variant__product_id", flat=True).distinct()
    )
    in_cart = list(
        CartItem.objects.filter(cart__user=user).values_list("variant__product_id", flat=True).distinct()
    )
    return get_model().for_user(bought, in_cart, limit)
