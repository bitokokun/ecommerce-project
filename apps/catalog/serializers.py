from django.core.exceptions import ObjectDoesNotExist
from django.core.files import images
from rest_framework import request, serializers
from .models import Category, Product, ProductImage, ProductVariant, Review
from decimal import Decimal


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text", "is_primary", "order")


class ProductVariantSerializer(serializers.ModelSerializer):
    price_override = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0")
    )
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = ("id", "sku", "attributes", "price_override", "price", "stock", "in_stock")


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = ("id", "user", "rating", "comment", "created_at")
        read_only_fields = ("id", "user", "created_at")
        extra_kwargs = {"comment": {"max_length": 2000}}

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be from 1 to 5.")
        return value


class ProductListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True)
    category_name = serializers.SerializerMethodField()
    seller_name = serializers.SerializerMethodField()
    store_logo = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "name", "slug", "base_price", "primary_image", "average_rating", "status",
            "category", "category_name", "seller_name", "store_logo",
        )

    def _store(self, obj):
        try:
            return obj.seller.store
        except ObjectDoesNotExist:
            return None

    def get_category_name(self, obj):
        return obj.category.name if obj.category_id else ""

    def get_seller_name(self, obj):
        store = self._store(obj)
        return store.store_name if store else obj.seller.username

    def get_store_logo(self, obj):
        store = self._store(obj)
        if not store or not store.logo:
            return None
        url = store.logo.url
        request = self.context.get("request")
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    def get_primary_image(self, obj):
        images = list(obj.images.all())

        img = next(
            (image for image in images if image.is_primary),
            images[0] if images else None,
        )

        if not img:
            return None

        url = img.image.url
        request = self.context.get("request")

        if request and url.startswith("/"):
            return request.build_absolute_uri(url)

        return url
        if not img:
            return None
        url = img.image.url
        request = self.context.get("request")
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url


class ProductDetailSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    category = CategorySerializer(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    seller = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "name", "slug", "description", "base_price", "status",
            "category", "seller", "images", "variants", "reviews",
            "average_rating", "created_at",
        )


class ProductWriteSerializer(serializers.ModelSerializer):
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))

    class Meta:
        model = Product
        fields = ("id", "name", "category", "description", "base_price", "status")

    def create(self, validated_data):
        validated_data["seller"] = self.context["request"].user
        return super().create(validated_data)
