from rest_framework import serializers
from .models import Category, Product

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "title", "image", "slug" ,"created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductListSerializer(serializers.ModelSerializer):
    """نمایش خلاصه‌ی محصول در لیست‌ها (محصولات، تخفیف‌ها، علاقه‌مندی‌ها، دسته‌بندی)."""

    category = serializers.CharField(source="category.title", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    final_price = serializers.IntegerField(read_only=True)
    has_discount = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "image",
            "category",
            "category_slug",
            "price",
            "discount",
            "final_price",
            "has_discount",
            "stock",
        ]
        read_only_fields = fields


class ProductDetailSerializer(ProductListSerializer):
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductWriteSerializer(serializers.ModelSerializer):
    """ساخت و ویرایش محصول (فقط ادمین)."""
    
    category = serializers.SlugRelatedField(
        slug_field="title",
        queryset=Category.objects.all(),
        error_messages={"does_not_exist": "دسته‌بندی‌ای با عنوان «{value}» وجود ندارد."},
    )
    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "name",
            "slug",
            "image",
            "price",
            "stock",
            "discount",
            "description",
        ]
        read_only_fields = ["id"]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("قیمت باید بیشتر از صفر باشد.")
        return value

    def validate_description(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("description باید یک آبجکت JSON باشد.")
        return value

    def update(self, instance, validated_data):
        # اگر تصویر عوض شد، فایل قدیمی روی دیسک نماند
        old_name = instance.image.name if "image" in validated_data and instance.image else None
        instance = super().update(instance, validated_data)
        new_name = instance.image.name if instance.image else None
        if old_name and old_name != new_name:
            instance.image.storage.delete(old_name)
        return instance


class ProductFilterSerializer(serializers.Serializer):
    """query params لیست محصولات."""

    SORT_CHOICES = ["newest", "most_expensive", "cheapest", "best_selling"]

    sort = serializers.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        default="newest",
        help_text="newest=جدیدترین، most_expensive=گران‌ترین، cheapest=ارزان‌ترین، best_selling=پرفروش‌ترین",
    )
    min_price = serializers.IntegerField(
        required=False, min_value=0, help_text="حداقل قیمت نهایی (بعد از تخفیف)"
    )
    max_price = serializers.IntegerField(
        required=False, min_value=0, help_text="حداکثر قیمت نهایی (بعد از تخفیف)"
    )
    category = serializers.SlugField(
        required=False, allow_unicode=True, help_text="title دسته‌بندی"
    )

    def validate(self, attrs):
        low, high = attrs.get("min_price"), attrs.get("max_price")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError("min_price نباید بزرگ‌تر از max_price باشد.")
        return attrs


class FavoriteAddSerializer(serializers.Serializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source="product")
    
    product = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Product.objects.all(),
        error_messages={"does_not_exist": "محصولی با این slug وجود ندارد."},
    )