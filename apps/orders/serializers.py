from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "id", "product_name", "sku", "unit_price", "quantity", "subtotal",
            "fulfilment_status", "carrier", "tracking_number", "shipped_at", "delivered_at",
        )


def order_can_cancel(order):
    if order.status not in (Order.Status.PENDING, Order.Status.PAID):
        return False
    return not any(i.fulfilment_status != OrderItem.Fulfilment.PENDING for i in order.items.all())


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()
    shipping_to = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "status", "shipping_address", "shipping_to", "total_amount", "items",
            "created_at", "cancelled_at", "can_cancel", "timeline",
        )
        read_only_fields = fields

    def get_can_cancel(self, obj):
        return order_can_cancel(obj)

    def get_shipping_to(self, obj):
        a = obj.shipping_address
        return {
            "name": a.full_name, "line1": a.line1, "line2": a.line2, "city": a.city,
            "state": a.state, "postal_code": a.postal_code, "country": a.country,
        }

    def get_timeline(self, obj):
        events = [{"key": "placed", "label": "Order placed", "at": obj.created_at}]
        for i in obj.items.all():
            if i.shipped_at:
                label = f"{i.product_name} shipped"
                if i.carrier or i.tracking_number:
                    label += f" ({' '.join(x for x in (i.carrier, i.tracking_number) if x)})"
                events.append({"key": f"shipped-{i.id}", "label": label, "at": i.shipped_at})
            if i.delivered_at:
                events.append({"key": f"delivered-{i.id}", "label": f"{i.product_name} delivered", "at": i.delivered_at})
        if obj.cancelled_at:
            events.append({"key": "cancelled", "label": "Order cancelled", "at": obj.cancelled_at})
        return sorted(events, key=lambda e: e["at"])


class CheckoutSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField()


class SaleItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = (
            "id", "product_name", "sku", "unit_price", "quantity", "subtotal",
            "fulfilment_status", "carrier", "tracking_number", "shipped_at", "delivered_at",
        )


class FulfilSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        OrderItem.Fulfilment.SHIPPED, OrderItem.Fulfilment.DELIVERED,
    ])
    carrier = serializers.CharField(max_length=60, required=False, allow_blank=True)
    tracking_number = serializers.CharField(max_length=100, required=False, allow_blank=True)


class SaleOrderSerializer(serializers.ModelSerializer):
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
