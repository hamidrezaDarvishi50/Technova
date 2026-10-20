from rest_framework.permissions import BasePermission

from .models import Customer, User


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, Customer)


class IsStaffUser(BasePermission):
    """هر کارمند فعال پنل (User)."""

    def has_permission(self, request, view):
        return isinstance(request.user, User) and request.user.is_active


class IsAdminRole(BasePermission):
    """فقط کاربرانی که role = admin دارند."""

    def has_permission(self, request, view):
        user = request.user
        return (
            isinstance(user, User) and user.is_active and user.role == User.Role.ADMIN
        )