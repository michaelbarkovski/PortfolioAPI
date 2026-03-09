from rest_framework import serializers
from .models import Asset, Price, Portfolio, Holding
from decimal import Decimal
from rest_framework import serializers
from django.contrib.auth.models import User


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ["id", "identifier", "name"]

class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Price
        fields = ["id", "asset", "date", "closing_price"]

class HoldingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Holding
        fields = ["id", "portfolio", "asset", "weight"]

    def validate(self, data): #all weights should sum to 1 per portfolio 
        request = self.context.get("request")
        portfolio = data.get("portfolio") or getattr(self.instance, "portfolio", None)
        weight = data.get("weight") if "weight" in data else getattr(self.instance, "weight", None)

        if portfolio is None or weight is None:
            return data

        if request and portfolio.user != request.user: #ownership check
            raise serializers.ValidationError("You can only add Holdings to your own portfolios") 
        
        #weight sum check
        existing = Holding.objects.filter(portfolio=portfolio)
        if self.instance is not None:
            existing = existing.exclude(id=self.instance.id)

        total = Decimal("0")
        for h in existing:
            total += h.weight
        total += weight

        if total > Decimal("1.00000"):
            raise serializers.ValidationError("Total portfolio weight cannot exceed 1.0")

        return data

class PortfolioSerializer(serializers.ModelSerializer):
    user = serializers.ReadOnlyField(source="user.username")

    class Meta:
        model = Portfolio
        fields = ["id", "user", "name", "date_created"]


class RegisterSerializer(serializers.ModelSerializer): #serializer for user registration
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "password_confirm"]

    def validate(self, attrs): #checks that both passwords match
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        if User.objects.filter(username=attrs["username"]).exists():
            raise serializers.ValidationError({"username": "This username is already taken."})

        email = attrs.get("email")
        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "This email is already in use."})

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        user = User.objects.create_user( #proper password hashing 
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        return user