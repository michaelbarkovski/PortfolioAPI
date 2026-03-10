"""
Portfolio Analytics MCP Server
================================
Exposes the Portfolio Analytics API as tools that any MCP-compatible
LLM client (e.g. Claude Desktop, Cursor) can call directly.

Setup:
    pip install mcp requests

Run:
    python mcp_server.py

Environment variables:
    PORTFOLIO_API_BASE   Base URL of the API  (default: http://127.0.0.1:8000)
    PORTFOLIO_API_TOKEN  JWT access token for authentication
"""

import os
import json
import requests
from mcp.server.fastmcp import FastMCP

# ── Configuration ────────────────────────────────────────────────────────────

API_BASE = os.getenv("PORTFOLIO_API_BASE", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("PORTFOLIO_API_TOKEN", "")

mcp = FastMCP("Portfolio Analytics")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _headers() -> dict:
    """Return auth headers if a token is configured."""
    if API_TOKEN:
        return {"Authorization": f"Bearer {API_TOKEN}"}
    return {}


def _get(path: str, params: dict = None) -> dict:
    """Make an authenticated GET request and return parsed JSON."""
    url = f"{API_BASE}{path}"
    try:
        response = requests.get(url, headers=_headers(), params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return {"error": f"HTTP {e.response.status_code}", "detail": detail}
    except requests.exceptions.ConnectionError:
        return {"error": "Could not connect to the Portfolio API.", "api_base": API_BASE}
    except Exception as e:
        return {"error": str(e)}


def _post(path: str, payload: dict) -> dict:
    """Make an authenticated POST request and return parsed JSON."""
    url = f"{API_BASE}{path}"
    try:
        response = requests.post(url, headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        return {"error": f"HTTP {e.response.status_code}", "detail": detail}
    except requests.exceptions.ConnectionError:
        return {"error": "Could not connect to the Portfolio API.", "api_base": API_BASE}
    except Exception as e:
        return {"error": str(e)}


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_assets() -> str:
    """
    List all financial assets available in the Portfolio Analytics system.
    Returns each asset's ID, ticker identifier (e.g. AAPL, MSFT), and full name.
    """
    result = _get("/api/assets/")
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def list_portfolios() -> str:
    """
    List all portfolios belonging to the authenticated user.
    Returns each portfolio's ID, name, and creation date.
    Requires a valid JWT token to be configured.
    """
    result = _get("/api/portfolios/")
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_portfolio_metrics(
    portfolio_id: int,
    policy: str = "intersection",
    risk_free_rate: float = 0.02,
) -> str:
    """
    Calculate performance metrics for a specific portfolio.

    Args:
        portfolio_id:    The integer ID of the portfolio to analyse.
        policy:          Missing data policy - 'intersection' (default) or 'forward_fill'.
                         intersection: only dates shared by all assets are used.
                         forward_fill: missing returns are filled with the last known value.
        risk_free_rate:  Annual risk-free rate used in the Sharpe ratio calculation (default 0.02).

    Returns:
        JSON with annualised_return, annualised_volatility, sharpe_ratio,
        max_drawdown, observations, and missing_data_policy.
    """
    params = {"policy": policy, "rf": risk_free_rate}
    result = _get(f"/api/portfolios/{portfolio_id}/metrics/", params=params)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_benchmark_comparison(
    portfolio_id: int,
    benchmark: str,
    policy: str = "intersection",
) -> str:
    """
    Compare a portfolio's performance against a benchmark asset.

    Args:
        portfolio_id:  The integer ID of the portfolio to analyse.
        benchmark:     Ticker identifier of the benchmark asset (e.g. 'SPY', 'QQQ').
                       The benchmark must already have price data ingested.
        policy:        Missing data policy - 'intersection' (default) or 'forward_fill'.

    Returns:
        JSON with portfolio_annual_return, benchmark_annual_return, excess_return,
        portfolio_volatility, benchmark_volatility, tracking_difference, and observations.
    """
    params = {"benchmark": benchmark, "policy": policy}
    result = _get(f"/api/portfolios/{portfolio_id}/benchmark/", params=params)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def get_rolling_metrics(
    portfolio_id: int,
    window: int = 30,
    policy: str = "intersection",
    risk_free_rate: float = 0.02,
) -> str:
    """
    Compute rolling performance metrics for a portfolio over a moving window.

    Args:
        portfolio_id:    The integer ID of the portfolio to analyse.
        window:          Rolling window size in trading days (default 30).
                         Each data point is computed using the previous N trading days.
        policy:          Missing data policy - 'intersection' (default) or 'forward_fill'.
        risk_free_rate:  Annual risk-free rate for rolling Sharpe ratio (default 0.02).

    Returns:
        JSON with portfolio_id, window, and a results list where each entry contains
        date, rolling_annualised_return, rolling_annualised_volatility, rolling_sharpe_ratio.
    """
    params = {"window": window, "policy": policy, "rf": risk_free_rate}
    result = _get(f"/api/portfolios/{portfolio_id}/rolling_metrics/", params=params)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def ingest_prices(identifier: str) -> str:
    """
    Ingest the latest daily closing prices for a financial asset from Alpha Vantage.
    Fetches up to 100 recent trading days of price data and stores it in the database.
    Use this before running analytics on a newly added asset.

    Args:
        identifier:  Ticker symbol of the asset to ingest (e.g. 'AAPL', 'MSFT', 'SPY').

    Returns:
        JSON with asset identifier, number of new price rows created, and number updated.
    """
    result = _post("/api/ingest/", {"identifier": identifier})

    # Graceful fallback if the ingest endpoint is not present
    if result.get("error") and "404" in str(result.get("error", "")):
        return json.dumps({
            "message": f"To ingest prices for {identifier}, run on the server:",
            "command": f"python manage.py ingest_prices {identifier}",
        }, indent=2)

    return json.dumps(result, indent=2, default=str)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting Portfolio Analytics MCP Server")
    print(f"API Base: {API_BASE}")
    print(f"Auth:     {'configured' if API_TOKEN else 'no token set (set PORTFOLIO_API_TOKEN)'}")
    print("Tools:    list_assets, list_portfolios, get_portfolio_metrics,")
    print("          get_benchmark_comparison, get_rolling_metrics, ingest_prices")
    print()
    mcp.run()