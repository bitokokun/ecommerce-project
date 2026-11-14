from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from django.db.models import Avg
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer

from . import service


def _limit(request, default=4, maximum=12):
    try:
        return max(1, min(int(request.query_params.get("limit", default)), maximum))
    except ValueError:
        return default


def _serialize(ranked, request):
    ids = [pid for pid, _, _ in ranked]
    products = {
        p.id: p
        for p in Product.objects.filter(pk__in=ids, status=Product.Status.ACTIVE)
        .annotate(average_rating=Avg("reviews__rating"))
        .prefetch_related("images")
    }
    out = []
    for pid, score, reason in ranked:
        product = products.get(pid)
        if product is None:
            continue
        data = dict(ProductListSerializer(product, context={"request": request}).data)
        data["reason"] = reason
        data["score"] = score
        out.append(data)
    return out


class SimilarProductsView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, product_id):
        ranked = service.similar_products(product_id, _limit(request))
        return Response({"results": _serialize(ranked, request)})


class ForYouView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"personalized": False, "results": []})
        ranked = service.products_for_user(request.user, _limit(request))
        results = _serialize(ranked, request)
        return Response({"personalized": bool(results), "results": results})
