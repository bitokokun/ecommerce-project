from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, Address
from .countries import COUNTRY_LOOKUP


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "role", "phone_number")


    def validate_role(self, value):
        # Anyone can pick customer or seller for themselves, but "admin" can
        # only be given from the Django admin. Before this, a signup request
        # could simply claim role="admin".
        if value not in (User.Role.CUSTOMER, User.Role.SELLER):
            raise serializers.ValidationError("Choose customer or seller.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "phone_number", "date_joined")
        read_only_fields = ("id", "date_joined")

    def validate_role(self, value):
        # Anyone can pick customer or seller for themselves, but "admin" can
        # only be given from the Django admin. Before this, a signup request
        # could simply claim role="admin".
        if value not in (User.Role.CUSTOMER, User.Role.SELLER):
            raise serializers.ValidationError("Choose customer or seller.")
        return value


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = "__all__"
        read_only_fields = ("user",)

    def validate_country(self, value):
        # must be one of the countries in the dropdown (case doesn't matter,
        # and it's saved with the proper spelling)
        match = COUNTRY_LOOKUP.get(value.strip().lower())
        if not match:
            raise serializers.ValidationError("Choose a country from the list.")
        return match
