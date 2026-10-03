from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoryViewSet,
    ProductViewSet,
    ProductVariantViewSet,
    ProductImageUploadView,
    ReviewViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")

review_list = ReviewViewSet.as_view({"get": "list", "post": "create"})
review_detail = ReviewViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"})

variant_list = ProductVariantViewSet.as_view({"get": "list", "post": "create"})
variant_detail = ProductVariantViewSet.as_view({"patch": "partial_update", "delete": "destroy"})

urlpatterns = [
    path("", include(router.urls)),
    path("products/<int:product_pk>/reviews/", review_list, name="product-reviews"),
    path("products/<int:product_pk>/reviews/<int:pk>/", review_detail, name="product-review-detail"),
    path("products/<int:product_pk>/variants/", variant_list, name="product-variants"),
    path("products/<int:product_pk>/variants/<int:pk>/", variant_detail, name="product-variant-detail"),
    path("products/<int:product_pk>/images/upload/", ProductImageUploadView.as_view(), name="product-image-upload"),
]
