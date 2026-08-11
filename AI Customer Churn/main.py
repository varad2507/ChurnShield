# -*- coding: utf-8 -*-
"""
main.py — Vitals Churn Intelligence Platform API

Backend architecture featuring:
  1. Company Registration & Secure Login (JWT + SQLite persistence)
  2. Audit Logging System (event tracking, search, action filter, pagination)
  3. Multi-Channel Automated Churn Notifications (Email + SMS triggers, throttling)
  4. Real-Time Churn Predictions & WebSockets Engine
  5. Admin AI Strategic Assistant (Chatbot API)
  6. CORS Middleware & Static Dashboard Serving
"""

from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import uuid
# pyrefly: ignore [missing-import]
import jwt
import bcrypt
import json
import asyncio
import urllib.request
import urllib.error
import urllib.parse
import os
import base64
import random
import sqlite3
import threading

from ml_model import predict_churn, SECTOR_FEATURES

app = FastAPI(title="Vitals Churn Intelligence API", version="2.0")

# Enable CORS for cross-origin web client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = os.getenv("JWT_SECRET", "vitals-churn-secret-key-production-2026")
JWT_ALGO = "HS256"
TOKEN_TTL_HOURS = 12

# ------------------------------------------------------------------
# SQLite Database — persistent storage
# ------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "vitals_churn.db")
_db_lock = threading.Lock()

def get_db() -> sqlite3.Connection:
    """Open a SQLite connection with row_factory for dict-like rows."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safer concurrent access
    return conn

def init_db():
    """Create all tables if they don't already exist."""
    with _db_lock, get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS companies (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                sector      TEXT NOT NULL DEFAULT 'ecommerce'
            );

            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                company_id    TEXT NOT NULL REFERENCES companies(id),
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'admin'
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id               TEXT PRIMARY KEY,
                company_id       TEXT NOT NULL,
                actor_id         TEXT,
                action_type      TEXT,
                entity_affected  TEXT,
                previous_state   TEXT,
                new_state        TEXT,
                ip_address       TEXT,
                timestamp        TEXT
            );

            CREATE TABLE IF NOT EXISTS notification_logs (
                id               TEXT PRIMARY KEY,
                company_id       TEXT NOT NULL,
                customer_id      TEXT,
                customer_name    TEXT,
                channel          TEXT,
                recipient        TEXT,
                subject          TEXT,
                body             TEXT,
                status           TEXT,
                triggered_score  REAL,
                sent_at          TEXT
            );

            CREATE TABLE IF NOT EXISTS notification_settings (
                company_id           TEXT PRIMARY KEY REFERENCES companies(id),
                high_risk_threshold  REAL    DEFAULT 75.0,
                email_enabled        INTEGER DEFAULT 1,
                sms_enabled          INTEGER DEFAULT 1,
                cooling_off_hours    INTEGER DEFAULT 24,
                email_recipient      TEXT,
                sms_recipient        TEXT
            );

            CREATE TABLE IF NOT EXISTS file_uploads (
                id           TEXT PRIMARY KEY,
                company_id   TEXT NOT NULL,
                name         TEXT,
                uploader     TEXT,
                timestamp    TEXT,
                size         TEXT,
                status       TEXT DEFAULT 'Processed',
                record_count INTEGER DEFAULT 0
            );
        """)
        conn.commit()

# Initialise database on startup
init_db()

# ── In-memory caches (non-persistent, rebuilt as needed) ──────────────────
# Customers & predictions stay in memory (large / frequently updated)
DB_CUSTOMERS: Dict[str, dict] = {}
DB_PREDICTIONS: Dict[str, dict] = {}
DB_CUSTOMER_NOTIFIED_AT: Dict[str, str] = {}

# Notification settings cache (loaded from DB on demand)
_notif_settings_cache: Dict[str, dict] = {}

# ── SQLite helper wrappers ────────────────────────────────────────────────
def db_get_company(company_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else None

def db_get_user_by_email(email: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

def db_insert_company(company_id: str, name: str, sector: str):
    with _db_lock, get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO companies (id, name, sector) VALUES (?, ?, ?)",
            (company_id, name, sector)
        )
        conn.commit()

def db_insert_user(user_id: str, company_id: str, email: str, password_hash: str, role: str = "admin"):
    with _db_lock, get_db() as conn:
        conn.execute(
            "INSERT INTO users (id, company_id, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            (user_id, company_id, email, password_hash, role)
        )
        conn.commit()

def db_insert_audit(entry: dict):
    with _db_lock, get_db() as conn:
        conn.execute(
            """INSERT INTO audit_logs
               (id, company_id, actor_id, action_type, entity_affected,
                previous_state, new_state, ip_address, timestamp)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                entry["id"], entry["company_id"], entry.get("actor_id"),
                entry["action_type"], entry["entity_affected"],
                json.dumps(entry.get("previous_state")),
                json.dumps(entry.get("new_state")),
                entry.get("ip_address"), entry["timestamp"]
            )
        )
        conn.commit()

