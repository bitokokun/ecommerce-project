from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Address, SellerProfile


class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Role & Contact", {"fields": ("role", "phone_number", "avatar")}),
        ("Preferences", {"fields": ("marketing_emails", "order_update_emails")}),
    )
    list_display = ("username", "email", "role", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    actions = ["deactivate_users", "reactivate_users"]

    @admin.action(description="Deactivate selected users (they cannot log in)")
    def deactivate_users(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).update(is_active=False)
        self.message_user(request, f"{n} user(s) deactivated.")

    @admin.action(description="Reactivate selected users")
    def reactivate_users(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} user(s) reactivated.")


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("store_name", "user", "created_at")
    search_fields = ("store_name", "user__username")
    list_select_related = ("user",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "city", "is_default")
    list_filter = ("is_default", "country")


admin.site.register(User, UserAdmin)
