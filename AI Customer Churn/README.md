# Vitals — Churn Intelligence Platform

Backend implementation of the architecture:

```
Company Registration → Secure Login → Auth Server
        → Company Dashboard (Overview / Customer List / Reports)
        → Search Customer → Fetch Customer Data
        → ML Model → Churn Probability Prediction
        → Risk Score + Reasons + AI Suggestions
        → Save to Database
```

## Files

| File | Role |
|---|---|
| `schema.sql` | Multi-tenant Postgres schema: companies, users, customers, features, predictions |
| `ml_model.py` | Trains one RandomForest per sector (ecommerce / shopping_app / ott) on behavioral features, exposes `predict_churn()` |
| `main.py` | FastAPI app: registration, JWT login, dashboard, customer search/CRUD, prediction endpoints |
| `requirements.txt` | Python dependencies |

## Running it

```bash
pip install -r requirements.txt
python ml_model.py          # trains and saves the 3 sector models to ./models
uvicorn main:app --reload   # starts the API on http://localhost:8000
```

Then, e.g.:

```bash
# 1. Register a company
curl -X POST localhost:8000/auth/register -H "Content-Type: application/json" -d \
  '{"company_name":"Northstar Retail","sector":"ecommerce","email":"admin@northstar.com","password":"secret123"}'
# -> returns { "access_token": "..." }

# 2. Add + score a customer (use the token from step 1)
curl -X POST localhost:8000/customers -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" -d \
  '{"external_ref":"CUST-001","name":"Aarav Sharma","features":{"cart_abandon_rate":0.72,"days_since_last_purchase":48,"order_frequency_30d":0.5,"avg_order_value_trend":-0.22,"promo_email_open_rate":0.05}}'

# 3. See the dashboard
curl localhost:8000/dashboard/overview -H "Authorization: Bearer <TOKEN>"
```

## Swapping in real data & production pieces

- **Database**: replace the `DB_*` in-memory dicts in `main.py` with SQLAlchemy/asyncpg calls against `schema.sql`. The function signatures are already shaped 1:1 for that swap.
- **Model training data**: replace `generate_synthetic_dataset()` in `ml_model.py` with a real query — pull `customer_features` joined against a `churned` label (e.g. "canceled/uninstalled within 30 days: yes/no") from your warehouse.
- **AI Suggestions**: `_suggest_actions()` is rule-based for the demo. In production, feed the `reasons` list + sector context into an LLM call (e.g. the Anthropic API) to generate more specific, on-brand retention copy per customer.
- **Reasons/explainability**: the current approach is feature-importance × deviation-from-mean, a fast approximation. For proper per-prediction attribution, swap in `shap.TreeExplainer(model).shap_values(x)`.
- **Auth**: `JWT_SECRET` must move to an environment variable / secrets manager, and passwords should be checked against rate-limiting on login.
- **Ingestion**: right now `POST /customers` takes features directly. In production you'd add a `/ingest` endpoint or webhook that companies point their event stream (Segment, their own backend, etc.) at, which writes into `customer_features` on a schedule, then a batch job scores all customers periodically (e.g. nightly) in addition to on-demand scoring.

## Frontend

The matching demo dashboard (`churn-dashboard.jsx`) is a self-contained React app showing the same workflow end-to-end with mock data. Point its API calls at this backend to go from demo to real product.
