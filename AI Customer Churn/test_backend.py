"""
test_backend.py — Backend Integration Test Suite for Vitals Platform
"""

import asyncio
from httpx import AsyncClient, ASGITransport
from main import app

async def run_async_tests():
    print("Running Vitals Backend Integration Tests...")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health check
        res = await client.get("/health")
        assert res.status_code == 200, f"Health check failed: {res.text}"
        print("[OK] Health check passed")

        # 2. Company registration
        reg_data = {
            "company_name": "Test Enterprise",
            "sector": "ecommerce",
            "email": "admin@testenterprise.com",
            "password": "password123"
        }
        res = await client.post("/auth/register", json=reg_data)
        assert res.status_code == 200, f"Registration failed: {res.text}"
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[OK] Registration and JWT generation passed")

        # 3. Create customer & score prediction
        cust_data = {
            "external_ref": "CUST-999",
            "name": "Alex Mercer",
            "features": {
                "cart_abandon_rate": 0.85,
                "days_since_last_purchase": 55,
                "order_frequency_30d": 0.2,
                "avg_order_value_trend": -0.4,
                "promo_email_open_rate": 0.02
            }
        }
        res = await client.post("/customers", json=cust_data, headers=headers)
        assert res.status_code == 200, f"Customer creation failed: {res.text}"
        cust_id = res.json()["customer_id"]
        pred = res.json()["prediction"]
        assert pred["risk_score"] > 70, f"Expected high risk score, got {pred['risk_score']}"
        print(f"[OK] Customer creation and ML scoring passed (Risk Score: {pred['risk_score']}%)")

        # 4. Audit Logs API verification
        res = await client.get("/audit-logs", headers=headers)
        assert res.status_code == 200, f"Audit logs failed: {res.text}"
        logs = res.json()["logs"]
        assert len(logs) >= 2, "Expected audit logs for registration and customer creation"
        print(f"[OK] Audit logs system passed ({len(logs)} logs captured)")

        # 5. Multi-channel Notifications verification
        res = await client.get("/notifications/history", headers=headers)
        assert res.status_code == 200, f"Notification history failed: {res.text}"
        notifs = res.json()
        assert len(notifs) >= 1, "Expected automated high-risk churn notifications triggered"
        print(f"[OK] Automated churn notifications dispatcher passed ({len(notifs)} alerts logged)")

        # 6. Real-Time Telemetry Customer Score Update
        update_data = {
            "features": {"cart_abandon_rate": 0.92, "days_since_last_purchase": 45}
        }
        res = await client.post(f"/customers/{cust_id}/telemetry", json=update_data, headers=headers)
        assert res.status_code == 200, f"Customer telemetry prediction update failed: {res.text}"
        print("[OK] Real-time customer telemetry update & score calculation passed")

        # 6b. Manual Notification Dispatch API
        manual_notif_payload = {
            "customer_id": cust_id,
            "customer_name": "Alex Mercer",
            "channels": ["email", "sms"],
            "subject": "Exclusive 15% Win-Back Offer for Alex Mercer!",
            "body": "Hi Alex Mercer, here is a 15% discount code RETENTION15."
        }
        res = await client.post("/notifications/send-manual", json=manual_notif_payload, headers=headers)
        assert res.status_code == 200, f"Manual notification dispatch failed: {res.text}"
        print("[OK] Manual customer notification dispatch passed")

        # 6c. Bulk Notification Dispatch API
        bulk_notif_payload = {
            "customer_ids": [cust_id, "EC-1001", "EC-1002"],
            "channels": ["email", "sms"],
            "subject": "Plan Renewal Reminder for {{name}}",
            "body": "Dear {{name}}, your plan is expiring soon."
        }
        res = await client.post("/notifications/dispatch-bulk", json=bulk_notif_payload, headers=headers)
        assert res.status_code == 200, f"Bulk notification dispatch failed: {res.text}"
        assert res.json()["dispatched_count"] == 3
        print("[OK] Bulk customer notification dispatch passed")

        # 7. Admin AI Strategic Assistant Chatbot API
        chat_queries = [
            "How many customers are currently at risk of churn?",
            "Show me a summary of the top reasons customers are churning this month.",
            "What specific actions can we take to stop Alex Mercer from leaving?"
        ]
        for q in chat_queries:
            res = await client.post("/ai/chat", json={"message": q}, headers=headers)
            assert res.status_code == 200, f"AI Chat query failed for '{q}': {res.text}"
            response_text = res.json()["response"]
            assert len(response_text) > 20, "Expected non-empty AI assistant response"
            print(f"[OK] AI Strategic Assistant answered query: '{q[:35]}...'")

        # 8. File Upload History & Storage API
        file_payload = {
            "name": "test_dataset_q3.csv",
            "uploader": "admin@company.com",
            "size": "1.5 MB",
            "status": "Processed",
            "recordCount": 50
        }
        res = await client.post("/files/upload", json=file_payload, headers=headers)
        assert res.status_code == 200, f"File record upload failed: {res.text}"
        uploaded_file_id = res.json()["file"]["id"]

        res = await client.get("/files/history", headers=headers)
        assert res.status_code == 200, f"Get file history failed: {res.text}"
        assert len(res.json()) >= 1, "Expected file history list to contain uploaded record"

        res = await client.delete(f"/files/{uploaded_file_id}", headers=headers)
        assert res.status_code == 200, f"File deletion failed: {res.text}"
        print("[OK] File Upload History & Storage API passed")

    print("\nALL FEATURE BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_async_tests())
