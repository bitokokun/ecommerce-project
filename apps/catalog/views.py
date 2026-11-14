from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from PIL import Image, UnidentifiedImageError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Prefetch
from rest_framework import viewsets, permissions, filters, status
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from .models import Category, Product, ProductImage, ProductVariant, Review, WishlistItem
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductWriteSerializer,
    ProductVariantSerializer,
    ProductImageSerializer,
    ReviewSerializer,
)


class IsSellerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.seller_id == request.user.id or request.user.is_staff


class IsSellerAccount(permissions.BasePermission):
    message = "Only seller accounts can create products."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.role == "seller" or u.is_staff))


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsSellerOrReadOnly]
    throttle_scope = "product_write"

    def get_permissions(self):
        if self.action == "create":
            return [IsSellerAccount()]
        return super().get_permissions()

    def get_throttles(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [ScopedRateThrottle()]
        return [AnonRateThrottle(), UserRateThrottle()]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "status", "seller"]
    search_fields = ["name", "description"]
    ordering_fields = ["base_price", "created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category", "seller", "seller__store").annotate(
            average_rating=Avg("reviews__rating")
        ).order_by("-created_at", "-id")
        if self.action == "retrieve":
            qs = qs.prefetch_related(
                "images",
                "variants",
                Prefetch("reviews", queryset=Review.objects.select_related("user")),
            )
        else:
            qs = qs.prefetch_related("images")
        if self.action in ("list", "retrieve"):
            if self.request.user.is_authenticated and self.request.user.is_staff:
                return qs
            if self.request.user.is_authenticated:
                from django.db.models import Q
                qs = qs.filter(Q(status=Product.Status.ACTIVE) | Q(seller=self.request.user))
            else:
                qs = qs.filter(status=Product.Status.ACTIVE)
        return qs

    def get_serializer_class(self):
        if self.action in ("list", "mine"):
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer

    @extend_schema(responses={204: None, 200: OpenApiTypes.OBJECT})
    def destroy(self, request, *args, **kwargs):
        product = self.get_object()
        if ProductVariant.objects.filter(product=product, order_items__isnull=False).exists():
            product.status = Product.Status.ARCHIVED
            product.save(update_fields=["status"])
            return Response(
                {"detail": "This product has been ordered, so it was archived instead of deleted."},
                status=status.HTTP_200_OK,
            )
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def mine(self, request):
        qs = (
            Product.objects.filter(seller=request.user)
            .select_related("category", "seller", "seller__store")
            .prefetch_related("images")
            .annotate(average_rating=Avg("reviews__rating"))
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProductVariant.objects.filter(
            product_id=self.kwargs["product_pk"],
            product__seller=self.request.user,
        ).order_by("id")

    def perform_create(self, serializer):
        product = get_object_or_404(
            Product,
            pk=self.kwargs["product_pk"],
        )
        if product.seller_id != self.request.user.id:
            raise PermissionDenied("Not your product.")
        serializer.save(product=product)

    def destroy(self, request, *args, **kwargs):
        variant = self.get_object()
        if variant.order_items.exists():
            return Response(
                {"detail": "This option has been ordered, so it cannot be deleted. Set its stock to 0 instead."},
                status=status.HTTP_409_CONFLICT,
            )
        variant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


class ProductImageUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_scope = "image_upload"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle()]

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {"image": {"type": "string", "format": "binary"}}, "required": ["image"]}}, responses=OpenApiTypes.OBJECT)
    def post(self, request, product_pk):
        try:
            product = Product.objects.get(pk=product_pk)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        if product.seller_id != request.user.id:
            return Response({"detail": "Not your product."}, status=status.HTTP_403_FORBIDDEN)

        file = request.FILES.get("image")
        if not file:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if file.size > MAX_IMAGE_BYTES:
            return Response(
                {"detail": "Image is larger than 5MB."}, status=status.HTTP_400_BAD_REQUEST
            )


        try:
            with Image.open(file) as im:
                if im.format not in ALLOWED_IMAGE_FORMATS:
                    return Response(
                        {"detail": "Use a JPEG, PNG or WebP image."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if im.width * im.height > MAX_IMAGE_PIXELS:
                    return Response(
                        {"detail": "Image dimensions are too large."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                im.verify()
        except (UnidentifiedImageError, OSError):
            return Response(
                {"detail": "That file isn't a valid image."}, status=status.HTTP_400_BAD_REQUEST
            )
        file.seek(0)

        try:
            with transaction.atomic():
                locked_product = Product.objects.select_for_update().get(pk=product_pk)
                if locked_product.seller_id != request.user.id:
                    return Response(
                        {"detail": "Not your product."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                is_first = not locked_product.images.filter(is_primary=True).exists()
                img = ProductImage.objects.create(
                    product=locked_product,
                    image=file,
                    is_primary=is_first,
                )
        except Product.DoesNotExist:
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(ProductImageSerializer(img).data, status=status.HTTP_201_CREATED)


class IsReviewAuthorOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user_id == request.user.id or request.user.is_staff


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsReviewAuthorOrReadOnly]

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs["product_pk"])

    def perform_create(self, serializer):
        product = get_object_or_404(
            Product,
            pk=self.kwargs["product_pk"],
            status=Product.Status.ACTIVE,
        )

        try:
            with transaction.atomic():
                serializer.save(
                    user=self.request.user,
                    product=product,
                )
        except IntegrityError:
            raise ValidationError({
                "detail": "You have already reviewed this product."
                })


class WishlistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=ProductListSerializer(many=True))
    def get(self, request):
        products = (
            Product.objects.filter(
                wishlisted_by__user=request.user, status=Product.Status.ACTIVE
            )
            .select_related("category", "seller", "seller__store")
            .prefetch_related("images")
            .annotate(average_rating=Avg("reviews__rating"))
            .order_by("-wishlisted_by__created_at")
        )
        data = ProductListSerializer(products, many=True, context={"request": request}).data
        return Response(data)

    @extend_schema(request={"application/json": {"type": "object", "properties": {"product": {"type": "integer"}}, "required": ["product"]}}, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        try:
            product_id = int(request.data.get("product"))
        except (TypeError, ValueError):
            return Response({"detail": "A product id is required."}, status=400)
        product = get_object_or_404(Product, pk=product_id, status=Product.Status.ACTIVE)
        _, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        return Response(
            {"product": product.id, "saved": True},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses={204: None})
    def delete(self, request, product_id):
        WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WishlistIdsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses={200: {"type": "array", "items": {"type": "integer"}}})
    def get(self, request):
        ids = list(
            WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True)
        )
        return Response(ids)
