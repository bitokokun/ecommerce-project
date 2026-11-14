from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "sku", "unit_price", "quantity")
    fields = readonly_fields + ("fulfilment_status", "carrier", "tracking_number")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
