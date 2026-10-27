import hashlib
import hmac
import secrets
import time

from django.conf import settings
from django.core.cache import cache
from rest_framework.exceptions import Throttled, ValidationError

OTP_TTL = 120 
RESEND_COOLDOWN = 60 
MAX_VERIFY_ATTEMPTS = 5
MAX_SENDS_PER_HOUR = 5
OTP_LENGTH = 4
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def to_ascii_digits(value) -> str:
    return str(value).translate(_DIGITS).strip()


def _key(kind: str, phone: str) -> str:
    return f"otp:{kind}:{phone}"


def _hash(phone: str, code: str) -> str:
    # کد به‌صورت plain در Redis ذخیره نمی‌شود
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{phone}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def _incr(key: str, timeout: int) -> int:
    try:
        return cache.incr(key)
    except ValueError:  # کلید وجود ندارد
        cache.set(key, 1, timeout)
        return 1


def issue_otp(phone: str) -> str:
    """یک کد جدید می‌سازد و ذخیره می‌کند. phone باید نرمالایز شده باشد."""
    now = time.time()

    if not cache.add(_key("cooldown", phone), now + RESEND_COOLDOWN, RESEND_COOLDOWN):
        until = cache.get(_key("cooldown", phone)) or now + RESEND_COOLDOWN
        raise Throttled(
            wait=max(1, int(until - now)),
            detail="لطفاً کمی صبر کنید و دوباره تلاش کنید.",
        )

    cache.add(_key("hour", phone), 0, 3600)
    if _incr(_key("hour", phone), 3600) > MAX_SENDS_PER_HOUR:
        raise Throttled(wait=3600, detail="تعداد درخواست کد بیش از حد مجاز است.")

    code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
    cache.set(_key("code", phone), _hash(phone, code), OTP_TTL)
    cache.set(_key("attempts", phone), 0, OTP_TTL)
    return code


def verify_otp(phone: str, code: str) -> None:
    """اگر کد درست باشد چیزی برنمی‌گرداند، وگرنه ValidationError می‌دهد."""
    stored = cache.get(_key("code", phone))
    if stored is None:
        raise ValidationError({"code": "کد منقضی شده یا درخواست داده نشده است."})

    attempts = _incr(_key("attempts", phone), OTP_TTL)
    if attempts > MAX_VERIFY_ATTEMPTS:
        cache.delete_many([_key("code", phone), _key("attempts", phone)])
        raise ValidationError(
            {"code": "تعداد تلاش‌ها بیش از حد مجاز است. کد جدید بگیرید."}
        )

    if not hmac.compare_digest(stored, _hash(phone, code)):
        raise ValidationError({"code": "کد وارد شده اشتباه است."})

    cache.delete_many([_key("code", phone), _key("attempts", phone)])