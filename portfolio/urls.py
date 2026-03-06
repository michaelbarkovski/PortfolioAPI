from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AssetViewSet, PriceViewSet, PortfolioViewSet, HoldingViewSet

router = DefaultRouter()
router.register("assets", AssetViewSet, basename="asset")
router.register("prices", PriceViewSet, basename="price")
router.register("portfolios", PortfolioViewSet, basename="portfolio")
router.register("holdings", HoldingViewSet, basename="holding")

urlpatterns = [
    path("", include(router.urls)),
]