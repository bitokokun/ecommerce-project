from rest_framework import generics, permissions, viewsets
from rest_framework.throttling import ScopedRateThrottle
from .models import Address
from .serializers import RegisterSerializer, UserSerializer, AddressSerializer


class RegisterView(generics.CreateAPIView):
    # a script could otherwise spin up unlimited seller accounts to spam
    # products; this caps new accounts to 5 per hour per IP (see
    # DEFAULT_THROTTLE_RATES["register"] in settings.py)
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"


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
