from rest_framework import serializers
from .models import Cart, CartItem
from apps.catalog.models import ProductVariant


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    unit_price = serializers.DecimalField(source="variant.price", max_digits=10, decimal_places=2, read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ("id", "variant", "product_name", "sku", "unit_price", "quantity", "subtotal")

    def validate(self, data):
        variant = data.get("variant") or getattr(self.instance, "variant", None)
        quantity = data.get("quantity", getattr(self.instance, "quantity", 1))
        if variant and quantity > variant.stock:
            raise serializers.ValidationError(
                f"Only {variant.stock} unit(s) of {variant.sku} available."
            )
        return data


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = ("id", "items", "total", "item_count", "updated_at")
