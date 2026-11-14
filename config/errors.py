from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.views.defaults import page_not_found
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ProtectedError):
        return Response(
            {"detail": "This item is referenced by other records and cannot be removed."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "The change conflicted with another update. Please try again."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, DjangoValidationError):
        return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    return None


def server_error(request, *args, **kwargs):
    return JsonResponse({"detail": "Something went wrong on our side."}, status=500)


def not_found(request, exception, *args, **kwargs):
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": "Not found."}, status=404)
    return page_not_found(request, exception, *args, **kwargs)