def db_get_audit_logs(company_id: str, action_filter: str = "ALL", search: str = "",
                      skip: int = 0, limit: int = 50) -> List[dict]:
    with get_db() as conn:
        q = "SELECT * FROM audit_logs WHERE company_id = ?"
        params: list = [company_id]
        if action_filter and action_filter != "ALL":
            q += " AND action_type = ?"
            params.append(action_filter)
        if search:
            q += " AND (entity_affected LIKE ? OR actor_id LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        q += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params += [limit, skip]
        rows = conn.execute(q, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["previous_state"] = json.loads(d["previous_state"]) if d["previous_state"] else None
            d["new_state"]      = json.loads(d["new_state"])      if d["new_state"]      else None
            result.append(d)
        return result

def db_insert_notif_log(entry: dict):
    with _db_lock, get_db() as conn:
        conn.execute(
            """INSERT INTO notification_logs
               (id, company_id, customer_id, customer_name, channel,
                recipient, subject, body, status, triggered_score, sent_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entry["id"], entry["company_id"], entry.get("customer_id"),
                entry.get("customer_name"), entry.get("channel"),
                entry.get("recipient"), entry.get("subject"), entry.get("body"),
                entry.get("status"), entry.get("triggered_score"), entry.get("sent_at")
            )
        )
        conn.commit()

def db_get_notif_logs(company_id: str, limit: int = 100) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notification_logs WHERE company_id = ? ORDER BY sent_at DESC LIMIT ?",
            (company_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def db_get_notif_settings(company_id: str) -> dict:
    """Load from DB (or cache). Create default row if none exists."""
    if company_id in _notif_settings_cache:
        return _notif_settings_cache[company_id]
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM notification_settings WHERE company_id = ?", (company_id,)
        ).fetchone()
        if row:
            s = dict(row)
            s["email_enabled"] = bool(s["email_enabled"])
            s["sms_enabled"]   = bool(s["sms_enabled"])
        else:
            company = db_get_company(company_id) or {}
            s = {
                "company_id": company_id,
                "high_risk_threshold": 75.0,
                "email_enabled": True,
                "sms_enabled": True,
                "cooling_off_hours": 24,
                "email_recipient": "retention-team@" + company.get("name", "company").lower().replace(" ", "") + ".com",
                "sms_recipient": "+15550192834"
            }
            with _db_lock, get_db() as cw:
                cw.execute(
                    """INSERT OR IGNORE INTO notification_settings
                       (company_id, high_risk_threshold, email_enabled, sms_enabled,
                        cooling_off_hours, email_recipient, sms_recipient)
                       VALUES (?,?,?,?,?,?,?)""",
                    (company_id, s["high_risk_threshold"], 1, 1,
                     s["cooling_off_hours"], s["email_recipient"], s["sms_recipient"])
                )
                cw.commit()
        _notif_settings_cache[company_id] = s
        return s

def db_save_notif_settings(company_id: str, settings: dict):
    _notif_settings_cache[company_id] = settings
    with _db_lock, get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO notification_settings
               (company_id, high_risk_threshold, email_enabled, sms_enabled,
                cooling_off_hours, email_recipient, sms_recipient)
               VALUES (?,?,?,?,?,?,?)""",
            (
                company_id,
                settings.get("high_risk_threshold", 75.0),
                1 if settings.get("email_enabled", True) else 0,
                1 if settings.get("sms_enabled", True)   else 0,
                settings.get("cooling_off_hours", 24),
                settings.get("email_recipient", ""),
                settings.get("sms_recipient", "")
            )
        )
        conn.commit()

def db_insert_file_upload(record: dict, company_id: str):
    with _db_lock, get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO file_uploads
               (id, company_id, name, uploader, timestamp, size, status, record_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                record.get("id", str(uuid.uuid4())), company_id,
                record.get("name"), record.get("uploader"),
                record.get("timestamp"), record.get("size"),
                record.get("status", "Processed"),
                record.get("recordCount", record.get("record_count", 0))
            )
        )
        conn.commit()

