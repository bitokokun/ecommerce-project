from django.urls import path

from .views import ForYouView, SimilarProductsView

urlpatterns = [
    path("similar/<int:product_id>/", SimilarProductsView.as_view(), name="recommendations-similar"),
    path("for-you/", ForYouView.as_view(), name="recommendations-for-you"),
]
