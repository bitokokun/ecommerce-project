from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from django.db import transaction
from django.db.models import Prefetch
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Cart, CartItem
from .serializers import CartAddSerializer, CartItemSerializer, CartSerializer
from apps.catalog.models import Product, ProductVariant
from .validation import parse_id, parse_quantity


def get_or_create_cart(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    if not request.session.session_key:
        request.session.create()
    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key)
    return cart


def cart_data(cart):
    fresh = Cart.objects.prefetch_related(
        Prefetch("items", queryset=CartItem.objects.select_related("variant__product").order_by("id"))
    ).get(pk=cart.pk)
    return CartSerializer(fresh).data


class CartDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=CartSerializer)
    def get(self, request):
        cart = get_or_create_cart(request)
        return Response(cart_data(cart))


class CartItemAddView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=CartAddSerializer, responses={201: CartSerializer})
    def post(self, request):
        try:
            variant_id = parse_id(request.data.get("variant"), "item")
            quantity = parse_quantity(request.data.get("quantity"))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            cart = get_or_create_cart(request)
            cart = Cart.objects.select_for_update().get(pk=cart.pk)
            variant = get_object_or_404(
                ProductVariant.objects.select_for_update().select_related("product"),
                pk=variant_id,
                product__status=Product.Status.ACTIVE,
            )
            item = CartItem.objects.select_for_update().filter(
                cart=cart, variant=variant
            ).first()
            new_quantity = quantity + (item.quantity if item else 0)
            if new_quantity > variant.stock:
                return Response(
                    {"detail": f"Only {variant.stock} unit(s) of {variant.sku} available."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if item:
                item.quantity = new_quantity
                item.save(update_fields=["quantity"])
            else:
                CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)

        return Response(cart_data(cart), status=status.HTTP_201_CREATED)


class CartItemUpdateView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=CartItemSerializer, responses=CartSerializer)
    def patch(self, request, item_id):
        with transaction.atomic():
            cart = get_or_create_cart(request)
            cart = Cart.objects.select_for_update().get(pk=cart.pk)
            item = get_object_or_404(CartItem.objects.select_for_update(), pk=item_id, cart=cart)
            serializer = CartItemSerializer(item, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(cart_data(cart))

    @extend_schema(request=None, responses=CartSerializer)
    def delete(self, request, item_id):
        with transaction.atomic():
            cart = get_or_create_cart(request)
            cart = Cart.objects.select_for_update().get(pk=cart.pk)
            item = get_object_or_404(CartItem.objects.select_for_update(), pk=item_id, cart=cart)
            item.delete()
        return Response(cart_data(cart))
