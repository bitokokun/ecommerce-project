from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Order, OrderItem
from .serializers import OrderSerializer, CheckoutSerializer
from apps.accounts.models import Address
from apps.cart.views import get_or_create_cart
from apps.catalog.models import ProductVariant


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items")


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = get_object_or_404(
            Address, pk=serializer.validated_data["shipping_address_id"], user=request.user
        )

        cart = get_or_create_cart(request)
        items = list(cart.items.select_related("variant", "variant__product"))
        if not items:
            return Response({"detail": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            variant_ids = [i.variant_id for i in items]
            locked_variants = {
                v.id: v for v in
                ProductVariant.objects.select_for_update().filter(id__in=variant_ids)
            }

            for item in items:
                variant = locked_variants[item.variant_id]
                if item.quantity > variant.stock:
                    return Response(
                        {"detail": f"Only {variant.stock} unit(s) of {variant.sku} left."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            order = Order.objects.create(
                user=request.user, shipping_address=address, total_amount=0
            )
            for item in items:
                variant = locked_variants[item.variant_id]
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    product_name=variant.product.name,
                    sku=variant.sku,
                    unit_price=variant.price,
                    quantity=item.quantity,
                )
                variant.stock -= item.quantity
                variant.save(update_fields=["stock"])

            order.recalculate_total()
            cart.items.all().delete()

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
