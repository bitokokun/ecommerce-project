from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from django.db.models import Prefetch, Sum, Count, F, DecimalField, ExpressionWrapper
from django.utils.dateparse import parse_datetime
from datetime import timedelta
from django.utils import timezone
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from .models import Order, OrderItem
from .services import KEY_PATTERN, CheckoutError, place_order
from .serializers import (
    OrderSerializer, CheckoutSerializer, SaleOrderSerializer, FulfilSerializer, order_can_cancel,
)
from apps.accounts.models import Address
from apps.cart.views import get_or_create_cart
from apps.catalog.models import Product, ProductVariant


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .select_related("shipping_address")
            .prefetch_related("items")
        )

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            order = get_object_or_404(
                Order.objects.select_for_update(), pk=pk, user=request.user
            )
            items = list(order.items.select_for_update())
            if order.status == Order.Status.CANCELLED:
                return Response({"detail": "This order is already cancelled."}, status=400)
            if order.status not in (Order.Status.PENDING, Order.Status.PAID) or any(
                i.fulfilment_status != OrderItem.Fulfilment.PENDING for i in items
            ):
                return Response(
                    {"detail": "This order has already shipped and can no longer be cancelled."},
                    status=status.HTTP_409_CONFLICT,
                )
            variant_ids = sorted({i.variant_id for i in items if i.variant_id})
            variants = {
                v.id: v for v in ProductVariant.objects.select_for_update().filter(id__in=variant_ids).order_by("id")
            }
            for i in items:
                if i.variant_id in variants:
                    v = variants[i.variant_id]
                    v.stock += i.quantity
                    v.save(update_fields=["stock"])
            order.status = Order.Status.CANCELLED
            order.cancelled_at = timezone.now()
            order.save(update_fields=["status", "cancelled_at", "updated_at"])
        order = self.get_queryset().get(pk=order.pk)
        return Response(OrderSerializer(order).data)


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout"

    @extend_schema(
        request=CheckoutSerializer,
        responses={200: OrderSerializer, 201: OrderSerializer},
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=False,
                description="8-64 characters of letters, digits, '-' or '_'. Repeating a request with the same key returns the original order instead of creating another one.",
            )
        ],
        description="Turns the signed-in user's cart into an order and deducts stock in one transaction.",
    )
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = get_object_or_404(
            Address, pk=serializer.validated_data["shipping_address_id"], user=request.user
        )

        key = request.headers.get("Idempotency-Key")
        if key is not None and not KEY_PATTERN.match(key):
            return Response(
                {"detail": "Idempotency-Key must be 8-64 characters: letters, digits, '-' or '_'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            order, replayed = place_order(request, address, key)
        except CheckoutError as exc:
            return Response({"detail": exc.detail}, status=exc.status)

        order = (
            Order.objects.select_related("shipping_address").prefetch_related("items").get(pk=order.pk)
        )
        response = Response(
            OrderSerializer(order).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
        if replayed:
            response["Idempotent-Replayed"] = "true"
        return response


def _orders_for_seller(user):
    return Order.objects.filter(items__variant__product__seller=user).distinct()


class ReceivedOrdersView(generics.ListAPIView):
    serializer_class = SaleOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        mine = OrderItem.objects.filter(variant__product__seller=user)
        return (
            _orders_for_seller(user)
            .select_related("shipping_address")
            .prefetch_related(Prefetch("items", queryset=mine, to_attr="seller_items"))
            .order_by("-created_at")
        )


class ReceivedOrdersCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = _orders_for_seller(request.user)
        raw = request.query_params.get("since", "")
        if raw:
            try:
                since = parse_datetime(raw)
            except ValueError:
                since = None
            if since:
                if timezone.is_naive(since):
                    since = timezone.make_aware(since)
                qs = qs.filter(created_at__gt=since)
        return Response({"count": qs.count()})


class FulfilView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    ORDER = {"pending": 0, "shipped": 1, "delivered": 2}

    @extend_schema(request=FulfilSerializer, responses=SaleOrderSerializer)
    def post(self, request, order_id):
        serializer = FulfilSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        carrier = serializer.validated_data.get("carrier", "").strip()
        tracking = serializer.validated_data.get("tracking_number", "").strip()

        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=order_id)
            if not order.items.filter(variant__product__seller=request.user).exists():
                raise Http404
            if order.status == Order.Status.CANCELLED:
                return Response({"detail": "This order was cancelled."}, status=409)
            mine = list(
                order.items.select_for_update().filter(variant__product__seller=request.user)
            )
            now = timezone.now()
            for item in mine:
                if self.ORDER[new_status] < self.ORDER[item.fulfilment_status]:
                    return Response(
                        {"detail": "An item cannot move backwards in fulfilment."}, status=400
                    )
            for item in mine:
                item.fulfilment_status = new_status
                if carrier:
                    item.carrier = carrier
                if tracking:
                    item.tracking_number = tracking
                if not item.shipped_at:
                    item.shipped_at = now
                if new_status == OrderItem.Fulfilment.DELIVERED and not item.delivered_at:
                    item.delivered_at = now
                item.save()

            statuses = {i.fulfilment_status for i in order.items.all()}
            if statuses == {OrderItem.Fulfilment.DELIVERED}:
                order.status = Order.Status.DELIVERED
            elif statuses - {OrderItem.Fulfilment.PENDING}:
                order.status = Order.Status.SHIPPED
            order.save(update_fields=["status", "updated_at"])

        order = (
            _orders_for_seller(request.user)
            .select_related("shipping_address")
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=OrderItem.objects.filter(variant__product__seller=request.user),
                    to_attr="seller_items",
                )
            )
            .get(pk=order.pk)
        )
        return Response(SaleOrderSerializer(order).data)


class SellerStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        user = request.user
        if user.role not in ("seller", "admin"):
            return Response({"detail": "Only seller accounts have sales statistics."}, status=403)

        line_total = ExpressionWrapper(
            F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)
        )
        lines = OrderItem.objects.filter(variant__product__seller=user).exclude(
            order__status=Order.Status.CANCELLED
        )
        totals = lines.aggregate(
            revenue=Sum(line_total), units=Sum("quantity"), orders=Count("order", distinct=True)
        )
        since = timezone.now() - timedelta(days=30)
        recent = lines.filter(order__created_at__gte=since).aggregate(
            revenue=Sum(line_total), orders=Count("order", distinct=True)
        )
        by_day = {}
        for row in lines.filter(order__created_at__gte=since).values(
            "order__created_at__date"
        ).annotate(revenue=Sum(line_total)):
            by_day[str(row["order__created_at__date"])] = f"{row['revenue']:.2f}"
        top = (
            lines.values("variant__product_id", "product_name")
            .annotate(revenue=Sum(line_total), units=Sum("quantity"))
            .order_by("-revenue")[:5]
        )
        from apps.catalog.models import Product, ProductVariant

        low = ProductVariant.objects.filter(
            product__seller=user, product__status=Product.Status.ACTIVE, stock__lte=5
        ).select_related("product").order_by("stock")[:10]
        to_ship = (
            lines.filter(fulfilment_status=OrderItem.Fulfilment.PENDING)
            .values("order").distinct().count()
        )
        return Response({
            "revenue": f"{(totals['revenue'] or 0):.2f}",
            "units_sold": totals["units"] or 0,
            "orders": totals["orders"] or 0,
            "revenue_30d": f"{(recent['revenue'] or 0):.2f}",
            "orders_30d": recent["orders"] or 0,
            "revenue_by_day": by_day,
            "orders_to_ship": to_ship,
            "active_products": Product.objects.filter(seller=user, status=Product.Status.ACTIVE).count(),
            "top_products": [
                {"product_id": r["variant__product_id"], "name": r["product_name"],
                 "revenue": f"{r['revenue']:.2f}", "units": r["units"]}
                for r in top
            ],
            "low_stock": [
                {"product_id": v.product_id, "product": v.product.name, "sku": v.sku, "stock": v.stock}
                for v in low
            ],
        })


class AdminStatsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from django.contrib.auth import get_user_model
        from apps.catalog.models import Product

        User = get_user_model()
        line_total = ExpressionWrapper(
            F("unit_price") * F("quantity"), output_field=DecimalField(max_digits=14, decimal_places=2)
        )
        lines = OrderItem.objects.exclude(order__status=Order.Status.CANCELLED)
        return Response({
            "users": {r["role"]: r["n"] for r in User.objects.values("role").annotate(n=Count("id"))},
            "products": {r["status"]: r["n"] for r in Product.objects.values("status").annotate(n=Count("id"))},
            "orders": {r["status"]: r["n"] for r in Order.objects.values("status").annotate(n=Count("id"))},
            "gross_sales": f"{(lines.aggregate(t=Sum(line_total))['t'] or 0):.2f}",
            "top_sellers": [
                {"seller": r["variant__product__seller__username"], "revenue": f"{r['revenue']:.2f}"}
                for r in lines.values("variant__product__seller__username")
                .annotate(revenue=Sum(line_total)).order_by("-revenue")[:5]
            ],
        })
