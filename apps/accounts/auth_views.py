from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from django.conf import settings

from .throttles import LoginUsernameThrottle
from .tokens import clear_refresh_cookie, cookie_auth_enabled, set_refresh_cookie


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle, LoginUsernameThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if cookie_auth_enabled() and response.status_code == status.HTTP_200_OK:
            refresh = response.data.pop("refresh", None)
            if refresh:
                set_refresh_cookie(response, refresh)
        return response


class RefreshView(TokenRefreshView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    def post(self, request, *args, **kwargs):
        data = request.data
        if cookie_auth_enabled() and not data.get("refresh"):
            token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
            if token:
                data = {"refresh": token}
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        payload = dict(serializer.validated_data)
        response = Response(payload, status=status.HTTP_200_OK)
        if cookie_auth_enabled():
            refresh = payload.pop("refresh", None)
            if refresh:
                set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    @extend_schema(request=None, responses={204: None}, description="Revokes the refresh token and clears the refresh cookie.")
    def post(self, request):
        token = request.data.get("refresh") or request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response
