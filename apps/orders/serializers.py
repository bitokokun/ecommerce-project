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


class SaleItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product_name", "sku", "unit_price", "quantity", "subtotal")


class SaleOrderSerializer(serializers.ModelSerializer):
    """
    An order as a SELLER sees it: only that seller's own lines (an order can
    contain several sellers' products), plus where to ship them. The buyer's
    email and phone are deliberately not included.
    """
    items = SaleItemSerializer(source="seller_items", many=True, read_only=True)
    ship_to = serializers.SerializerMethodField()
    seller_total = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ("id", "status", "created_at", "ship_to", "items", "seller_total")

    def get_ship_to(self, obj):
        a = obj.shipping_address
        return {
            "name": a.full_name,
            "line1": a.line1,
            "line2": a.line2,
            "city": a.city,
            "state": a.state,
            "postal_code": a.postal_code,
            "country": a.country,
        }

    def get_seller_total(self, obj):
        from decimal import Decimal

        total = sum((i.subtotal for i in obj.seller_items), Decimal("0"))
        return f"{total:.2f}"
