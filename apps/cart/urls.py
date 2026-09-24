from django.urls import path
from .views import CartDetailView, CartItemAddView, CartItemUpdateView

urlpatterns = [
    path("", CartDetailView.as_view(), name="cart-detail"),
    path("items/", CartItemAddView.as_view(), name="cart-item-add"),
    path("items/<int:item_id>/", CartItemUpdateView.as_view(), name="cart-item-update"),
]