def db_get_file_uploads(company_id: str) -> List[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM file_uploads WHERE company_id = ? ORDER BY timestamp DESC",
            (company_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["recordCount"] = d.pop("record_count", 0)
            result.append(d)
        return result



# ------------------------------------------------------------------
# WebSockets Real-Time Connection Manager
# ------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        # company_id -> list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, company_id: str):
        await websocket.accept()
        if company_id not in self.active_connections:
            self.active_connections[company_id] = []
        self.active_connections[company_id].append(websocket)

    def disconnect(self, websocket: WebSocket, company_id: str):
        if company_id in self.active_connections:
            if websocket in self.active_connections[company_id]:
                self.active_connections[company_id].remove(websocket)

    async def broadcast_to_company(self, company_id: str, message: dict):
        if company_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[company_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, company_id)

manager = ConnectionManager()


# ------------------------------------------------------------------
# Audit Logging Helper
# ------------------------------------------------------------------
def log_audit_event(
    company_id: str,
    action_type: str,
    entity_affected: str,
    previous_state: Optional[dict] = None,
    new_state: Optional[dict] = None,
    actor_id: str = "System",
    ip_address: str = "127.0.0.1"
):
    audit_entry = {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "actor_id": actor_id,
        "action_type": action_type,
        "entity_affected": entity_affected,
        "previous_state": previous_state,
        "new_state": new_state,
        "ip_address": ip_address,
        "timestamp": datetime.utcnow().isoformat()
    }
    db_insert_audit(audit_entry)
    return audit_entry


# ------------------------------------------------------------------
# Automated Multi-Channel Notification Engine with Throttling
# ------------------------------------------------------------------
def get_notification_settings(company_id: str) -> dict:
    return db_get_notif_settings(company_id)

RESEND_API_KEY = "re_bEjRXLbH_KPJnwsdZKNkhshQg4PUDDfXi"

def send_resend_email(to_email: str, subject: str, body_text: str):
    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    }
    html_body = body_text.replace("\n", "<br>")
    data = {
        "from": "Acme <onboarding@resend.dev>",
        "to": [to_email],
        "subject": subject,
        "html": html_body
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            return True, response.read().decode('utf-8')
    except Exception as e:
        return False, str(e)


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "AC_YOUR_ACCOUNT_SID")
TWILIO_API_KEY = "SKbdbe4096fe4108f29b9320922d96df61"
TWILIO_API_SECRET = os.getenv("TWILIO_API_SECRET", "YOUR_API_SECRET")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+15550192834")

def send_twilio_sms(to_phone: str, body_text: str):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth_str = f"{TWILIO_API_KEY}:{TWILIO_API_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = urllib.parse.urlencode({
        "From": TWILIO_FROM_NUMBER,
        "To": to_phone,
        "Body": body_text
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return True, response.read().decode('utf-8')
    except Exception as e:
        return False, str(e)


def process_churn_notifications(company_id: str, customer: dict, prediction: dict) -> List[dict]:
    settings = get_notification_settings(company_id)
    threshold = settings.get("high_risk_threshold", 75.0)
    risk_score = prediction.get("risk_score", 0.0)

    if risk_score < threshold:
        return []

    customer_id = customer["id"]
    customer_name = customer.get("name", "Valued Customer")
    cooling_off_hours = settings.get("cooling_off_hours", 24)

    # Cooling-off / Throttling check
    last_notified_str = DB_CUSTOMER_NOTIFIED_AT.get(customer_id)
    if last_notified_str:
        last_notified = datetime.fromisoformat(last_notified_str)
        if datetime.utcnow() - last_notified < timedelta(hours=cooling_off_hours):
            # Throttle notification to prevent spam
            log_record = {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "customer_id": customer_id,
                "customer_name": customer_name,
                "channel": "email_and_sms",
                "recipient": settings["email_recipient"],
                "subject": f"[THROTTLED] High Risk Alert: {customer_name}",
                "body": f"Notification suppressed for {customer_name} due to active cooling-off period ({cooling_off_hours}h).",
                "status": "SKIPPED_THROTTLED",
                "triggered_score": risk_score,
                "sent_at": datetime.utcnow().isoformat()
            }
            db_insert_notif_log(log_record)
            log_audit_event(
                company_id=company_id,
                action_type="NOTIFICATION_THROTTLED",
                entity_affected=customer_id,
                new_state={"score": risk_score, "reason": "cooling_off_active"}
            )
            return [log_record]

    # Generate Notification Payload
    suggestions = prediction.get("ai_suggestions", ["Offer personalized retention incentive"])
    top_suggestion = suggestions[0] if suggestions else "Reach out with a special offer"
    reasons = prediction.get("reasons", ["Elevated churn signals detected"])
    reasons_text = "; ".join(reasons)

    triggered_logs = []

    # 1. Email Notification
    if settings.get("email_enabled", True):
        email_recipient = settings.get("email_recipient") or "admin@company.com"
        subject = f"⚠️ HIGH RISK ALERT: {customer_name} (Churn Risk: {risk_score}%)"
        body = (
            f"ALERT: Customer '{customer_name}' (ID: {customer['external_ref']}) has reached a critical churn risk score of {risk_score}%.\n\n"
            f"Top Behavioral Reasons:\n- {reasons_text}\n\n"
            f"Recommended Retention Action:\n-> {top_suggestion}\n\n"
            f"System Notice: Please initiate proactive retention outreach immediately."
        )
        email_log = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "channel": "email",
            "recipient": email_recipient,
            "subject": subject,
            "body": body,
            "status": "SENT",
            "triggered_score": risk_score,
            "sent_at": datetime.utcnow().isoformat()
        }
        
        # Send actual email via Resend
        success, response_msg = send_resend_email(email_recipient, subject, body)
        if not success:
            email_log["status"] = f"FAILED: {response_msg}"
            
        DB_NOTIFICATION_LOGS.insert(0, email_log)
        triggered_logs.append(email_log)

    # 2. SMS Notification
    if settings.get("sms_enabled", True):
        sms_recipient = settings.get("sms_recipient") or "+15550192834"
        sms_body = f"[Vitals Alert] {customer_name} churn risk spiked to {risk_score}%. Suggested action: {top_suggestion}"
        sms_log = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "channel": "sms",
            "recipient": sms_recipient,
            "subject": "SMS Risk Alert",
            "body": sms_body,
            "status": "SENT",
            "triggered_score": risk_score,
            "sent_at": datetime.utcnow().isoformat()
        }
        
        success, response_msg = send_twilio_sms(sms_recipient, sms_body)
        if not success:
            sms_log["status"] = f"FAILED: {response_msg}"
            
        DB_NOTIFICATION_LOGS.insert(0, sms_log)
        triggered_logs.append(sms_log)

    # Mark last notified time for cooling-off throttling
    DB_CUSTOMER_NOTIFIED_AT[customer_id] = datetime.utcnow().isoformat()

    log_audit_event(
        company_id=company_id,
        action_type="NOTIFICATION_DISPATCHED",
        entity_affected=customer_id,
        new_state={"score": risk_score, "channels": [l["channel"] for l in triggered_logs]}
    )

    return triggered_logs


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------
class RegisterRequest(BaseModel):
    company_name: str
    sector: str  # "ecommerce" | "shopping_app" | "ott" | "telecom" | "banking" | "insurance" | "jobportals" | "utilities"
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


