from rest_framework import generics, permissions, viewsets
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Address
from .serializers import RegisterSerializer, UserSerializer, AddressSerializer
from .captcha import verify_turnstile
from .countries import COUNTRIES


class RegisterView(generics.CreateAPIView):
    # a script could otherwise spin up unlimited seller accounts to spam
    # products; this caps new accounts to 5 per hour per IP (see
    # DEFAULT_THROTTLE_RATES["register"] in settings.py)
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
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class CountryListView(APIView):
    """The countries shown in the address dropdown."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(COUNTRIES)
