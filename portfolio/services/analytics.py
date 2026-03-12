from decimal import Decimal
import math
from collections import defaultdict
from portfolio.models import Holding, Asset, Price
import pandas as pd
import numpy as np

TRADING_DAYS_PER_YEAR = 252  # approx trading days per year


def compute_portfolio_returns(portfolio, policy="intersection"):
    """
    Build a date-aligned portfolio return series as a pandas DataFrame.

    Returns:
        DataFrame with columns:
        - date
        - return
    """

    holdings = portfolio.holdings.select_related("asset").all()
    if not holdings.exists():
        raise ValueError("Portfolio has no holdings.")

    # 1. Build date -> return mapping for each asset
    asset_returns = {}

    for holding in holdings:
        prices = list(
            holding.asset.prices.order_by("date").values_list("date", "closing_price")
        )

        if len(prices) < 2:
            raise ValueError(f"Not enough price data for {holding.asset.identifier}")

        returns_by_date = {}

        for i in range(1, len(prices)):
            date_today = prices[i][0]
            price_today = float(prices[i][1])
            price_yesterday = float(prices[i - 1][1])

            r = (price_today / price_yesterday) - 1
            returns_by_date[date_today] = r

        asset_returns[holding.asset.id] = returns_by_date

    # 2. Determine which dates to use
    all_date_sets = [set(asset_returns[asset_id].keys()) for asset_id in asset_returns]

    if policy == "intersection":
        valid_dates = set.intersection(*all_date_sets)
    elif policy == "forward_fill":
        valid_dates = set.union(*all_date_sets)
    else:
        raise ValueError("Invalid missing_data_policy")

    valid_dates = sorted(valid_dates)

    if not valid_dates:
        raise ValueError("No valid return dates available after alignment.")

    # 3. Build aligned portfolio return series
    portfolio_rows = []
    last_known_returns = defaultdict(lambda: 0)

    for date in valid_dates:
        rp_t = 0

        for holding in holdings:
            weight = float(holding.weight)
            asset_id = holding.asset.id
            returns_for_asset = asset_returns[asset_id]

            if date in returns_for_asset:
                r = returns_for_asset[date]
                last_known_returns[asset_id] = r
            else:
                if policy == "intersection":
                    continue
                elif policy == "forward_fill":
                    r = last_known_returns[asset_id]

            rp_t += weight * r

        portfolio_rows.append({"date": date, "return": rp_t})

    return pd.DataFrame(portfolio_rows)


def calculate_portfolio_metrics(portfolio, missing_data_policy="intersection", risk_free_rate=0.02):
    """
    Core financial engine:
    1. build aligned return series
    2. compute summary metrics
    """

    portfolio_df = compute_portfolio_returns(portfolio, policy=missing_data_policy)

    if portfolio_df.empty:
        raise ValueError("Portfolio has insufficient return data.")

    portfolio_returns = portfolio_df["return"].tolist()

    mean_daily = sum(portfolio_returns) / len(portfolio_returns)
    annual_return = mean_daily * TRADING_DAYS_PER_YEAR

    if len(portfolio_returns) < 2:
        raise ValueError("Not enough return observations to compute volatility.")

    variance = sum((r - mean_daily) ** 2 for r in portfolio_returns) / (len(portfolio_returns) - 1)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)

    sharpe = (annual_return - risk_free_rate) / annual_vol if annual_vol != 0 else 0

    #max drawdown
    cumulative = 1
    peak = 1
    max_drawdown = 0

    for r in portfolio_returns:
        cumulative *= (1 + r)
        peak = max(peak, cumulative)
        drawdown = (cumulative - peak) / peak
        max_drawdown = min(max_drawdown, drawdown)

    return {
        "annualised_return": round(annual_return, 6),
        "annualised_volatility": round(annual_vol, 6),
        "sharpe_ratio": round(sharpe, 6),
        "max_drawdown": round(max_drawdown, 6),
        "missing_data_policy": missing_data_policy,
        "observations": len(portfolio_returns),
    }


