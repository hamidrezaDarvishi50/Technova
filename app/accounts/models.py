from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

from django.core.validators import RegexValidator
from django.db import models
from .utils import normalize_phone


phone_validator = RegexValidator(r"^9\d{9}$", "شماره موبایل معتبر نیست.")

class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("username الزامی است.")
        extra_fields.setdefault("is_staff", True)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        STORAGE = "storage", "Storage"
        FINANCE = "finance", "Finance"
        SALES = "sales", "Sales"

    username = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=10, unique=True,  null=True, blank=True, validators=[phone_validator])
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=100, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALES)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # برای دسترسی به django admin
    is_superuser = models.BooleanField(default=False)
    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = normalize_phone(self.phone) if self.phone else None
        super().save(*args, **kwargs)


class UserAccess(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="access")

    dashboard = models.BooleanField(default=False)
    orderlist = models.BooleanField(default=False)
    products = models.BooleanField(default=False)
    users = models.BooleanField(default=False)
    lead = models.BooleanField(default=False)
    customer = models.BooleanField(default=False)
    tasks = models.BooleanField(default=False)

    #{"view": true, "create": false, "edit": false, "delete": false}
    dashboard_details = models.JSONField(default=dict, blank=True)
    orderlist_details = models.JSONField(default=dict, blank=True)
    products_details = models.JSONField(default=dict, blank=True)
    users_details = models.JSONField(default=dict, blank=True)
    lead_details = models.JSONField(default=dict, blank=True)
    customer_details = models.JSONField(default=dict, blank=True)
    tasks_details = models.JSONField(default=dict, blank=True)


class Customer(models.Model):
    phone = models.CharField(max_length=10, unique=True, validators=[phone_validator])
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.phone

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = normalize_phone(self.phone)
        super().save(*args, **kwargs)


class Address(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    title = models.CharField(max_length=50, blank=True)  # مثلا خانه / محل کار
    address = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)