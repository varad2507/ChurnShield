# 📊 ChurnSheild — AI Customer Churn Prediction System

** ChurnSheild** is an end-to-end machine learning web application built to predict customer churn probability across three distinct business domains: **E-Commerce**, **OTT Streaming Platforms**, and **Shopping Apps**[cite: 1]. The platform features high-performance FastAPI REST endpoints[cite: 1], pre-trained Scikit-learn classification models[cite: 1], and a responsive React analytical dashboard[cite: 1].

---

## 🚀 Key Features

* **Multi-Domain ML Inference:** Specialized Scikit-learn models tailored to capture domain-specific churn signals[cite: 1]:
  * **E-Commerce:** Evaluates order frequencies, cart abandonments, and return rates[cite: 1].
  * **OTT Streaming:** Tracks watch time, login frequency, and subscription tiers[cite: 1].
  * **Shopping Apps:** Analyzes session duration, feature usage, and app engagement[cite: 1].
* **Real-Time Scoring Engine:** High-performance REST API built on FastAPI for real-time model predictions and feature validation[cite: 1].
* **Interactive Analytical Dashboard:** Visualizes churn probability distribution, customer status flags, and key telemetry metrics using Chart.js and Tailwind CSS[cite: 1].
* **Automated Data Persistence:** Logs historical prediction runs, model outputs, and execution metrics into a lightweight SQLite database (`vitals_churn.db`)[cite: 1].
* **Executive PDF Reporting:** Includes printable summary templates (`vitals-dashboard.html`) for generating exportable churn reports[cite: 1].

---

## 🛠️ Tech Stack

### **Frontend**
* **Framework:** React 18 (JSX)[cite: 1]
* **Styling:** Tailwind CSS[cite: 1]
* **Data Visualization:** Chart.js[cite: 1]
* **Language:** JavaScript / HTML5[cite: 1]

### **Backend**
* **Language:** Python 3.10+[cite: 1]
* **Framework:** FastAPI[cite: 1]
* **Server:** Uvicorn[cite: 1]
* **Validation:** Pydantic[cite: 1]
* **Machine Learning:** Scikit-learn, Joblib, Pandas, NumPy[cite: 1]

### **Database & Security**
* **Database:** SQLite (`vitals_churn.db`)[cite: 1]
* **Schema Definition:** SQL (`schema.sql`)[cite: 1]
* **Security:** API Key Headers & CORS Middleware[cite: 1]

---

## 🏗️ System Architecture

```text
├── ChurnSheild<img width="1886" height="852" alt="Screenshot 2026-08-12 001240" src="https://github.com/user-attachments/assets/508d93ee-608b-4386-b6c9-f4315eae8c3a" />
<img width="1886" height="852" alt="Screenshot 2026-08-12 001240" src="https://github.com/user-attachments/assets/2975fb7d-cd6d-48a3-bc56-84e05aa9a4c1" />
/
│   ├── assets/                      # Dashboard UI assets & images[cite: 1]
│   ├── models/                      # Pre-trained ML models (.joblib)[cite: 1]
│   │   ├── ecommerce_model.joblib[cite: 1]
│   │   ├── ott_model.joblib[cite: 1]
│   │   └── shopping_app_model.joblib[cite: 1]
│   ├── churn-dashboard.jsx          # React Churn Dashboard Component[cite: 1]
│   ├── vitals-dashboard.html        # Interactive HTML Metrics Dashboard[cite: 1]
│   ├── main.py                      # FastAPI REST API Server[cite: 1]
│   ├── ml_model.py                  # Model Ingestion & Inference Logic[cite: 1]
│   ├── schema.sql                   # Database Schema Definition[cite: 1]
│   ├── vitals_churn.db              # SQLite Relational Database[cite: 1]
│   ├── test_backend.py              # Backend API Unit & Integration Tests[cite: 1]
│   └── requirements.txt             # Python Dependencies[cite: 1]
