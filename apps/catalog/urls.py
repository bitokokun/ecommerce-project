from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, ReviewViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")

review_list = ReviewViewSet.as_view({"get": "list", "post": "create"})
review_detail = ReviewViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"})

urlpatterns = [
    path("", include(router.urls)),
    path("products/<int:product_pk>/reviews/", review_list, name="product-reviews"),
    path("products/<int:product_pk>/reviews/<int:pk>/", review_detail, name="product-review-detail"),
]