class CustomerCreate(BaseModel):
    external_ref: str
    name: str
    features: dict
    email: Optional[str] = None
    phone: Optional[str] = None

class CustomerTelemetryUpdate(BaseModel):
    features: dict

class NotificationSettingsUpdate(BaseModel):
    high_risk_threshold: Optional[float] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    cooling_off_hours: Optional[int] = None
    email_recipient: Optional[str] = None
    sms_recipient: Optional[str] = None

class ManualNotificationRequest(BaseModel):
    customer_id: str
    customer_name: Optional[str] = None
    channels: List[str] = ["email", "sms"]
    subject: str
    body: str

class BulkNotificationRequest(BaseModel):
    customer_ids: List[str]
    channels: List[str] = ["email", "sms"]
    subject: str
    body: str

class FileUploadRecord(BaseModel):
    id: Optional[str] = None
    name: str
    uploader: Optional[str] = None
    timestamp: Optional[str] = None
    size: Optional[str] = "1.2 MB"
    status: Optional[str] = "Processed"
    recordCount: Optional[int] = 28

class AIChatRequest(BaseModel):
    message: str
    customer_id: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    company_name: Optional[str] = None
    sector: Optional[str] = None
    email: Optional[str] = None


# ------------------------------------------------------------------
# Auth Helpers
# ------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_email: str, company_id: str, company_name: str = "", sector: str = "") -> str:
    payload = {
        "sub": user_email,
        "company_id": company_id,
        "company_name": company_name,
        "sector": sector,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def get_current_company(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    return payload["company_id"]


# ------------------------------------------------------------------
# 1. Web & Auth Endpoints
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the Vitals Dashboard HTML file directly."""
    html_path = os.path.join(os.path.dirname(__file__), "vitals-dashboard.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Vitals Churn Intelligence Platform API v2.0</h1>"

@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, request: Request):
    user = db_get_user_by_email(req.email)
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    company_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    db_insert_company(company_id, req.company_name, req.sector)
    db_insert_user(user_id, company_id, req.email, hash_password(req.password))
    
    token = create_token(req.email, company_id, req.company_name, req.sector)
    
    log_audit_event(
        company_id=company_id,
        action_type="USER_REGISTER",
        entity_affected=req.email,
        actor_id=req.email,
        ip_address=request.client.host if request.client else "127.0.0.1"
    )
    
    return TokenResponse(access_token=token, company_name=req.company_name, sector=req.sector, email=req.email)

@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request):
    user = db_get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials.")
    
    company_id = user["company_id"]
    company = db_get_company(company_id) or {}
    company_name = company.get("name", "")
    sector = company.get("sector", "ecommerce")

    token = create_token(req.email, company_id, company_name, sector)

    log_audit_event(
        company_id=company_id,
        action_type="USER_LOGIN",
        entity_affected=req.email,
        actor_id=req.email,
        ip_address=request.client.host if request.client else "127.0.0.1"
    )

    return TokenResponse(access_token=token, company_name=company_name, sector=sector, email=req.email)


# ------------------------------------------------------------------
# 2. Company Dashboard & Customer Endpoints
# ------------------------------------------------------------------
@app.get("/dashboard/overview")
def dashboard_overview(company_id: str = Depends(get_current_company)):
    customers = [c for c in DB_CUSTOMERS.values() if c["company_id"] == company_id]
    predictions = [DB_PREDICTIONS[c["id"]] for c in customers if c["id"] in DB_PREDICTIONS]

    if not predictions:
        return {"customers_monitored": len(customers), "avg_risk": None, "high_risk_count": 0}

    avg_risk = sum(p["risk_score"] for p in predictions) / len(predictions)
    high_risk = sum(1 for p in predictions if p["risk_band"] == "high")
    return {
        "customers_monitored": len(customers),
        "avg_risk": round(avg_risk, 1),
        "high_risk_count": high_risk,
        "retained_count": len(customers) - high_risk
    }

@app.get("/customers")
def list_customers(q: Optional[str] = None, company_id: str = Depends(get_current_company)):
    customers = [c for c in DB_CUSTOMERS.values() if c["company_id"] == company_id]
    if q:
        q_lower = q.lower()
        customers = [c for c in customers if q_lower in c["name"].lower() or q_lower in c["external_ref"].lower()]

    results = []
    for c in customers:
        pred = DB_PREDICTIONS.get(c["id"])
        results.append({
            "id": c["id"],
            "external_ref": c["external_ref"],
            "name": c["name"],
            "last_active": c.get("last_active_at", "1d ago"),
            "risk_score": pred["risk_score"] if pred else None,
            "risk_band": pred["risk_band"] if pred else None,
            "reasons": pred.get("reasons", []) if pred else [],
            "ai_suggestions": pred.get("ai_suggestions", []) if pred else []
        })
    return results

@app.post("/customers")
async def create_customer(req: CustomerCreate, company_id: str = Depends(get_current_company)):
    company = db_get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    customer_id = str(uuid.uuid4())
    customer_record = {
        "id": customer_id,
        "company_id": company_id,
        "external_ref": req.external_ref,
        "name": req.name,
        "features": req.features,
        "email": req.email or f"{req.name.lower().replace(' ', '.')}@example.com",
        "phone": req.phone or "+15550192834",
        "last_active_at": "Just now",
        "created_at": datetime.utcnow().isoformat()
    }
    DB_CUSTOMERS[customer_id] = customer_record

    prediction = _score_customer(company["sector"], req.features)
    prediction_record = {**prediction, "customer_id": customer_id, "predicted_at": datetime.utcnow().isoformat()}
    DB_PREDICTIONS[customer_id] = prediction_record

    log_audit_event(
        company_id=company_id,
        action_type="CUSTOMER_CREATED",
        entity_affected=customer_id,
        new_state={"name": req.name, "risk_score": prediction["risk_score"]}
    )

    # Process notifications if risk is high
    triggered_notifs = process_churn_notifications(company_id, customer_record, prediction_record)

    # Broadcast WebSockets real-time update
    event_payload = {
        "type": "CUSTOMER_CREATED",
        "customer_id": customer_id,
        "name": req.name,
        "external_ref": req.external_ref,
        "prediction": prediction_record,
        "notifications_triggered": len(triggered_notifs)
    }
    await manager.broadcast_to_company(company_id, event_payload)

    return {"customer_id": customer_id, "prediction": prediction_record, "notifications": triggered_notifs}

@app.post("/customers/{customer_id}/telemetry")
async def update_customer_telemetry(customer_id: str, req: CustomerTelemetryUpdate, company_id: str = Depends(get_current_company)):
    customer = DB_CUSTOMERS.get(customer_id)
    if not customer or customer["company_id"] != company_id:
        raise HTTPException(404, "Customer not found")

    company = db_get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    prev_prediction = DB_PREDICTIONS.get(customer_id, {})
    prev_score = prev_prediction.get("risk_score")

    # Update features
    customer["features"].update(req.features)
    customer["last_active_at"] = "Just now"

    # Re-calculate real-time prediction
    prediction = _score_customer(company["sector"], customer["features"])
    prediction_record = {**prediction, "customer_id": customer_id, "predicted_at": datetime.utcnow().isoformat()}
    DB_PREDICTIONS[customer_id] = prediction_record

    log_audit_event(
        company_id=company_id,
        action_type="REALTIME_TELEMETRY_UPDATED",
        entity_affected=customer_id,
        previous_state={"risk_score": prev_score},
        new_state={"risk_score": prediction["risk_score"], "updated_features": req.features}
    )

    # Notification check
    triggered_notifs = process_churn_notifications(company_id, customer, prediction_record)

    # Broadcast real-time score update via WebSockets
    event_payload = {
        "type": "PREDICTION_UPDATED",
        "customer_id": customer_id,
        "name": customer["name"],
        "previous_score": prev_score,
        "prediction": prediction_record,
        "notifications_triggered": len(triggered_notifs)
    }
    await manager.broadcast_to_company(company_id, event_payload)

    return {"customer_id": customer_id, "prediction": prediction_record, "notifications": triggered_notifs}


# ------------------------------------------------------------------
# 4. Comprehensive Audit Logs API
# ------------------------------------------------------------------
@app.get("/audit-logs")
def get_audit_logs(
    action_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(15, ge=1, le=100),
    company_id: str = Depends(get_current_company)
):
    logs = [l for l in DB_AUDIT_LOGS if l["company_id"] == company_id]

    if action_type and action_type != "ALL":
        logs = [l for l in logs if l["action_type"] == action_type]

    if q:
        q_lower = q.lower()
        logs = [
            l for l in logs
            if q_lower in l["action_type"].lower()
            or q_lower in l["entity_affected"].lower()
            or q_lower in l["actor_id"].lower()
        ]

    total = len(logs)
    start = (page - 1) * limit
    end = start + limit
    paginated_logs = logs[start:end]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total > 0 else 1,
        "logs": paginated_logs
    }


# ------------------------------------------------------------------
# 5. Multi-Channel Notifications API
# ------------------------------------------------------------------
@app.get("/notifications/history")
def get_notification_history(company_id: str = Depends(get_current_company)):
    logs = [l for l in DB_NOTIFICATION_LOGS if l["company_id"] == company_id]
    return logs

@app.get("/notifications/settings")
def read_notification_settings(company_id: str = Depends(get_current_company)):
    return get_notification_settings(company_id)

@app.post("/notifications/settings")
def update_notification_settings(req: NotificationSettingsUpdate, company_id: str = Depends(get_current_company)):
    settings = get_notification_settings(company_id)
    prev_state = dict(settings)

    if req.high_risk_threshold is not None:
        settings["high_risk_threshold"] = req.high_risk_threshold
    if req.email_enabled is not None:
        settings["email_enabled"] = req.email_enabled
    if req.sms_enabled is not None:
        settings["sms_enabled"] = req.sms_enabled
    if req.cooling_off_hours is not None:
        settings["cooling_off_hours"] = req.cooling_off_hours
    if req.email_recipient is not None:
        settings["email_recipient"] = req.email_recipient
    if req.sms_recipient is not None:
        settings["sms_recipient"] = req.sms_recipient

    log_audit_event(
        company_id=company_id,
        action_type="NOTIFICATION_SETTINGS_UPDATED",
        entity_affected="notification_settings",
        previous_state=prev_state,
        new_state=settings
    )

    return settings

@app.post("/notifications/send-manual")
def send_manual_notification(req: ManualNotificationRequest, company_id: str = Depends(get_current_company)):
    customer = DB_CUSTOMERS.get(req.customer_id)
    customer_name = req.customer_name or (customer["name"] if customer else req.customer_id)
    settings = get_notification_settings(company_id)

    logs = []
    for ch in req.channels:
        log_entry = {
            "id": str(uuid.uuid4()),
            "company_id": company_id,
            "customer_id": req.customer_id,
            "customer_name": customer_name,
            "channel": ch.lower(),
            "recipient": settings.get("email_recipient", "retention-team@company.com") if ch.lower() == "email" else settings.get("sms_recipient", "+15550192834"),
            "subject": req.subject,
            "body": req.body,
            "status": "SENT",
            "triggered_score": 85.0,
            "sent_at": datetime.utcnow().isoformat()
        }
        
        if ch.lower() == "email":
            success, response_msg = send_resend_email(log_entry["recipient"], log_entry["subject"], log_entry["body"])
            if not success:
                log_entry["status"] = f"FAILED: {response_msg}"
        elif ch.lower() == "sms":
            success, response_msg = send_twilio_sms(log_entry["recipient"], log_entry["body"])
            if not success:
                log_entry["status"] = f"FAILED: {response_msg}"
                
        DB_NOTIFICATION_LOGS.insert(0, log_entry)
        logs.append(log_entry)

    log_audit_event(
        company_id=company_id,
        action_type="MANUAL_NOTIFICATION_DISPATCHED",
        entity_affected=req.customer_id,
        new_state={"customer_name": customer_name, "channels": req.channels, "subject": req.subject}
    )

    return {"status": "success", "logs": logs, "message": f"Notification delivered to {customer_name}"}

@app.post("/notifications/dispatch-bulk")
def dispatch_bulk_notifications(req: BulkNotificationRequest, company_id: str = Depends(get_current_company)):
    logs = []
    settings = get_notification_settings(company_id)

    for cust_id in req.customer_ids:
        customer = DB_CUSTOMERS.get(cust_id)
        cust_name = customer["name"] if customer else cust_id

        for ch in req.channels:
            log_entry = {
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "customer_id": cust_id,
                "customer_name": cust_name,
                "channel": ch.lower(),
                "recipient": customer.get("email") if (ch == "email" and customer) else (settings.get("email_recipient", "retention-team@company.com") if ch.lower() == "email" else settings.get("sms_recipient", "+15550192834")),
                "subject": req.subject.replace("{{name}}", cust_name).replace("{{customer_name}}", cust_name),
                "body": req.body.replace("{{name}}", cust_name).replace("{{customer_name}}", cust_name),
                "status": "SENT",
                "triggered_score": 85.0,
                "sent_at": datetime.utcnow().isoformat()
            }
            
            if ch.lower() == "email":
                success, response_msg = send_resend_email(log_entry["recipient"], log_entry["subject"], log_entry["body"])
                if not success:
                    log_entry["status"] = f"FAILED: {response_msg}"
            elif ch.lower() == "sms":
                success, response_msg = send_twilio_sms(log_entry["recipient"], log_entry["body"])
                if not success:
                    log_entry["status"] = f"FAILED: {response_msg}"
            
            DB_NOTIFICATION_LOGS.insert(0, log_entry)
            logs.append(log_entry)

    log_audit_event(
        company_id=company_id,
        action_type="BULK_NOTIFICATION_DISPATCHED",
        entity_affected=f"{len(req.customer_ids)} customers",
        new_state={"count": len(req.customer_ids), "customer_ids": req.customer_ids, "channels": req.channels, "subject": req.subject}
    )

    return {"status": "success", "dispatched_count": len(req.customer_ids), "logs": logs}

# ------------------------------------------------------------------
# 5b. File Upload History & Storage API
# ------------------------------------------------------------------
@app.get("/files/history")
def get_file_history(company_id: str = Depends(get_current_company)):
    files = [f for f in DB_FILE_UPLOADS if f.get("company_id") == company_id]
    return files

@app.post("/files/upload")
def upload_file_record(req: FileUploadRecord, company_id: str = Depends(get_current_company)):
    file_id = req.id or f"FILE-{uuid.uuid4().hex[:6].upper()}"
    file_entry = {
        "id": file_id,
        "company_id": company_id,
        "name": req.name,
        "uploader": req.uploader or "admin@company.com",
        "timestamp": req.timestamp or datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
        "size": req.size or "1.2 MB",
        "status": req.status or "Processed",
        "recordCount": req.recordCount or 28
    }
    DB_FILE_UPLOADS.insert(0, file_entry)

    log_audit_event(
        company_id=company_id,
        action_type="FILE_DATASET_UPLOADED",
        entity_affected=req.name,
        new_state={"file_id": file_id, "size": req.size, "record_count": req.recordCount}
    )

    return {"status": "success", "file": file_entry}

@app.delete("/files/{file_id}")
def delete_file_record(file_id: str, company_id: str = Depends(get_current_company)):
    global DB_FILE_UPLOADS
    target = next((f for f in DB_FILE_UPLOADS if f["id"] == file_id and f.get("company_id") == company_id), None)
    if not target:
        raise HTTPException(404, "File record not found")
    
    DB_FILE_UPLOADS = [f for f in DB_FILE_UPLOADS if not (f["id"] == file_id and f.get("company_id") == company_id)]

    log_audit_event(
        company_id=company_id,
        action_type="FILE_DATASET_DELETED",
        entity_affected=file_id,
        previous_state=target
    )

    return {"status": "success", "message": f"File {file_id} deleted"}

@app.post("/notifications/trigger-test")
def trigger_test_notification(customer_id: str, company_id: str = Depends(get_current_company)):
    customer = DB_CUSTOMERS.get(customer_id)
    if not customer or customer["company_id"] != company_id:
        raise HTTPException(404, "Customer not found")

    pred = DB_PREDICTIONS.get(customer_id, {
        "risk_score": 88.5,
        "risk_band": "high",
        "reasons": ["Test notification trigger requested by Admin"],
        "ai_suggestions": ["Send immediate win-back discount"]
    })

    logs = process_churn_notifications(company_id, customer, pred)
    return {"status": "test_triggered", "logs": logs}


# ------------------------------------------------------------------
# 6. Admin AI Strategic Assistant (Chatbot API)
# ------------------------------------------------------------------
@app.post("/ai/chat")
async def ai_chat_assistant(req: AIChatRequest, company_id: str = Depends(get_current_company)):
    """AI Assistant endpoint that injects live DB metric context into query reasoning."""
    user_query = req.message.strip()
    company = db_get_company(company_id) or {"name": "Your Company", "sector": "ecommerce"}
    
    customers = [c for c in DB_CUSTOMERS.values() if c["company_id"] == company_id]
    predictions = [DB_PREDICTIONS[c["id"]] for c in customers if c["id"] in DB_PREDICTIONS]
    high_risk_customers = [c for c in customers if DB_PREDICTIONS.get(c["id"], {}).get("risk_band") == "high"]
    avg_risk = round(sum(p["risk_score"] for p in predictions) / len(predictions), 1) if predictions else 0.0

    # Aggregate top reasons across high risk customers
    reason_counts: Dict[str, int] = {}
    for p in predictions:
        for r in p.get("reasons", []):
            reason_counts[r] = reason_counts.get(r, 0) + 1
    top_reasons_sorted = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]

    # Specific Customer Context if mentioned
    target_customer = None
    if req.customer_id:
        target_customer = DB_CUSTOMERS.get(req.customer_id)
    else:
        # Check if name is mentioned in user_query
        for c in customers:
            if c["name"].lower() in user_query.lower() or c["external_ref"].lower() in user_query.lower():
                target_customer = c
                break

    query_lower = user_query.lower()

    log_audit_event(
        company_id=company_id,
        action_type="AI_ASSISTANT_QUERIED",
        entity_affected="ai_strategic_assistant",
        new_state={"query": user_query}
    )

    # 1. Query: Count at risk
    if "how many" in query_lower and ("risk" in query_lower or "churn" in query_lower):
        reply = (
            f"📊 **At-Risk Customer Summary for {company['name']}**:\n\n"
            f"- **Currently Monitored**: `{len(customers)}` total customers.\n"
            f"- **High Risk of Churn (>70%)**: `{len(high_risk_customers)}` customers.\n"
            f"- **Average Churn Risk**: `{avg_risk}%` across your customer base.\n\n"
            f"Would you like me to draft an automated win-back campaign for the `{len(high_risk_customers)}` high-risk customers?"
        )
        return {"response": reply, "context": {"high_risk_count": len(high_risk_customers), "total": len(customers)}}

    # 2. Query: Top reasons for churning
    if "reasons" in query_lower or "why" in query_lower or "top reasons" in query_lower:
        reasons_md = "\n".join([f"{i+1}. **{r[0]}** — affecting `{r[1]}` customer(s)" for i, r in enumerate(top_reasons_sorted)]) if top_reasons_sorted else "No major churn reasons recorded yet."
        reply = (
            f"🔍 **Top Churn Drivers for {company['name']} ({company['sector'].upper()})**:\n\n"
            f"{reasons_md}\n\n"
            f"💡 **Strategic Recommendation**: Addressing the #1 factor above can reduce overall churn by an estimated **15–22%** this month."
        )
        return {"response": reply, "context": {"top_reasons": top_reasons_sorted}}

    # 3. Query: Customer specific actions
    if target_customer or "stop customer" in query_lower or "action" in query_lower:
        c = target_customer or (high_risk_customers[0] if high_risk_customers else (customers[0] if customers else None))
        if c:
            pred = DB_PREDICTIONS.get(c["id"], {})
            score = pred.get("risk_score", 85.0)
            reasons_list = pred.get("reasons", ["High inactivity", "Cart dropoff"])
            suggestions = pred.get("ai_suggestions", ["Send immediate win-back discount", "Offer free shipping", "Reach out via priority support"])

            suggestions_md = "\n".join([f"- ✅ **Action {i+1}**: {s}" for i, s in enumerate(suggestions)])
            reasons_md = "\n".join([f"- ⚠️ {r}" for r in reasons_list])

            reply = (
                f"🎯 **Targeted Retention Strategy for {c['name']} (ID: `{c['external_ref']}`)**:\n\n"
                f"• **Predicted Churn Probability**: `{score}%` (`{pred.get('risk_band', 'High').upper()}` Risk)\n\n"
                f"**Key Behavioral Triggers**:\n{reasons_md}\n\n"
                f"**Recommended Action Plan**:\n{suggestions_md}\n\n"
                f"⚡ *Tip: You can send a 1-click notification trigger from the Notifications tab.*"
            )
            return {"response": reply, "context": {"customer_id": c["id"], "score": score}}

    # Default Intelligent Strategy Response
    reply = (
        f"🤖 **Vitals AI Strategic Assistant — {company['name']} Dashboard**\n\n"
        f"I have live access to your company metrics (`{len(customers)}` monitored customers, `{len(high_risk_customers)}` high risk, avg risk `{avg_risk}%`).\n\n"
        f"Here are quick questions you can ask me:\n"
        f"- *'How many customers are currently at risk of churn?'*\n"
        f"- *'Show me a summary of the top reasons customers are churning this month.'*\n"
        f"- *'What specific actions can we take to stop Customer X from leaving?'*\n\n"
        f"How can I assist your retention workflow today?"
    )
    return {"response": reply, "context": {"total": len(customers), "avg_risk": avg_risk}}


# ------------------------------------------------------------------
# 7. Real-Time WebSockets Endpoint
# ------------------------------------------------------------------
@app.websocket("/ws/churn-updates")
async def websocket_churn_updates(websocket: WebSocket, token: Optional[str] = Query(None)):
    if not token:
        await websocket.close(code=1008)
        return
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        company_id = payload["company_id"]
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, company_id)
    try:
        # Send initial welcome & baseline status
        await websocket.send_json({
            "type": "CONNECTED",
            "message": "Connected to Vitals Real-Time Churn Telemetry Stream",
            "timestamp": datetime.utcnow().isoformat()
        })
        while True:
            # Keep-alive receive loop
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "PONG", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(websocket, company_id)


# ------------------------------------------------------------------
# Model Inference & Action Helper
# ------------------------------------------------------------------
def _score_customer(sector: str, features: dict) -> dict:
    result = predict_churn(sector, features)
    result["ai_suggestions"] = _suggest_actions(sector, result["risk_band"])
    return result

def _suggest_actions(sector: str, band: str) -> List[str]:
    actions = {
        "ecommerce": {
            "high": ["Send a personalized win-back discount (15-20%)", "Trigger cart-recovery email within 2 hours", "Offer free shipping on next order"],
            "medium": ["Send a curated restock reminder", "A/B test a loyalty-points bonus"],
            "low": ["Continue current engagement cadence", "Invite to referral program"],
        },
        "shopping_app": {
            "high": ["Re-permission push notifications with a value prompt", "Send a limited-time in-app offer banner", "Simplify checkout flow"],
            "medium": ["Surface wishlist items with a price-drop alert", "Gamify next visit with an incentive"],
            "low": ["Maintain personalized recommendations", "Offer early access to new drops"],
        },
        "ott": {
            "high": ["Prompt to resume an abandoned series with a recap", "Offer a discounted plan tier before renewal", "Flag and resolve payment method issue"],
            "medium": ["Recommend trending titles in watched genres", "Highlight a limited-time exclusive premiere"],
            "low": ["Continue tailored recommendations", "Invite to early-access previews"],
        },
        "telecom": {
            "high": ["Escalate to network team & offer bonus data top-up", "Send recharge reminder with 20% discount", "Schedule priority retention call"],
            "medium": ["Offer personalized data-pack upgrade", "Highlight zero-drop family plans"],
            "low": ["Maintain standard loyalty rewards", "Offer handset upgrade preview"],
        },
        "banking": {
            "high": ["Assign dedicated relationship manager check-in", "Offer preferential FD / Credit Card rate", "Waive annual account service fees"],
            "medium": ["Nudge with cashback card incentive", "Offer automated savings tool"],
            "low": ["Send monthly wealth summary", "Invite to private advisory webinar"],
        },
        "insurance": {
            "high": ["Assign claims specialist to review rejected claim", "Send policy renewal discount voucher", "Proactive outreach from senior manager"],
            "medium": ["Offer bundled multi-policy discount", "Grace-period extension notice"],
            "low": ["Provide annual health checkup perk", "Send claim-free bonus certificate"],
        },
        "jobportals": {
            "high": ["Boost profile visibility in recruiter searches", "Send targeted top-matching job alerts", "Discounted 1-month Premium membership"],
            "medium": ["Prompt profile completion for 2x views", "Free resume review report"],
            "low": ["Regular weekly digest", "Career growth webinar invite"],
        },
        "utilities": {
            "high": ["Offer flexible installment payment plan", "Assign utility usage auditor", "Waive late payment surcharge"],
            "medium": ["Offer auto-pay cashback incentive", "Send smart usage report"],
            "low": ["Send quarterly green energy report", "Community paperless reward"],
        }
    }
    sec_actions = actions.get(sector, actions["ecommerce"])
    return sec_actions.get(band, sec_actions["high"])


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
