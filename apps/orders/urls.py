from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, CheckoutView, ReceivedOrdersView, ReceivedOrdersCountView

router = DefaultRouter()
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("received/", ReceivedOrdersView.as_view(), name="received-orders"),
    path("received/count/", ReceivedOrdersCountView.as_view(), name="received-orders-count"),
    path("", include(router.urls)),
]
