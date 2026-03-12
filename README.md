# Portfolio Analytics API

A REST API for building and analysing investment portfolios. Users can create portfolios, ingest live market data from Alpha Vantage, and compute professional-grade financial performance metrics including annualised return, volatility, Sharpe ratio, maximum drawdown, benchmark comparison, and rolling analytics.

Built with Python, Django, and Django REST Framework. Deployed live on PythonAnywhere.

**Live API:** https://mikeb04.pythonanywhere.com/api/docs/

---

## Tech Stack

- Python 3.13
- Django
- Django REST Framework
- djangorestframework-simplejwt
- drf-spectacular (OpenAPI/Swagger docs)
- SQLite
- Alpha Vantage API

---

## Local Setup

**1. Clone the repository**
```bash
git clone https://github.com/michaelbarkovski/PortfolioAPI.git
cd PortfolioAPI
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set environment variables**
```bash
export ALPHAVANTAGE_API_KEY=your_api_key_here
```

**5. Run migrations**
```bash
python manage.py migrate
```

**6. Create a superuser (optional)**
```bash
python manage.py createsuperuser
```

**7. Run the development server**
```bash
python manage.py runserver
```

API will be available at http://127.0.0.1:8000/api/docs/

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ALPHAVANTAGE_API_KEY` | API key from https://www.alphavantage.co/support/#api-key |

---

## Ingesting Market Data

To ingest historical price data for an asset:
```bash
python manage.py ingest_prices AAPL
python manage.py ingest_prices SPY
```

This fetches up to 100 days of daily closing prices from Alpha Vantage and stores them in the database. The command is idempotent — safe to re-run without creating duplicates.

---

## API Endpoints

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET/POST | `/api/assets/` | List and create assets | Read public |
| GET/POST | `/api/prices/` | List and create prices | Read public |
| GET/POST | `/api/portfolios/` | List and create portfolios | Required |
| GET/POST | `/api/holdings/` | List and create holdings | Required |
| GET | `/api/portfolios/{id}/metrics/` | Performance metrics | Required |
| GET | `/api/portfolios/{id}/benchmark/` | Benchmark comparison | Required |
| GET | `/api/portfolios/{id}/rolling_metrics/` | Rolling analytics | Required |
| POST | `/api/auth/register/` | Register a new user | None |
| POST | `/api/token/` | Obtain JWT token | None |
| POST | `/api/token/refresh/` | Refresh JWT token | None |

Full interactive documentation available at `/api/docs/`

---

## Authentication

Register a user:
```bash
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "mypassword", "password2": "mypassword"}'
```

Obtain a token:
```bash
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "myuser", "password": "mypassword"}'
```

Use the token in requests:
```bash
curl -H "Authorization: Bearer <access_token>" \
  http://127.0.0.1:8000/api/portfolios/
```

---

## Running Tests
```bash
python manage.py test portfolio -v 2
```

82 tests across 11 test classes covering models, analytics, API endpoints, security, and edge cases.

---

## MCP Server

The MCP server exposes the portfolio analytics as tools callable by any MCP-compatible LLM client such as Claude Desktop or Cursor.

**Setup:**
```bash
pip install mcp requests
```

**Run:**
```bash
export PORTFOLIO_API_BASE=https://mikeb04.pythonanywhere.com
export PORTFOLIO_API_TOKEN=your_jwt_token_here
python mcp_server.py
```

**Tools available:**
- `list_assets`
- `list_portfolios`
- `get_portfolio_metrics`
- `get_benchmark_comparison`
- `get_rolling_metrics`
- `ingest_prices`

## MCP Demo

A demonstration script is included to verify all 6 MCP tools are working correctly against the live API.

**Run:**
```bash
export PORTFOLIO_API_BASE=https://mikeb04.pythonanywhere.com
export PORTFOLIO_API_TOKEN=your_jwt_token_here
python mcp_demo.py
```

This will call all 6 tools in sequence and print the results to the terminal, confirming the MCP server is communicating correctly with the live API.

## Test Credentials (Live API)

- **Username:** testuser
- **Password:** testpass123
- **Token endpoint:** https://mikeb04.pythonanywhere.com/api/token/
