from django.shortcuts import render
from rest_framework import viewsets
from .models import Asset, Price, Portfolio, Holding
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status, generics, permissions
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from .services.analytics import calculate_portfolio_metrics
from .serializers import (
    AssetSerializer,
    PriceSerializer,
    PortfolioSerializer,
    HoldingSerializer,
    RegisterSerializer,
)

class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.all().order_by("identifier")
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class PriceViewSet(viewsets.ModelViewSet):
    queryset = Price.objects.all().select_related("asset").order_by("asset__identifier", "date")
    serializer_class = PriceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class PortfolioViewSet(viewsets.ModelViewSet):
    #queryset = Portfolio.objects.all().order_by("-date_created")
    serializer_class = PortfolioSerializer
    permission_classes = [IsAuthenticated]

    #restrict portfoloioviewset to the logged in user 
    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user).order_by("-date_created")
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        portfolio = self.get_object()
        #read query paremters
        missing_data_policy = request.query_params.get("policy", "intersection") 
        risk_free_rate = float(request.query_params.get("rf", 0.02))
        try:
            results = calculate_portfolio_metrics(portfolio, missing_data_policy, risk_free_rate=risk_free_rate,)
            return Response(results, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

class HoldingViewSet(viewsets.ModelViewSet):
    #queryset = Holding.objects.all().select_related("portfolio", "asset").order_by("portfolio__name", "asset__identifier")
    serializer_class = HoldingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Holding.objects.filter(portfolio__user=self.request.user) #updated so that users only access their own holdings 

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "message": "User registered successfully.",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                },
            },
            status=status.HTTP_201_CREATED,
        )

