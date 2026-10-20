import re

from django.contrib.auth import authenticate, password_validation
from django.db import transaction
from rest_framework import serializers

from .models import Customer, User, UserAccess
from .otp import to_ascii_digits
from .utils import normalize_phone


# --------------------------------------------------------------------------
# Customer (OTP)
# --------------------------------------------------------------------------
class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value):
        return normalize_phone(value)  # -> 9123456789


class OTPVerifySerializer(PhoneSerializer):
    code = serializers.CharField(max_length=10)

    def validate_code(self, value):
        value = to_ascii_digits(value)
        if not re.fullmatch(r"\d{6}", value):
            raise serializers.ValidationError("کد باید ۶ رقم باشد.")
        return value


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "phone",
            "first_name",
            "last_name",
            "email",
            "created_at",
        ]
        read_only_fields = ["id", "phone", "created_at"]


# --------------------------------------------------------------------------
# User (پنل)
# --------------------------------------------------------------------------
class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        # کاربر غیرفعال هم None برمی‌گرداند؛ پیام عمداً یکسان است
        if user is None:
            raise serializers.ValidationError("نام کاربری یا رمز عبور اشتباه است.")
        attrs["user"] = user
        return attrs


class UserAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAccess
        exclude = ["id", "user"]


class UserSerializer(serializers.ModelSerializer):
    """خروجی (خواندن) کاربر؛ بدون پسورد."""

    access = UserAccessSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "phone",
            "first_name",
            "last_name",
            "email",
            "role",
            "is_active",
            "created_at",
            "updated_at",
            "access",
        ]
        read_only_fields = fields


class UserWriteSerializer(serializers.ModelSerializer):
    """ساخت/ویرایش کاربر توسط ادمین."""

    phone = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, max_length=20
    )
    password = serializers.CharField(
        write_only=True, required=False, trim_whitespace=False
    )
    access = UserAccessSerializer(required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "password",
            "phone",
            "first_name",
            "last_name",
            "email",
            "role",
            "is_active",
            "access",
        ]
        read_only_fields = ["id"]

    def validate_phone(self, value):
        if not value:
            return None
        phone = normalize_phone(value)
        qs = User.objects.filter(phone=phone)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("این شماره قبلاً ثبت شده است.")
        return phone

    def validate_password(self, value):
        password_validation.validate_password(value, user=self.instance)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "رمز عبور الزامی است."})

        # ادمین نباید خودش را از ادمینی بیندازد یا غیرفعال کند
        request = self.context.get("request")
        if self.instance and request and self.instance.pk == request.user.pk:
            new_role = attrs.get("role", self.instance.role)
            if new_role != User.Role.ADMIN or attrs.get("is_active") is False:
                raise serializers.ValidationError(
                    "نمی‌توانید نقش یا وضعیت حساب خودتان را تنزل دهید."
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        access = validated_data.pop("access", {})
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        UserAccess.objects.create(user=user, **access)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        access = validated_data.pop("access", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()

        if access is not None:
            UserAccess.objects.update_or_create(user=instance, defaults=access)
        return instance

    def to_representation(self, instance):
        fresh = User.objects.select_related("access").get(pk=instance.pk)
        return UserSerializer(fresh, context=self.context).data