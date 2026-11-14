from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView, MeView, AddressViewSet, CountryListView, AvatarView,
    ChangePasswordView, DeleteAccountView, StoreView, StoreLogoView,
)

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", AvatarView.as_view(), name="avatar"),
    path("password/", ChangePasswordView.as_view(), name="change-password"),
    path("delete/", DeleteAccountView.as_view(), name="delete-account"),
    path("store/", StoreView.as_view(), name="store"),
    path("store/logo/", StoreLogoView.as_view(), name="store-logo"),
    path("countries/", CountryListView.as_view(), name="countries"),
    path("", include(router.urls)),
]
