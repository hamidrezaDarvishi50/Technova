import re
from django.core.exceptions import ValidationError

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_phone(value) -> str:
    """09123456789 / 989123456789 / 9123456789 / 00989123456789 -> 9123456789"""
    digits = re.sub(r"\D", "", str(value).translate(_DIGITS))

    if len(digits) == 14 and digits.startswith("0098"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("98"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if not re.fullmatch(r"9\d{9}", digits):
        raise ValidationError("شماره موبایل معتبر نیست.")
    return digits