from django.db import models

# Create your models here.
from django.core.validators import MaxValueValidator
from django.utils.text import slugify

def unique_slugify(instance, value, max_length=150):
    """از value یک slug یکتا می‌سازد (فارسی هم پشتیبانی می‌شود)."""
    base = slugify(value, allow_unicode=True)[: max_length - 10]
    base = base or instance.__class__.__name__.lower()
    model = instance.__class__
    slug, n = base, 2
    while model.objects.exclude(pk=instance.pk).filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug

class Category(models.Model):
    title = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=150, unique=True, allow_unicode=True, blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)   
        super().save(*args, **kwargs)


class Product(models.Model):
    category = models.ForeignKey("Category", on_delete=models.PROTECT, related_name="products",)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=150, unique=True, allow_unicode=True, blank=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    price = models.PositiveIntegerField()
    stock = models.PositiveIntegerField(default=0)
    description = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    discount = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(99)])
    sold_count = models.PositiveIntegerField(default=0)

    @property
    def final_price(self):
        return self.price * (100 - self.discount) // 100

    @property
    def has_discount(self):
        return self.discount > 0
    
    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title)
        super().save(*args, **kwargs)