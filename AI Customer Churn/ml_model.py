"""
ml_model.py — Churn prediction model for the Vitals platform.

Trains one RandomForestClassifier per sector (ecommerce, shopping_app, ott)
on synthetic-but-realistic behavioral data, then exposes:

    predict_churn(sector, features: dict) -> {
        "risk_score": float (0-100),
        "risk_band": "low" | "medium" | "high",
        "reasons": [str, ...],          # from feature importance
        "top_features": [(name, contribution), ...]
    }

In production, replace `generate_synthetic_dataset` with a query against
`customer_features` (see schema.sql) aggregated per customer.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
import joblib
import os

RANDOM_STATE = 42
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# ------------------------------------------------------------------
# Sector-specific feature schemas.
# Each entry: (feature_name, "higher_is_bad" | "higher_is_good")
# ------------------------------------------------------------------
SECTOR_FEATURES = {
    "ecommerce": [
        ("cart_abandon_rate", "bad"),        # 0-1
        ("days_since_last_purchase", "bad"),  # days
        ("order_frequency_30d", "good"),      # count
        ("avg_order_value_trend", "good"),    # -1..1 (pct change)
        ("promo_email_open_rate", "good"),    # 0-1
    ],
    "shopping_app": [
        ("session_freq_7d", "good"),
        ("app_opens_trend", "good"),          # -1..1
        ("wishlist_dormant_days", "bad"),
        ("avg_session_duration_min", "good"),
        ("push_opt_out", "bad"),              # 0/1
    ],
    "ott": [
        ("watch_time_decay_pct", "bad"),      # 0-1
        ("days_since_last_watch", "bad"),
        ("genres_explored_30d", "good"),
        ("series_completion_rate", "good"),
        ("payment_issue_flag", "bad"),        # 0/1
    ],
}

REASON_TEMPLATES = {
    "cart_abandon_rate": "Cart abandonment rate is elevated ({val:.0%})",
    "days_since_last_purchase": "No purchase in {val:.0f} days",
    "order_frequency_30d": "Order frequency dropped to {val:.1f} per month",
    "avg_order_value_trend": "Average order value trending down ({val:+.0%})",
    "promo_email_open_rate": "Rarely opens promotional emails ({val:.0%} open rate)",
    "session_freq_7d": "Only {val:.0f} app sessions in the last 7 days",
    "app_opens_trend": "App opens down {val:+.0%} vs. prior period",
    "wishlist_dormant_days": "Wishlist untouched for {val:.0f} days",
    "avg_session_duration_min": "Session duration shrinking ({val:.1f} min avg)",
    "push_opt_out": "Opted out of push notifications",
    "watch_time_decay_pct": "Watch time decayed {val:.0%} vs. last month",
    "days_since_last_watch": "Hasn't watched anything in {val:.0f} days",
    "genres_explored_30d": "Exploring fewer genres ({val:.0f} in 30 days)",
    "series_completion_rate": "Low series completion rate ({val:.0%})",
    "payment_issue_flag": "Payment method has an outstanding issue",
}


def generate_synthetic_dataset(sector: str, n: int = 4000, seed: int = RANDOM_STATE) -> pd.DataFrame:
    """Generates a labeled synthetic dataset for a sector. Replace with real
    historical data (customers who did/didn't churn) in production."""
    rng = np.random.default_rng(seed)
    feats = SECTOR_FEATURES[sector]
    data = {}

    for name, direction in feats:
        if name in ("push_opt_out", "payment_issue_flag"):
            data[name] = rng.binomial(1, 0.2, n).astype(float)
        elif "rate" in name or "pct" in name:
            data[name] = rng.beta(2, 3, n)
        elif "trend" in name:
            data[name] = rng.normal(0, 0.3, n)
        elif "days" in name:
            data[name] = rng.exponential(15, n)
        else:
            data[name] = rng.gamma(2, 2, n)

    df = pd.DataFrame(data)

    # Construct a latent churn propensity from the features so labels are
    # actually learnable (bad-direction features push churn up).
    latent = np.zeros(n)
    for name, direction in feats:
        col = df[name]
        norm = (col - col.mean()) / (col.std() + 1e-9)
        latent += norm if direction == "bad" else -norm

    latent += rng.normal(0, 1.0, n)  # noise
    prob = 1 / (1 + np.exp(-latent / 2))
    df["churned"] = rng.binomial(1, prob)
    return df


def train_sector_model(sector: str):
    df = generate_synthetic_dataset(sector)
    feature_names = [f[0] for f in SECTOR_FEATURES[sector]]
    X, y = df[feature_names], df["churned"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)

    model = RandomForestClassifier(
        n_estimators=300, max_depth=6, min_samples_leaf=20,
        random_state=RANDOM_STATE, class_weight="balanced",
    )
    model.fit(X_train, y_train)
    auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])

    joblib.dump(model, os.path.join(MODEL_DIR, f"{sector}_model.joblib"))
    print(f"[{sector}] trained. holdout AUC = {auc:.3f}")
    return model, auc


def load_model(sector: str):
    path = os.path.join(MODEL_DIR, f"{sector}_model.joblib")
    if not os.path.exists(path):
        train_sector_model(sector)
    return joblib.load(path)


def predict_churn(sector: str, features: dict) -> dict:
    """features: dict of {feature_name: value} matching SECTOR_FEATURES[sector]"""
    model = load_model(sector)
    feature_names = [f[0] for f in SECTOR_FEATURES[sector]]
    x = pd.DataFrame([{name: features.get(name, 0.0) for name in feature_names}])

    risk_score = float(model.predict_proba(x)[0, 1] * 100)
    band = "high" if risk_score > 70 else "medium" if risk_score > 40 else "low"

    # Feature-importance x deviation-from-mean gives a rough "why" ranking
    # (a lightweight stand-in for SHAP; swap in `shap.TreeExplainer` for
    # production-grade per-prediction attributions).
    importances = model.feature_importances_
    contributions = []
    for i, name in enumerate(feature_names):
        direction = dict(SECTOR_FEATURES[sector])[name]
        val = features.get(name, 0.0)
        sign = 1 if direction == "bad" else -1
        contributions.append((name, importances[i] * sign * (val if val else 0.01)))

    contributions.sort(key=lambda t: t[1], reverse=True)
    top = contributions[:3]

    reasons = []
    for name, _ in top:
        val = features.get(name, 0.0)
        template = REASON_TEMPLATES.get(name, "{name} is a contributing factor")
        reasons.append(template.format(val=val, name=name))

    return {
        "risk_score": round(risk_score, 1),
        "risk_band": band,
        "reasons": reasons,
        "top_features": [(n, round(float(c), 3)) for n, c in top],
    }


if __name__ == "__main__":
    for sector in SECTOR_FEATURES:
        train_sector_model(sector)

    # quick smoke test
    sample = {
        "cart_abandon_rate": 0.72,
        "days_since_last_purchase": 48,
        "order_frequency_30d": 0.5,
        "avg_order_value_trend": -0.22,
        "promo_email_open_rate": 0.05,
    }
    print(predict_churn("ecommerce", sample))
