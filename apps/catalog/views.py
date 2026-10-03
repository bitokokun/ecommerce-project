from django.db.models import Avg
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from .models import Category, Product, ProductImage, ProductVariant, Review
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


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsSellerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["category", "status", "seller"]
    search_fields = ["name", "description"]
    ordering_fields = ["base_price", "created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category", "seller").prefetch_related(
            "images", "variants"
        ).annotate(average_rating=Avg("reviews__rating"))
        if self.action == "list":
            qs = qs.filter(status=Product.Status.ACTIVE)
        return qs

    def get_serializer_class(self):
        if self.action in ("list", "mine"):
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def mine(self, request):
        """
        A seller's own dashboard list — unlike the public list, this includes
        drafts and archived products too, since the seller needs to see and
        edit everything they own, not just what's live for customers.
        """
        qs = (
            Product.objects.filter(seller=request.user)
            .select_related("category")
            .prefetch_related("images", "variants")
            .annotate(average_rating=Avg("reviews__rating"))
            .order_by("-created_at")
        )
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """
    Nested under a product: /api/catalog/products/<id>/variants/
    A seller manages SKUs and stock for their own products here, without
    needing Django admin access.
    """
    serializer_class = ProductVariantSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProductVariant.objects.filter(
            product_id=self.kwargs["product_pk"], product__seller=self.request.user
        )

    def perform_create(self, serializer):
        product = Product.objects.get(pk=self.kwargs["product_pk"])
        if product.seller_id != self.request.user.id:
            raise PermissionDenied("Not your product.")
        serializer.save(product=product)


class ProductImageUploadView(APIView):
    """
    POST a single multipart "image" file to /products/<id>/images/upload/
    so a seller can add product photos from the dashboard without touching
    Django admin. Marks the new image primary if the product has none yet.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

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

        is_first = not product.images.exists()
        img = ProductImage.objects.create(product=product, image=file, is_primary=is_first)
        return Response(ProductImageSerializer(img).data, status=status.HTTP_201_CREATED)


class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs["product_pk"])

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, product_id=self.kwargs["product_pk"])
