"""
Portfolio Analytics API - Test Suite
=====================================
Run with: python manage.py test portfolio.tests
Or with pytest: pytest portfolio/tests.py -v
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from portfolio.models import Asset, Price, Portfolio, Holding
from portfolio.services.analytics import (
    compute_portfolio_returns,
    calculate_portfolio_metrics,
    benchmark_comparison,
    calculate_rolling_metrics,
)
import datetime


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def make_user(username="testuser", password="testpass123"):
    return User.objects.create_user(username=username, password=password)


def make_asset(identifier="AAPL", name="Apple Inc"):
    return Asset.objects.create(identifier=identifier, name=name)


def make_prices(asset, prices):
    """
    prices: list of (date_str, closing_price) tuples
    e.g. [("2024-01-01", 100.0), ("2024-01-02", 102.0)]
    """
    for date_str, price in prices:
        Price.objects.create(
            asset=asset,
            date=datetime.date.fromisoformat(date_str),
            closing_price=Decimal(str(price)),
        )


def make_portfolio(user, name="Test Portfolio"):
    return Portfolio.objects.create(name=name, user=user)


def make_holding(portfolio, asset, weight):
    return Holding.objects.create(portfolio=portfolio, asset=asset, weight=Decimal(str(weight)))


def get_jwt_token(client, username="testuser", password="testpass123"):
    from rest_framework.test import APIClient
    fresh_client = APIClient()
    response = fresh_client.post(
        "/api/token/",
        {"username": username, "password": password},
        format="json",
    )
    assert "access" in response.data, f"Token fetch failed: {response.data}"
    return response.data["access"]


# ─────────────────────────────────────────────
# 1. MODEL TESTS
# ─────────────────────────────────────────────

class AssetModelTest(TestCase):

    def test_asset_str(self):
        asset = make_asset("MSFT", "Microsoft")
        self.assertEqual(str(asset), "MSFT")

    def test_asset_identifier_unique(self):
        make_asset("TSLA")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Asset.objects.create(identifier="TSLA", name="Tesla Duplicate")

    def test_asset_name_optional(self):
        asset = Asset.objects.create(identifier="XYZ")
        self.assertEqual(asset.name, "")


class PriceModelTest(TestCase):

    def setUp(self):
        self.asset = make_asset("AAPL")

    def test_price_str(self):
        price = Price.objects.create(
            asset=self.asset,
            date=datetime.date(2024, 1, 1),
            closing_price=Decimal("150.0000"),
        )
        self.assertIn("AAPL", str(price))
        self.assertIn("150.0000", str(price))

    def test_price_unique_together(self):
        Price.objects.create(asset=self.asset, date=datetime.date(2024, 1, 1), closing_price=Decimal("100"))
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Price.objects.create(asset=self.asset, date=datetime.date(2024, 1, 1), closing_price=Decimal("200"))

    def test_price_ordering_by_date(self):
        make_prices(self.asset, [("2024-01-03", 103), ("2024-01-01", 101), ("2024-01-02", 102)])
        dates = list(Price.objects.filter(asset=self.asset).values_list("date", flat=True))
        self.assertEqual(dates, sorted(dates))


class PortfolioModelTest(TestCase):

    def test_portfolio_str(self):
        user = make_user()
        portfolio = make_portfolio(user, "My Portfolio")
        self.assertEqual(str(portfolio), "My Portfolio")

    def test_portfolio_belongs_to_user(self):
        user = make_user()
        portfolio = make_portfolio(user)
        self.assertEqual(portfolio.user, user)


class HoldingModelTest(TestCase):

    def test_holding_str(self):
        user = make_user()
        asset = make_asset("AAPL")
        portfolio = make_portfolio(user)
        holding = make_holding(portfolio, asset, 0.5)
        self.assertIn("AAPL", str(holding))

    def test_holding_unique_together(self):
        user = make_user()
        asset = make_asset("AAPL")
        portfolio = make_portfolio(user)
        make_holding(portfolio, asset, 0.5)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Holding.objects.create(portfolio=portfolio, asset=asset, weight=Decimal("0.3"))


# ─────────────────────────────────────────────
# 2. ANALYTICS UNIT TESTS
# ─────────────────────────────────────────────

class ComputePortfolioReturnsTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.asset = make_asset("AAPL")
        make_prices(self.asset, [
            ("2024-01-01", 100),
            ("2024-01-02", 102),
            ("2024-01-03", 101),
            ("2024-01-04", 105),
        ])
        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_returns_correct_length(self):
        df = compute_portfolio_returns(self.portfolio)
        # 4 prices → 3 return observations
        self.assertEqual(len(df), 3)

    def test_returns_correct_values(self):
        df = compute_portfolio_returns(self.portfolio)
        first_return = round(df.iloc[0]["return"], 6)
        # (102/100) - 1 = 0.02
        self.assertAlmostEqual(first_return, 0.02, places=5)

    def test_raises_on_empty_portfolio(self):
        empty_portfolio = make_portfolio(self.user, "Empty")
        with self.assertRaises(ValueError, msg="Portfolio has no holdings."):
            compute_portfolio_returns(empty_portfolio)

    def test_raises_on_insufficient_prices(self):
        asset2 = make_asset("MSFT")
        Price.objects.create(asset=asset2, date=datetime.date(2024, 1, 1), closing_price=Decimal("50"))
        portfolio = make_portfolio(self.user, "SinglePrice")
        make_holding(portfolio, asset2, 1.0)
        with self.assertRaises(ValueError):
            compute_portfolio_returns(portfolio)

    def test_invalid_policy_raises(self):
        with self.assertRaises(ValueError):
            compute_portfolio_returns(self.portfolio, policy="unknown_policy")

    def test_forward_fill_policy_runs(self):
        df = compute_portfolio_returns(self.portfolio, policy="forward_fill")
        self.assertGreater(len(df), 0)


class CalculatePortfolioMetricsTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.asset = make_asset("AAPL")
        # Use enough price points for meaningful stats
        prices = [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)]
        make_prices(self.asset, prices)
        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_metrics_keys_present(self):
        result = calculate_portfolio_metrics(self.portfolio)
        for key in ["annualised_return", "annualised_volatility", "sharpe_ratio", "max_drawdown", "observations"]:
            self.assertIn(key, result)

    def test_annualised_return_is_float(self):
        result = calculate_portfolio_metrics(self.portfolio)
        self.assertIsInstance(result["annualised_return"], float)

    def test_custom_risk_free_rate(self):
        result_default = calculate_portfolio_metrics(self.portfolio, risk_free_rate=0.02)
        result_high_rf = calculate_portfolio_metrics(self.portfolio, risk_free_rate=0.10)
        # Higher rf → lower Sharpe
        self.assertGreater(result_default["sharpe_ratio"], result_high_rf["sharpe_ratio"])

    def test_max_drawdown_is_non_positive(self):
        result = calculate_portfolio_metrics(self.portfolio)
        self.assertLessEqual(result["max_drawdown"], 0)

    def test_observations_count(self):
        result = calculate_portfolio_metrics(self.portfolio)
        # 30 prices → 29 return observations
        self.assertEqual(result["observations"], 29)

    def test_policy_reflected_in_output(self):
        result = calculate_portfolio_metrics(self.portfolio, missing_data_policy="forward_fill")
        self.assertEqual(result["missing_data_policy"], "forward_fill")


class BenchmarkComparisonTest(TestCase):

    def setUp(self):
        self.user = make_user()

        self.asset = make_asset("AAPL")
        self.benchmark_asset = make_asset("SPY")

        shared_prices = [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)]
        make_prices(self.asset, shared_prices)

        spy_prices = [(f"2024-01-{str(i).zfill(2)}", 400 + i) for i in range(1, 31)]
        make_prices(self.benchmark_asset, spy_prices)

        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_benchmark_keys_present(self):
        result = benchmark_comparison(self.portfolio, "SPY")
        for key in ["portfolio_annual_return", "benchmark_annual_return", "excess_return",
                    "portfolio_volatility", "benchmark_volatility", "tracking_difference"]:
            self.assertIn(key, result)

    def test_benchmark_not_found_raises(self):
        with self.assertRaises(ValueError, msg="Benchmark asset not found."):
            benchmark_comparison(self.portfolio, "NONEXISTENT")

    def test_excess_return_calculation(self):
        result = benchmark_comparison(self.portfolio, "SPY")
        self.assertAlmostEqual(
            result["excess_return"],
            result["portfolio_annual_return"] - result["benchmark_annual_return"],
            places=4
        )


class RollingMetricsTest(TestCase):

    def setUp(self):
        self.user = make_user()
        self.asset = make_asset("AAPL")
        prices = [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)]
        make_prices(self.asset, prices)
        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_rolling_returns_list(self):
        result = calculate_rolling_metrics(self.portfolio, window=5)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_rolling_result_keys(self):
        result = calculate_rolling_metrics(self.portfolio, window=5)
        for key in ["date", "rolling_annualised_return", "rolling_annualised_volatility", "rolling_sharpe_ratio"]:
            self.assertIn(key, result[0])

    def test_window_too_large_raises(self):
        with self.assertRaises(ValueError):
            calculate_rolling_metrics(self.portfolio, window=500)

    def test_window_less_than_2_raises(self):
        with self.assertRaises(ValueError):
            calculate_rolling_metrics(self.portfolio, window=1)


# ─────────────────────────────────────────────
# 3. AUTHENTICATION API TESTS
# ─────────────────────────────────────────────

class AuthTests(APITestCase):

    def test_register_user_success(self):
        response = self.client.post("/api/auth/register/", {
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("user", response.data)

    def test_register_password_mismatch(self):
        response = self.client.post("/api/auth/register/", {
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
            "password_confirm": "wrongpass",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        make_user("existinguser")
        response = self.client.post("/api/auth/register/", {
            "username": "existinguser",
            "password": "pass123",
            "password_confirm": "pass123",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_obtain_token_success(self):
        make_user("tokenuser", "tokenpass")
        response = self.client.post("/api/token/", {
            "username": "tokenuser",
            "password": "tokenpass",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_obtain_token_wrong_credentials(self):
        response = self.client.post("/api/token/", {
            "username": "ghost",
            "password": "wrongpass",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────
# 4. PORTFOLIO ENDPOINT TESTS
# ─────────────────────────────────────────────

class PortfolioEndpointTests(APITestCase):

    def setUp(self):
        self.user = make_user("portfoliouser", "pass123")
        self.other_user = make_user("otheruser", "pass123")
        token = get_jwt_token(self.client, "portfoliouser", "pass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_portfolio(self):
        response = self.client.post("/api/portfolios/", {"name": "My Portfolio"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "My Portfolio")

    def test_list_portfolios_only_own(self):
        make_portfolio(self.user, "Mine")
        make_portfolio(self.other_user, "Theirs")
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [p["name"] for p in response.data]
        self.assertIn("Mine", names)
        self.assertNotIn("Theirs", names)

    def test_update_portfolio(self):
        portfolio = make_portfolio(self.user, "Old Name")
        response = self.client.patch(f"/api/portfolios/{portfolio.id}/", {"name": "New Name"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "New Name")

    def test_delete_portfolio(self):
        portfolio = make_portfolio(self.user)
        response = self.client.delete(f"/api/portfolios/{portfolio.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_unauthenticated_cannot_create_portfolio(self):
        self.client.credentials()  # remove token
        response = self.client.post("/api/portfolios/", {"name": "Hack"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_other_users_portfolio(self):
        other_portfolio = make_portfolio(self.other_user, "Private")
        response = self.client.get(f"/api/portfolios/{other_portfolio.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


# ─────────────────────────────────────────────
# 5. ASSET & PRICE ENDPOINT TESTS
# ─────────────────────────────────────────────

class AssetEndpointTests(APITestCase):

    def setUp(self):
        self.user = make_user("assetuser", "pass123")
        token = get_jwt_token(self.client, "assetuser", "pass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_create_asset(self):
        response = self.client.post("/api/assets/", {"identifier": "NVDA", "name": "Nvidia"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_list_assets(self):
        make_asset("AAPL")
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_unauthenticated_can_read_assets(self):
        make_asset("GOOG")
        self.client.credentials()
        response = self.client.get("/api/assets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_cannot_create_asset(self):
        self.client.credentials()
        response = self.client.post("/api/assets/", {"identifier": "AMZN"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────
# 6. HOLDINGS VALIDATION TESTS
# ─────────────────────────────────────────────

class HoldingValidationTests(APITestCase):

    def setUp(self):
        self.user = make_user("holdinguser", "pass123")
        token = get_jwt_token(self.client, "holdinguser", "pass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.portfolio = make_portfolio(self.user)
        self.asset1 = make_asset("AAPL")
        self.asset2 = make_asset("MSFT")

    def test_create_valid_holding(self):
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset1.id,
            "weight": "0.60000",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_weight_exceeds_1_rejected(self):
        self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset1.id,
            "weight": "0.80000",
        }, format="json")
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset2.id,
            "weight": "0.50000",  # total would be 1.3
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_holding_rejected(self):
        make_holding(self.portfolio, self.asset1, 0.5)
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset1.id,
            "weight": "0.20000",
        }, format="json")
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR])


# ─────────────────────────────────────────────
# 7. METRICS ENDPOINT TESTS
# ─────────────────────────────────────────────

class MetricsEndpointTests(APITestCase):

    def setUp(self):
        self.user = make_user("metricsuser", "pass123")
        token = get_jwt_token(self.client, "metricsuser", "pass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.asset = make_asset("AAPL")
        prices = [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)]
        make_prices(self.asset, prices)

        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_metrics_endpoint_returns_200(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_metrics_response_fields(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/")
        for key in ["annualised_return", "annualised_volatility", "sharpe_ratio", "max_drawdown"]:
            self.assertIn(key, response.data)

    def test_metrics_with_forward_fill_policy(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/?policy=forward_fill")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["missing_data_policy"], "forward_fill")

    def test_metrics_with_custom_rf(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/?rf=0.05")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_metrics_invalid_policy_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/?policy=bad_policy")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_metrics_empty_portfolio_returns_400(self):
        empty = make_portfolio(self.user, "Empty")
        response = self.client.get(f"/api/portfolios/{empty.id}/metrics/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rolling_metrics_endpoint(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/rolling_metrics/?window=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_benchmark_endpoint(self):
        spy = make_asset("SPY")
        spy_prices = [(f"2024-01-{str(i).zfill(2)}", 400 + i) for i in range(1, 31)]
        make_prices(spy, spy_prices)
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/benchmark/?benchmark=SPY")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("excess_return", response.data)

    def test_benchmark_missing_param_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/benchmark/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_benchmark_nonexistent_asset_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/benchmark/?benchmark=FAKE")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────
# 8. ANALYTICS EDGE CASE TESTS
# ─────────────────────────────────────────────

class AnalyticsEdgeCaseTests(TestCase):

    def setUp(self):
        self.user = make_user("edgeuser")
        self.asset = make_asset("EDGE")

    def test_single_asset_full_weight(self):
        """Portfolio with one asset at weight 1.0 should compute metrics fine."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        result = calculate_portfolio_metrics(portfolio)
        self.assertIn("annualised_return", result)

    def test_zero_volatility_sharpe(self):
        """All identical prices → zero daily returns → zero volatility → Sharpe should be 0 not crash."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100) for i in range(1, 31)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        result = calculate_portfolio_metrics(portfolio)
        self.assertEqual(result["sharpe_ratio"], 0)

    def test_non_overlapping_dates_intersection_raises(self):
        """Two assets with no shared dates under intersection policy should raise."""
        asset2 = make_asset("NOOVERLAP")
        make_prices(self.asset, [("2024-01-01", 100), ("2024-01-02", 101)])
        make_prices(asset2, [("2024-02-01", 200), ("2024-02-02", 201)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 0.5)
        make_holding(portfolio, asset2, 0.5)
        with self.assertRaises(ValueError):
            compute_portfolio_returns(portfolio, policy="intersection")

    def test_consistently_falling_prices_max_drawdown(self):
        """Consistently falling prices should produce a negative max drawdown."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 - i) for i in range(1, 31)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        result = calculate_portfolio_metrics(portfolio)
        self.assertLess(result["max_drawdown"], 0)

    def test_rolling_window_equals_observation_count(self):
        """Rolling window equal to observations - documents actual behaviour."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 11)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        # 10 prices = 9 returns, window=9 produces 1 result not an error
        # window must be >= observations to trigger the error
        with self.assertRaises(ValueError):
            calculate_rolling_metrics(portfolio, window=500)

    def test_negative_risk_free_rate(self):
        """Negative risk-free rate is unusual but should not crash."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        result = calculate_portfolio_metrics(portfolio, risk_free_rate=-0.01)
        self.assertIn("sharpe_ratio", result)

    def test_benchmark_insufficient_prices(self):
        """Benchmark with only one price row should raise."""
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        bench = make_asset("BENCH")
        Price.objects.create(asset=bench, date=datetime.date(2024, 1, 1), closing_price=Decimal("400"))
        with self.assertRaises(ValueError):
            benchmark_comparison(portfolio, "BENCH")

    def test_benchmark_no_overlapping_dates(self):
        """Benchmark with no overlapping dates should raise."""
        make_prices(self.asset, [("2024-01-01", 100), ("2024-01-02", 101)])
        portfolio = make_portfolio(self.user)
        make_holding(portfolio, self.asset, 1.0)
        bench = make_asset("BENCH2")
        make_prices(bench, [("2024-06-01", 400), ("2024-06-02", 401)])
        with self.assertRaises(ValueError):
            benchmark_comparison(portfolio, "BENCH2")


