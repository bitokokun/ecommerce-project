from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, CheckoutView, ReceivedOrdersView, ReceivedOrdersCountView, FulfilView, SellerStatsView, AdminStatsView

router = DefaultRouter()
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("received/", ReceivedOrdersView.as_view(), name="received-orders"),
    path("received/<int:order_id>/fulfil/", FulfilView.as_view(), name="fulfil-order"),
    path("seller-stats/", SellerStatsView.as_view(), name="seller-stats"),
    path("admin-stats/", AdminStatsView.as_view(), name="admin-stats"),
    path("received/count/", ReceivedOrdersCountView.as_view(), name="received-orders-count"),
    path("", include(router.urls)),
]