def benchmark_comparison(portfolio, benchmark_identifier, policy="intersection"):
    """
    Compare portfolio performance against a benchmark asset.
    """

    try:
        benchmark_asset = Asset.objects.get(identifier=benchmark_identifier)
    except Asset.DoesNotExist:
        raise ValueError("Benchmark asset not found.")

    benchmark_prices = list(
        Price.objects.filter(asset=benchmark_asset)
        .order_by("date")
        .values("date", "closing_price")
    )

    if len(benchmark_prices) < 2:
        raise ValueError("Benchmark has insufficient price data.")

    benchmark_df = pd.DataFrame(benchmark_prices)
    benchmark_df["closing_price"] = benchmark_df["closing_price"].astype(float)
    benchmark_df["return"] = benchmark_df["closing_price"].pct_change()
    benchmark_df.dropna(inplace=True)

    portfolio_df = compute_portfolio_returns(portfolio, policy=policy)

    if portfolio_df.empty:
        raise ValueError("Portfolio has insufficient return data.")

    merged = portfolio_df.merge(
        benchmark_df[["date", "return"]],
        on="date",
        how="inner",
        suffixes=("_portfolio", "_benchmark"),
    )

    if merged.empty:
        raise ValueError("No overlapping dates between portfolio and benchmark.")

    portfolio_returns_series = merged["return_portfolio"]
    benchmark_returns_series = merged["return_benchmark"]

    portfolio_mean = portfolio_returns_series.mean()
    benchmark_mean = benchmark_returns_series.mean()

    portfolio_vol = portfolio_returns_series.std()
    benchmark_vol = benchmark_returns_series.std()

    portfolio_annual_return = portfolio_mean * TRADING_DAYS_PER_YEAR
    benchmark_annual_return = benchmark_mean * TRADING_DAYS_PER_YEAR

    portfolio_vol_annual = portfolio_vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    benchmark_vol_annual = benchmark_vol * np.sqrt(TRADING_DAYS_PER_YEAR)

    return {
        "benchmark_identifier": benchmark_identifier,
        "portfolio_annual_return": round(float(portfolio_annual_return), 6),
        "benchmark_annual_return": round(float(benchmark_annual_return), 6),
        "excess_return": round(float(portfolio_annual_return - benchmark_annual_return), 6),
        "portfolio_volatility": round(float(portfolio_vol_annual), 6),
        "benchmark_volatility": round(float(benchmark_vol_annual), 6),
        "tracking_difference": round(float(portfolio_annual_return - benchmark_annual_return), 6),
        "observations": int(len(merged)),
        "missing_data_policy": policy,
    }

def calculate_rolling_metrics(portfolio, window=30, policy="intersection", risk_free_rate=0.02):
    """
    compute rolling portfolio analytics over a moving window.
    returns a list of date-based rolling metrics
    """

    if window < 2:
        raise ValueError("Window must be at least 2.")

    portfolio_df = compute_portfolio_returns(portfolio, policy=policy)

    if portfolio_df.empty:
        raise ValueError("Portfolio has insufficient return data.")

    if len(portfolio_df) < window:
        raise ValueError("Not enough return observations for the selected rolling window.")

    #rolling mean and rolling standard deviation of daily returns
    portfolio_df["rolling_mean_daily"] = portfolio_df["return"].rolling(window=window).mean()
    portfolio_df["rolling_std_daily"] = portfolio_df["return"].rolling(window=window).std()

    #convert daily measures into annualised measures
    portfolio_df["rolling_annualised_return"] = (
        portfolio_df["rolling_mean_daily"] * TRADING_DAYS_PER_YEAR
    )
    portfolio_df["rolling_annualised_volatility"] = (
        portfolio_df["rolling_std_daily"] * np.sqrt(TRADING_DAYS_PER_YEAR)
    )

    #sharpe ratio for each rolling window
    portfolio_df["rolling_sharpe_ratio"] = np.where(
        portfolio_df["rolling_annualised_volatility"] != 0,
        (portfolio_df["rolling_annualised_return"] - risk_free_rate)
        / portfolio_df["rolling_annualised_volatility"],
        0,
    )

    #remove rows before the first full window is available
    portfolio_df = portfolio_df.dropna(
        subset=[
            "rolling_annualised_return",
            "rolling_annualised_volatility",
            "rolling_sharpe_ratio",
        ]
    )

    results = []
    for _, row in portfolio_df.iterrows():
        results.append(
            {
                "date": row["date"],
                "rolling_annualised_return": round(float(row["rolling_annualised_return"]), 6),
                "rolling_annualised_volatility": round(float(row["rolling_annualised_volatility"]), 6),
                "rolling_sharpe_ratio": round(float(row["rolling_sharpe_ratio"]), 6),
            }
        )

    return results