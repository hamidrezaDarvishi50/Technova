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

from . import Otp
from .authentication import ACTOR_CUSTOMER, ACTOR_USER, CustomerJWTAuthentication, tokens_for_customer, tokens_for_user
from .models import Customer, User
from .Permission import IsAdminRole, IsCustomer, IsStaffUser
from .serializers import *
from .Tasks import send_otp_sms


class CustomerOTPRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request: Request):
        serializer = PhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        code = Otp.issue_otp(phone)
        send_otp_sms.delay(phone, code)

        return Response({"detail": "کد تایید ارسال شد.", "expires_in": otp.OTP_TTL})


class CustomerOTPVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "otp"

    def post(self, request: Request):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]

        Otp.verify_otp(phone, serializer.validated_data["code"])

        customer, created = Customer.objects.get_or_create(phone=phone)
        if not customer.is_active:
            return Response(
                {"detail": "حساب کاربری شما غیرفعال است."},
                status=status.HTTP_403_FORBIDDEN,
            )

        customer.last_login = timezone.now()
        customer.save(update_fields=["last_login"])

        return Response(
            {
                "tokens": tokens_for_customer(customer),
                "is_new": created,
                "profile_completed": bool(customer.first_name and customer.last_name),
                "customer": CustomerSerializer(customer).data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CustomerMeView(RetrieveUpdateAPIView):
    authentication_classes = [CustomerJWTAuthentication]
    permission_classes = [IsCustomer]
    serializer_class = CustomerSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return self.request.user


class _BaseRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    actor = None

    def is_active(self, token) -> bool:
        raise NotImplementedError

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
        return User.objects.filter(pk=token.get("user_id"), is_active=True).exists()


class UserLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

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

    def get(self, request):
        return Response(UserSerializer(request.user).data)


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