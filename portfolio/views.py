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
from portfolio.services.analytics import (
    benchmark_comparison,
    calculate_portfolio_metrics,
    calculate_rolling_metrics,

)
from drf_spectacular.utils import extend_schema, OpenApiParameter

class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.all().order_by("identifier")
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class PriceViewSet(viewsets.ModelViewSet):
    queryset = Price.objects.all().select_related("asset").order_by("asset__identifier", "date")
    serializer_class = PriceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class PortfolioViewSet(viewsets.ModelViewSet):
    queryset = Portfolio.objects.all().order_by("-date_created")
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

    #benchmark ednpoint
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="benchmark",
                description="Benchmark asset identifier, for example SPY",
                required=True,
                type=str,
            )
        ]
    )
    @action(detail=True, methods=["get"])
    def benchmark(self, request, pk=None):
        portfolio = self.get_object()

        benchmark = request.query_params.get("benchmark")

        if not benchmark:
            return Response(
                {"error": "Benchmark identifier required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = benchmark_comparison(portfolio, benchmark)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)
    
    #rolling metrics endpoint 
    @extend_schema(
    parameters=[
        OpenApiParameter(
            name="window",
            description="Rolling window size in trading days, for example 30",
            required=False,
            type=int,
        ),
        OpenApiParameter(
            name="policy",
            description="Missing data policy: intersection or forward_fill",
            required=False,
            type=str,
        ),
        OpenApiParameter(
            name="rf",
            description="Risk free rate used in rolling Sharpe ratio",
            required=False,
            type=float,
        ),
    ]
)

    @action(detail=True, methods=["get"])
    def rolling_metrics(self, request, pk=None):
        portfolio = self.get_object()

        window = request.query_params.get("window", 30)
        policy = request.query_params.get("policy", "intersection")
        rf = request.query_params.get("rf", 0.02)

        try:
            window = int(window)
            rf = float(rf)
        except ValueError:
            return Response(
                {"error": "window must be an integer and rf must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = calculate_rolling_metrics(
                portfolio,
                window=window,
                policy=policy,
                risk_free_rate=rf,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "portfolio_id": portfolio.id,
                "window": window,
                "risk_free_rate": rf,
                "missing_data_policy": policy,
                "results": result,
            }
        )





class HoldingViewSet(viewsets.ModelViewSet):
    queryset = Holding.objects.all().select_related("portfolio", "asset").order_by("portfolio__name", "asset__identifier")
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

