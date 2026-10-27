from django.urls import path
from .views import *

urlpatterns = [
    path("categories/", CategoryListCreateView.as_view(), name="category-list"),
    path("categories/<str:slug>/", CategoryDetailView.as_view(), name="category-detail"),
    
    path("favorites/", FavoriteListCreateView.as_view(), name="favorite-list"),
    path("favorites/<str:slug>/", FavoriteDetailView.as_view(), name="favorite-detail"),
    
    path("discounted/",ProductDiscountedListView.as_view(), name="product-discounted"),
    path("", ProductListCreateView.as_view(), name="product-list"),
    path("<str:slug>/", ProductDetailView.as_view(), name="product-detail"),
]