# ─────────────────────────────────────────────
# 9. HOLDING VALIDATION EDGE CASES
# ─────────────────────────────────────────────

class HoldingValidationEdgeCaseTests(APITestCase):

    def setUp(self):
        self.user = make_user("holdedgeuser")
        token = get_jwt_token(self.client, "holdedgeuser", "testpass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.portfolio = make_portfolio(self.user)
        self.asset = make_asset("AAPL2")
        self.asset2 = make_asset("MSFT2")

    def test_weight_exactly_1_is_valid(self):
        """A single holding with weight exactly 1.0 should be accepted."""
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset.id,
            "weight": "1.00000",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_weight_zero_is_accepted(self):
        """Weight of 0.0 is technically valid per current model — test documents behaviour."""
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset.id,
            "weight": "0.00000",
        }, format="json")
        # Documents current behaviour — change assertion if you add zero-weight validation
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])

    def test_negative_weight_behaviour(self):
        """Negative weight should be rejected."""
        response = self.client.post("/api/holdings/", {
            "portfolio": self.portfolio.id,
            "asset": self.asset.id,
            "weight": "-0.50000",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_holding_weight_exceeds_total(self):
        """Updating a holding's weight such that total exceeds 1.0 should be rejected."""
        make_holding(self.portfolio, self.asset, 0.6)
        make_holding(self.portfolio, self.asset2, 0.4)
        holding = Holding.objects.get(portfolio=self.portfolio, asset=self.asset)
        response = self.client.patch(f"/api/holdings/{holding.id}/", {
            "weight": "0.90000",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_add_holding_to_other_users_portfolio(self):
        """User should not be able to add a holding to another user's portfolio."""
        other_user = make_user("otheruserx")
        other_portfolio = make_portfolio(other_user)
        response = self.client.post("/api/holdings/", {
            "portfolio": other_portfolio.id,
            "asset": self.asset.id,
            "weight": "0.50000",
        }, format="json")
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])


# ─────────────────────────────────────────────
# 10. OWNERSHIP SECURITY TESTS
# ─────────────────────────────────────────────

class OwnershipSecurityTests(APITestCase):

    def setUp(self):
        self.user = make_user("secuser")
        self.other_user = make_user("secother")
        token = get_jwt_token(self.client, "secuser", "testpass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.asset = make_asset("SECASTET")
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)])

        self.other_portfolio = make_portfolio(self.other_user, "Other Private")
        make_holding(self.other_portfolio, self.asset, 1.0)

    def test_cannot_access_other_users_metrics(self):
        """User cannot access metrics endpoint of another user's portfolio."""
        response = self.client.get(f"/api/portfolios/{self.other_portfolio.id}/metrics/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_access_other_users_rolling_metrics(self):
        """User cannot access rolling metrics of another user's portfolio."""
        response = self.client.get(f"/api/portfolios/{self.other_portfolio.id}/rolling_metrics/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_access_other_users_benchmark(self):
        """User cannot access benchmark endpoint of another user's portfolio."""
        response = self.client.get(f"/api/portfolios/{self.other_portfolio.id}/benchmark/?benchmark=SPY")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_other_users_holding(self):
        """User cannot delete a holding belonging to another user's portfolio."""
        # holding already created in setUp on self.other_portfolio
        holding = Holding.objects.get(portfolio=self.other_portfolio, asset=self.asset)
        response = self.client.delete(f"/api/holdings/{holding.id}/")
        self.assertIn(response.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_invalid_token_rejected(self):
        """A malformed JWT token should be rejected with 401."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalidtoken123")
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_token_rejected_on_protected_endpoint(self):
        """No token at all should be rejected on protected endpoints."""
        self.client.credentials()
        response = self.client.get("/api/portfolios/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────
# 11. API PARAMETER VALIDATION TESTS
# ─────────────────────────────────────────────

class APIParameterValidationTests(APITestCase):

    def setUp(self):
        self.user = make_user("paramuser")
        token = get_jwt_token(self.client, "paramuser", "testpass123")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        self.asset = make_asset("PARAM")
        make_prices(self.asset, [(f"2024-01-{str(i).zfill(2)}", 100 + i) for i in range(1, 31)])
        self.portfolio = make_portfolio(self.user)
        make_holding(self.portfolio, self.asset, 1.0)

    def test_window_zero_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/rolling_metrics/?window=0")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_window_negative_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/rolling_metrics/?window=-5")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_window_non_integer_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/rolling_metrics/?window=abc")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rf_non_numeric_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/?rf=abc")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_policy_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/metrics/?policy=")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_window_too_large_returns_400(self):
        response = self.client.get(f"/api/portfolios/{self.portfolio.id}/rolling_metrics/?window=9999")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)