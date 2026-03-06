from rest_framework import serializers
from .models import Asset, Price, Portfolio, Holding
from decimal import Decimal
from rest_framework import serializers
from .models import Holding

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
        portfolio = data.get("portfolio") or getattr(self.instance, "portfolio", None)
        weight = data.get("weight") if "weight" in data else getattr(self.instance, "weight", None)

        if portfolio is None or weight is None:
            return data

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
    class Meta:
        model = Portfolio
        fields = ["id", "name", "date_created"]