from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RegisterView, MeView, AddressViewSet, CountryListView

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("countries/", CountryListView.as_view(), name="countries"),
    path("", include(router.urls)),
]
