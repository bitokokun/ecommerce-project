from django.contrib import admin
from .models import Category, Product, ProductImage, ProductVariant, Review, WishlistItem


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "seller", "category", "base_price", "status", "created_at")
    list_filter = ("status", "category")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariantInline]
    list_select_related = ("seller", "category")
    actions = ["archive_selected", "activate_selected"]

    @admin.action(description="Archive selected products (hide from the shop)")
    def archive_selected(self, request, queryset):
        n = queryset.update(status=Product.Status.ARCHIVED)
        self.message_user(request, f"{n} product(s) archived.")

    @admin.action(description="Activate selected products")
    def activate_selected(self, request, queryset):
        n = queryset.update(status=Product.Status.ACTIVE)
        self.message_user(request, f"{n} product(s) activated.")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "created_at")
    list_filter = ("rating",)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    list_select_related = ("user", "product")
