import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


def _send_sms(receiver: str, text: str) -> None:
    """
    TODO: اتصال به پنل پیامک (کاوه‌نگار، ملی‌پیامک، ...).
    receiver با فرمت 09123456789 است.
    """
    raise NotImplementedError("SMS provider is not configured.")


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_otp_sms(phone: str, code: str) -> None:
    receiver = f"0{phone}"
    text = f"کد ورود به تکنوا: {code}"

    if settings.DEBUG:
        # در محیط توسعه پیامک واقعی نمی‌فرستیم
        logger.warning("OTP for %s: %s", receiver, code)
        return

    _send_sms(receiver, text)