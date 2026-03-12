import os
import json
import requests
from mcp.server.fastmcp import FastMCP

#configuration — loaded from environment variables
API_BASE = os.getenv("PORTFOLIO_API_BASE", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("PORTFOLIO_API_TOKEN", "")

mcp = FastMCP("Portfolio Analytics")

def _headers() -> dict:
    #return auth header if token is set
    if API_TOKEN:
        return {"Authorization": f"Bearer {API_TOKEN}"}
    return {}

def _get(path: str, params: dict = None) -> dict:
    #authenticated GET request
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
    #authenticated POST request
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

#list all assets in the system
@mcp.tool()
def list_assets() -> str:
    result = _get("/api/assets/")
    return json.dumps(result, indent=2, default=str)

#list all portfolios belonging to the authenticated user
@mcp.tool()
def list_portfolios() -> str:
    result = _get("/api/portfolios/")
    return json.dumps(result, indent=2, default=str)

#get performance metrics for a specific portfolio
@mcp.tool()
def get_portfolio_metrics(
    portfolio_id: int,
    policy: str = "intersection",
    risk_free_rate: float = 0.02,
) -> str:
    params = {"policy": policy, "rf": risk_free_rate}
    result = _get(f"/api/portfolios/{portfolio_id}/metrics/", params=params)
    return json.dumps(result, indent=2, default=str)

#compare portfolio performance against a benchmark asset
@mcp.tool()
def get_benchmark_comparison(
    portfolio_id: int,
    benchmark: str,
    policy: str = "intersection",
) -> str:
    params = {"benchmark": benchmark, "policy": policy}
    result = _get(f"/api/portfolios/{portfolio_id}/benchmark/", params=params)
    return json.dumps(result, indent=2, default=str)

#compute rolling metrics over a configurable moving window
@mcp.tool()
def get_rolling_metrics(
    portfolio_id: int,
    window: int = 30,
    policy: str = "intersection",
    risk_free_rate: float = 0.02,
) -> str:
    params = {"window": window, "policy": policy, "rf": risk_free_rate}
    result = _get(f"/api/portfolios/{portfolio_id}/rolling_metrics/", params=params)
    return json.dumps(result, indent=2, default=str)

#ingest latest prices for an asset from Alpha Vantage
@mcp.tool()
def ingest_prices(identifier: str) -> str:
    result = _post("/api/ingest/", {"identifier": identifier})

    #graceful fallback if ingest endpoint is not available
    if result.get("error") and "404" in str(result.get("error", "")):
        return json.dumps({
            "message": f"To ingest prices for {identifier}, run on the server:",
            "command": f"python manage.py ingest_prices {identifier}",
        }, indent=2)

    return json.dumps(result, indent=2, default=str)

if __name__ == "__main__":
    print("Starting Portfolio Analytics MCP Server")
    print(f"API Base: {API_BASE}")
    print(f"Auth:     {'configured' if API_TOKEN else 'no token set (set PORTFOLIO_API_TOKEN)'}")
    print("Tools:    list_assets, list_portfolios, get_portfolio_metrics,")
    print("          get_benchmark_comparison, get_rolling_metrics, ingest_prices")
    print()
    mcp.run()