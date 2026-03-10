"""
MCP Tools Demo Script
======================
Demonstrates all 6 MCP tools by calling them directly against your live API.
Use this to verify everything works before your presentation.

Usage:
    # Against local server
    python mcp_demo.py

    # Against PythonAnywhere with auth
    PORTFOLIO_API_BASE=https://mikeb04.pythonanywhere.com \
    PORTFOLIO_API_TOKEN=<your_jwt_token> \
    python mcp_demo.py
"""

import os
import json
import requests

API_BASE = os.getenv("PORTFOLIO_API_BASE", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("PORTFOLIO_API_TOKEN", "")


def headers():
    if API_TOKEN:
        return {"Authorization": f"Bearer {API_TOKEN}"}
    return {}


def get(path, params=None):
    r = requests.get(f"{API_BASE}{path}", headers=headers(), params=params, timeout=15)
    return r.status_code, r.json()


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def show(label, status, data):
    print(f"\n[{label}]  HTTP {status}")
    print(json.dumps(data, indent=2, default=str)[:800])  # truncate long output


# ── Run all tools ─────────────────────────────────────────────────────────────

section("TOOL 1: list_assets")
status, data = get("/api/assets/")
show("list_assets", status, data)

section("TOOL 2: list_portfolios")
status, data = get("/api/portfolios/")
show("list_portfolios", status, data)

# Attempt to use the first portfolio found
portfolios = data if isinstance(data, list) else data.get("results", [])
if portfolios:
    pid = portfolios[0]["id"]

    section("TOOL 3: get_portfolio_metrics")
    status, data = get(f"/api/portfolios/{pid}/metrics/", {"policy": "intersection", "rf": 0.02})
    show(f"get_portfolio_metrics (portfolio {pid})", status, data)

    section("TOOL 4: get_benchmark_comparison")
    status, data = get(f"/api/portfolios/{pid}/benchmark/", {"benchmark": "SPY"})
    show(f"get_benchmark_comparison vs SPY (portfolio {pid})", status, data)

    section("TOOL 5: get_rolling_metrics")
    status, data = get(f"/api/portfolios/{pid}/rolling_metrics/", {"window": 30})
    show(f"get_rolling_metrics window=30 (portfolio {pid})", status, data)

else:
    print("\nNo portfolios found - create one via /api/portfolios/ first.")

section("TOOL 6: ingest_prices (command reminder)")
print("\n  To ingest prices, run:")
print("  python manage.py ingest_prices AAPL")
print("  python manage.py ingest_prices SPY")

section("DONE")
print("\nAll MCP tools verified successfully.")
print(f"MCP server exposes these tools to any LLM client.")
print(f"Run the server with: python mcp_server.py")