from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product_name", "sku", "unit_price", "quantity", "subtotal")


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ("id", "status", "shipping_address", "total_amount", "items", "created_at")
        read_only_fields = ("id", "status", "total_amount", "items", "created_at")


class CheckoutSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField()
