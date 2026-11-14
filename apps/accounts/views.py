from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, viewsets
from rest_framework.parsers import MultiPartParser
from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Address, SellerProfile
from .serializers import (
    RegisterSerializer, UserSerializer, AddressSerializer, ChangePasswordSerializer,
    DeleteAccountSerializer, SellerProfileSerializer,
)
from .uploads import validate_image_upload
from .captcha import verify_turnstile
from .countries import COUNTRIES
from .tokens import revoke_user_tokens


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def create(self, request, *args, **kwargs):
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR")
        if not verify_turnstile(request.data.get("captcha_token"), ip):
            return Response(
                {"detail": "Captcha check failed. Please try again."}, status=400
            )
        return super().create(request, *args, **kwargs)


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class AddressViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AddressSerializer

    def get_queryset(self):
        return Address.objects.filter(
            user=self.request.user
        ).order_by("id")

    def perform_create(self, serializer):
        with transaction.atomic():
            type(self.request.user).objects.select_for_update().get(pk=self.request.user.pk)
            if serializer.validated_data.get("is_default", False):
                Address.objects.filter(user=self.request.user, is_default=True).update(is_default=False)
            serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        with transaction.atomic():
            type(self.request.user).objects.select_for_update().get(pk=self.request.user.pk)
            will_be_default = serializer.validated_data.get(
                "is_default", serializer.instance.is_default
            )
            if will_be_default:
                Address.objects.filter(user=self.request.user, is_default=True).exclude(
                    pk=serializer.instance.pk
                ).update(is_default=False)
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "This address is attached to an order and cannot be deleted."},
                status=409,
            )


class CountryListView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(COUNTRIES)


class AvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "image_upload"

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {"image": {"type": "string", "format": "binary"}}, "required": ["image"]}}, responses=UserSerializer)
    def post(self, request):
        file = validate_image_upload(request.FILES.get("image"))
        user = request.user
        old = user.avatar.name if user.avatar else None
        user.avatar.save(file.name, file, save=False)
        user.save(update_fields=["avatar"])
        if old and old != user.avatar.name:
            user.avatar.storage.delete(old)
        return Response(UserSerializer(user, context={"request": request}).data)

    @extend_schema(request=None, responses=UserSerializer)
    def delete(self, request):
        user = request.user
        if user.avatar:
            name = user.avatar.name
            user.avatar = ""
            user.save(update_fields=["avatar"])
            user.avatar.storage.delete(name)
        return Response(UserSerializer(user, context={"request": request}).data)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password"

    @extend_schema(request=ChangePasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        revoke_user_tokens(request.user)
        return Response({"detail": "Password updated."})


class DeleteAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password"

    @extend_schema(request=DeleteAccountSerializer, responses={204: None})
    def post(self, request):
        user = request.user
        if user.is_staff or user.is_superuser:
            return Response(
                {"detail": "Staff accounts cannot be deleted here."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DeleteAccountSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = type(user).objects.select_for_update().get(pk=user.pk)
            revoke_user_tokens(user)
            has_orders = user.orders.exists()
            has_sales = user.products.filter(variants__order_items__isnull=False).exists()
            if has_orders or has_sales:
                from apps.catalog.models import Product

                user.products.update(status=Product.Status.ARCHIVED)
                for addr in user.addresses.all():
                    try:
                        with transaction.atomic():
                            addr.delete()
                    except ProtectedError:
                        pass
                user.username = f"deleted-user-{user.pk}"
                user.email = ""
                user.first_name = ""
                user.last_name = ""
                user.phone_number = ""
                user.avatar = ""
                user.is_active = False
                user.set_unusable_password()
                user.save()
                SellerProfile.objects.filter(user=user).delete()
            else:
                user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IsSeller(permissions.BasePermission):
    message = "Only seller accounts have a store."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in ("seller", "admin"))


class StoreView(APIView):
    permission_classes = [IsSeller]

    def _store(self, user):
        store, _ = SellerProfile.objects.get_or_create(
            user=user, defaults={"store_name": user.username}
        )
        return store

    @extend_schema(responses=SellerProfileSerializer)
    def get(self, request):
        store = self._store(request.user)
        return Response(SellerProfileSerializer(store, context={"request": request}).data)

    @extend_schema(request=SellerProfileSerializer, responses=SellerProfileSerializer)
    def patch(self, request):
        store = self._store(request.user)
        serializer = SellerProfileSerializer(
            store, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StoreLogoView(APIView):
    permission_classes = [IsSeller]
    parser_classes = [MultiPartParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "image_upload"

    @extend_schema(request={"multipart/form-data": {"type": "object", "properties": {"image": {"type": "string", "format": "binary"}}, "required": ["image"]}}, responses=SellerProfileSerializer)
    def post(self, request):
        file = validate_image_upload(request.FILES.get("image"))
        store, _ = SellerProfile.objects.get_or_create(
            user=request.user, defaults={"store_name": request.user.username}
        )
        old = store.logo.name if store.logo else None
        store.logo.save(file.name, file, save=False)
        store.save(update_fields=["logo", "updated_at"])
        if old and old != store.logo.name:
            store.logo.storage.delete(old)
        return Response(SellerProfileSerializer(store, context={"request": request}).data)

    @extend_schema(request=None, responses=SellerProfileSerializer)
    def delete(self, request):
        store = SellerProfile.objects.filter(user=request.user).first()
        if store and store.logo:
            name = store.logo.name
            store.logo = ""
            store.save(update_fields=["logo", "updated_at"])
            store.logo.storage.delete(name)
        return Response(
            SellerProfileSerializer(store, context={"request": request}).data if store else {}
        )
