from django.shortcuts import render

# Create your views here.
from django.contrib.auth.models import update_last_login
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from . import otp
from .authentication import (
    ACTOR_CUSTOMER,
    ACTOR_USER,
    CustomerJWTAuthentication,
    tokens_for_customer,
    tokens_for_user,
)
from .models import Customer, User
from .permission import IsAdminRole, IsCustomer, IsStaffUser
from .serializers import *
from .tasks import send_otp_sms
from django.conf import settings


class CustomerOTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    @extend_schema(
        request=PhoneSerializer,
        responses={
            200: OpenApiResponse(description="کد تایید ارسال شد.")
        },
        summary="درخواست کد تایید مشتری",
    )
    def post(self, request: Request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        code = otp.issue_otp(phone)
        send_otp_sms.delay(phone, code)

        data = {"detail": "کد تایید ارسال شد.", "expires_in": otp.OTP_TTL}
        if settings.DEBUG:
            data["debug_code"] = code

        return Response(data)


class CustomerOTPVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    @extend_schema(
        request=OTPVerifySerializer,
        responses={
            200: OpenApiResponse(description="ورود موفق مشتری"),
            201: OpenApiResponse(description="ثبت‌نام و ورود موفق مشتری"),
            403: OpenApiResponse(description="حساب کاربری غیرفعال است."),
        },
        summary="تایید کد و ورود مشتری",
    )
    def post(self, request: Request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        otp.verify_otp(phone, serializer.validated_data["code"])

        customer, created = Customer.objects.get_or_create(phone=phone)
        if not customer.is_active:
            return Response(
                {"detail": "حساب کاربری شما غیرفعال است."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "tokens": tokens_for_customer(customer),
                "is_new": created,
                "profile_completed": bool(
                    customer.first_name and customer.last_name
                ),
                "customer": CustomerSerializer(customer).data,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )


class CustomerMeView(RetrieveUpdateAPIView):
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsCustomer]
    serializer_class = CustomerSerializer
    http_method_names = ["get", "patch", "head", "options"]

    @extend_schema(
        responses=CustomerSerializer,
        summary="دریافت پروفایل مشتری",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        request=CustomerSerializer,
        responses=CustomerSerializer,
        summary="ویرایش پروفایل مشتری",
    )
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        return self.request.user


class _BaseRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    actor = None

    def is_active(self, token) -> bool:
        raise NotImplementedError

    @extend_schema(
        request=RefreshSerializer,
        responses={
            200: OpenApiResponse(description="توکن دسترسی جدید"),
        },
        summary="دریافت توکن دسترسی جدید",
    )
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        if token.get("actor") != self.actor or not self.is_active(token):
            raise InvalidToken("توکن نامعتبر است.")
        return Response({"access": str(token.access_token)})


class CustomerRefreshView(_BaseRefreshView):
    actor = ACTOR_CUSTOMER

    def is_active(self, token):
        return Customer.objects.filter(
            pk=token.get("customer_id"), is_active=True
        ).exists()


class UserRefreshView(_BaseRefreshView):
    actor = ACTOR_USER

    def is_active(self, token):
        return User.objects.filter(
            pk=token.get("user_id"), is_active=True
        ).exists()


class UserLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=UserLoginSerializer,
        responses={
            200: OpenApiResponse(description="ورود موفق کاربر سازمانی"),
        },
        summary="ورود کاربر سازمانی",
    )
    def post(self, request):
        serializer = UserLoginSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        update_last_login(None, user)
        return Response(
            {
                "tokens": tokens_for_user(user),
                "user": UserSerializer(user).data,
            }
        )


class UserMeView(APIView):
    permission_classes = [IsStaffUser]

    @extend_schema(
        responses=UserSerializer,
        summary="دریافت اطلاعات کاربر سازمانی",
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema_view(
    list=extend_schema(
        responses=UserSerializer(many=True),
        summary="دریافت فهرست کاربران",
    ),
    retrieve=extend_schema(
        responses=UserSerializer,
        summary="دریافت اطلاعات یک کاربر",
    ),
    create=extend_schema(
        request=UserWriteSerializer,
        responses=UserSerializer,
        summary="ایجاد کاربر",
    ),
    update=extend_schema(
        request=UserWriteSerializer,
        responses=UserSerializer,
        summary="ویرایش کامل کاربر",
    ),
    partial_update=extend_schema(
        request=UserWriteSerializer,
        responses=UserSerializer,
        summary="ویرایش بخشی از اطلاعات کاربر",
    ),
    destroy=extend_schema(
        responses={
            204: OpenApiResponse(
                description="حساب کاربر غیرفعال شد."
            )
        },
        summary="غیرفعال کردن کاربر",
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("access").order_by("-id")
    permission_classes = [IsAdminRole]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return UserSerializer
        return UserWriteSerializer

    def perform_destroy(self, instance):
        # حذف واقعی نمی‌کنیم؛ فقط غیرفعال می‌شود
        if instance.pk == self.request.user.pk:
            raise ValidationError("نمی‌توانید حساب خودتان را غیرفعال کنید.")
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])