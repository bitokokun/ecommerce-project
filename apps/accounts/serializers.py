from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
import re

from .models import User, Address, SellerProfile
from .countries import COUNTRY_LOOKUP

PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{6,20}$")


def validate_phone(value):
    value = (value or "").strip()
    if value and not PHONE_RE.match(value):
        raise serializers.ValidationError("Enter a valid phone number.")
    return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "password", "role", "phone_number")

    def validate_email(self, value):
        if value and User.objects.filter(email__iexact=value.strip()).exists():
            raise serializers.ValidationError("That email is already in use.")
        return value.strip()

    def validate_phone_number(self, value):
        return validate_phone(value)


    def validate_password(self, value):
        prospective_user = User(**{
            key: self.initial_data.get(key)
            for key in ("username", "email")
            if self.initial_data.get(key) is not None
        })
        validate_password(value, user=prospective_user)
        return value

    def validate_role(self, value):
        if value not in (User.Role.CUSTOMER, User.Role.SELLER):
            raise serializers.ValidationError("Choose customer or seller.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    has_store = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "role",
            "phone_number", "date_joined", "avatar_url", "has_store",
            "marketing_emails", "order_update_emails", "is_staff",
        )
        read_only_fields = ("id", "date_joined", "role", "is_staff")

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        url = obj.avatar.url
        request = self.context.get("request")
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    def get_has_store(self, obj):
        return SellerProfile.objects.filter(user_id=obj.pk).exists()

    def validate_username(self, value):
        value = value.strip()
        qs = User.objects.filter(username__iexact=value).exclude(pk=self.instance.pk if self.instance else None)
        if qs.exists():
            raise serializers.ValidationError("That username is taken.")
        return value

    def validate_email(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Email is required.")
        qs = User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk if self.instance else None)
        if qs.exists():
            raise serializers.ValidationError("That email is already in use.")
        return value

    def validate_phone_number(self, value):
        return validate_phone(value)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        validate_password(attrs["new_password"], user=self.context["request"].user)
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": "Choose a password you have not used just now."}
            )
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    confirmation = serializers.CharField(write_only=True)

    def validate_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Password is incorrect.")
        return value

    def validate_confirmation(self, value):
        if value.strip() != self.context["request"].user.username:
            raise serializers.ValidationError("Type your username to confirm.")
        return value


class SellerProfileSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = SellerProfile
        fields = (
            "store_name", "description", "logo_url", "contact_email",
            "shipping_note", "return_policy", "created_at",
        )
        read_only_fields = ("created_at",)

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        url = obj.logo.url
        request = self.context.get("request")
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    def validate_store_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Store name is too short.")
        qs = SellerProfile.objects.filter(store_name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("That store name is taken.")
        return value


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = "__all__"
        read_only_fields = ("user",)

    def validate_country(self, value):
        match = COUNTRY_LOOKUP.get(value.strip().lower())
        if not match:
            raise serializers.ValidationError("Choose a country from the list.")
        return match
