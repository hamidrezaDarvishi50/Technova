from django.shortcuts import render

# Create your views here.
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import SAFE_METHODS, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema, OpenApiResponse

from accounts.permission import IsAdminRole
from .models import Category, Product
from .serializers import *

from accounts.authentication import CustomerJWTAuthentication
from accounts.permission import IsCustomer

from django.db.models import BigIntegerField, ExpressionWrapper, F, ProtectedError
from django.db.models.functions import Cast


class PublicReadAdminWriteMixin:
    """
    GET/HEAD/OPTIONS: برای همه (بدون احراز هویت، حتی مهمان).
    بقیه‌ی متدها: فقط کاربری با role=admin.

    روی متدهای خواندنی authentication را خاموش می‌کنیم تا مشتری‌ای که
    توکن خودش را می‌فرستد (یا توکن منقضی دارد) برای دیدن دسته‌بندی‌ها 401 نگیرد.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]


    def _is_safe_request(self):
        request = getattr(self, "request", None)
        return request is not None and request.method in SAFE_METHODS

    def get_authenticators(self):
        if self._is_safe_request():
            return []
        return super().get_authenticators()

    def get_permissions(self):
        if self._is_safe_request():
            return [AllowAny()]
        return [IsAdminRole()]
    
    
class CategoryListCreateView(PublicReadAdminWriteMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        responses=CategorySerializer(many=True),
        summary="دریافت فهرست دسته‌بندی‌ها",
    )
    def get(self, request):
        categories = Category.objects.all().order_by("-created_at")
        serializer = CategorySerializer(
            categories, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="ساخت دسته‌بندی (فقط ادمین)",
        request=CategorySerializer,
        responses={
            201: CategorySerializer,
            400: OpenApiResponse(description="اطلاعات نامعتبر است."),
            401: OpenApiResponse(description="احراز هویت نشده"),
            403: OpenApiResponse(description="دسترسی ندارید"),
        },
    )
    def post(self, request):
        serializer = CategorySerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status.HTTP_201_CREATED)


class CategoryDetailView(PublicReadAdminWriteMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]
    
    @extend_schema(
        responses=CategorySerializer,
        summary="دریافت جزئیات دسته‌بندی",
    )
    def get(self, request, slug):
        category = get_object_or_404(Category, slug=slug)
        serializer = CategorySerializer(
            category, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        request=CategorySerializer,
        responses={
            200: CategorySerializer,
            400: OpenApiResponse(description="داده نامعتبر"),
            401: OpenApiResponse(description="احراز هویت نشده"),
            403: OpenApiResponse(description="دسترسی ندارید"),
            404: OpenApiResponse(description="دسته‌بندی پیدا نشد"),
        },
        summary="ویرایش دسته‌بندی",
    )
    def patch(self, request, slug):
        category = get_object_or_404(Category, slug=slug)
        serializer = CategorySerializer(
            category,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="حذف دسته‌بندی (فقط ادمین)",
        responses={
            204: OpenApiResponse(description="دسته‌بندی حذف شد."),
            404: OpenApiResponse(description="دسته‌بندی یافت نشد."),
        },
    )
    def delete(self, request, slug):
        category = get_object_or_404(Category, slug=slug)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


FAVORITE_TAG = ["Favorite"]

class FavoriteBaseView(APIView):
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsCustomer]


class FavoriteListCreateView(FavoriteBaseView):
    @extend_schema(
        summary="لیست علاقه‌مندی‌های من",
        description="جدیدترین‌ها اول می‌آیند.",
        responses={
            200: ProductListSerializer(many=True),
            401: OpenApiResponse(description="احراز هویت نشده"),
        },
    )
    def get(self, request):
        through = request.user.favorite_products.through
        rows = (
            through.objects.filter(customer=request.user)
            .select_related("product__category")
            .order_by("-id")
        )
        products = [row.product for row in rows]
        serializer = ProductListSerializer(
            products, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="افزودن محصول به علاقه‌مندی‌ها",
        description="اگر محصول از قبل در لیست باشد، تغییری نمی‌کند و ۲۰۰ برمی‌گردد.",
        request=FavoriteAddSerializer,
        responses={
            201: ProductListSerializer,
            200: ProductListSerializer,
            400: OpenApiResponse(description="محصول نامعتبر است"),
            401: OpenApiResponse(description="احراز هویت نشده"),
        },
    )
    def post(self, request):
        serializer = FavoriteAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.validated_data["product"]

        favorites = request.user.favorite_products
        if favorites.filter(pk=product.pk).exists():
            code = status.HTTP_200_OK
        else:
            favorites.add(product)
            code = status.HTTP_201_CREATED

        data = ProductListSerializer(product, context={"request": request}).data
        return Response(data, status=code)


class FavoriteDetailView(FavoriteBaseView):
    @extend_schema(
        summary="حذف محصول از علاقه‌مندی‌ها",
        responses={
            204: OpenApiResponse(description="حذف شد"),
            401: OpenApiResponse(description="احراز هویت نشده"),
            404: OpenApiResponse(description="این محصول در علاقه‌مندی‌های شما نیست"),
        },
    )
    def delete(self, request, slug):
        product = get_object_or_404(request.user.favorite_products.all(), slug=slug)
        request.user.favorite_products.remove(product)
        return Response(status=status.HTTP_204_NO_CONTENT)
    


PRODUCT_TAG = ["Product"]

EFFECTIVE_PRICE = ExpressionWrapper(
    Cast("price", BigIntegerField()) * (100 - F("discount")) / 100,
    output_field=BigIntegerField(),
)

SORT_ORDERING = {
    "newest": ("-created_at", "-id"),
    "most_expensive": ("-effective_price", "-id"),
    "cheapest": ("effective_price", "-id"),
    "best_selling": ("-sold_count", "-id"),
}


def products_queryset():
    return Product.objects.select_related("category").annotate(
        effective_price=EFFECTIVE_PRICE
    )

def apply_filters(queryset, params):
    if "category" in params:
        queryset = queryset.filter(category__title=params["category"])
    if "min_price" in params:
        queryset = queryset.filter(effective_price__gte=params["min_price"])
    if "max_price" in params:
        queryset = queryset.filter(effective_price__lte=params["max_price"])
    return queryset.order_by(*SORT_ORDERING[params["sort"]])


class ProductListCreateView(PublicReadAdminWriteMixin, APIView):
    @extend_schema(
        summary="لیست محصولات (با مرتب‌سازی و فیلتر)",
        description=(
            "بدون پارامتر، همه‌ی محصولات از جدیدترین نمایش داده می‌شوند. "
            "فیلتر قیمت روی قیمت نهایی (بعد از تخفیف) اعمال می‌شود."
        ),
        parameters=[ProductFilterSerializer],
        responses={
            200: ProductListSerializer(many=True),
            400: OpenApiResponse(description="پارامتر نامعتبر"),
        },
    )
    def get(self, request):
        filters = ProductFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)

        queryset = apply_filters(products_queryset(), filters.validated_data)
        serializer = ProductListSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="ساخت محصول (فقط ادمین)",
        request=ProductWriteSerializer,
        responses={
            201: ProductDetailSerializer,
            400: OpenApiResponse(description="داده نامعتبر"),
            401: OpenApiResponse(description="احراز هویت نشده"),
            403: OpenApiResponse(description="دسترسی ندارید"),
        },
    )
    def post(self, request):
        serializer = ProductWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        data = ProductDetailSerializer(product, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED)


class ProductDiscountedListView(PublicReadAdminWriteMixin, APIView):
    @extend_schema(
        tags=PRODUCT_TAG,
        summary="محصولات تخفیف‌دار (بیشترین تخفیف اول)",
        responses=ProductListSerializer(many=True),
    )
    def get(self, request):
        queryset = products_queryset().filter(discount__gt=0).order_by(
            "-discount", "-created_at", "-id"
        )
        serializer = ProductListSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data)


class ProductDetailView(PublicReadAdminWriteMixin, APIView):
    
    @extend_schema(
        tags=PRODUCT_TAG,
        summary="جزئیات محصول",
        responses={
            200: ProductDetailSerializer,
            404: OpenApiResponse(description="محصول پیدا نشد"),
        },
    )
    def get(self, request, slug):
        product = get_object_or_404(products_queryset(), slug=slug)
        serializer = ProductDetailSerializer(product, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="ویرایش محصول (فقط ادمین)",
        request=ProductWriteSerializer,
        responses={
            200: ProductDetailSerializer,
            400: OpenApiResponse(description="داده نامعتبر"),
            401: OpenApiResponse(description="احراز هویت نشده"),
            403: OpenApiResponse(description="دسترسی ندارید"),
            404: OpenApiResponse(description="محصول پیدا نشد"),
        },
    )
    def patch(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        serializer = ProductWriteSerializer(
            product, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        data = ProductDetailSerializer(product, context={"request": request}).data
        return Response(data)

    @extend_schema(
        summary="حذف محصول (فقط ادمین)",
        responses={
            204: OpenApiResponse(description="حذف شد"),
            401: OpenApiResponse(description="احراز هویت نشده"),
            403: OpenApiResponse(description="دسترسی ندارید"),
            404: OpenApiResponse(description="محصول پیدا نشد"),
            409: OpenApiResponse(description="محصول در سفارش‌ها استفاده شده و حذف نمی‌شود"),
        },
    )
    def delete(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        image = product.image
        try:
            product.delete()
        except ProtectedError:
            return Response(
                {"detail": "این محصول در سفارش‌ها استفاده شده و قابل حذف نیست."},
                status=status.HTTP_409_CONFLICT,
            )
        if image:
            image.delete(save=False)  
        return Response(status=status.HTTP_204_NO_CONTENT)