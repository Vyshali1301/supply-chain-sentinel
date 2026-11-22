# SupplyChain Sentinel — Autonomous Disruption Response & Impact Intelligence System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/framework-Flask-black.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/database-SQLite%203-003B57.svg)](https://www.sqlite.org/)
[![Google Gemini API](https://img.shields.io/badge/AI-Google%20Gemini%202.5-4285F4.svg)](https://ai.google.dev/)
[![Tests](https://img.shields.io/badge/tests-pytest%2016%2F16%20passed-brightgreen.svg)](tests/test_sentinel.py)

**SupplyChain Sentinel** is an enterprise supply-chain intelligence and autonomous decision-support system. It bridges the gap between unstructured disruption alerts (supplier emails, carrier notices, WhatsApp messages, logistics updates) and operational ERP/WMS databases.

Rather than assuming every reported supplier delay causes an enterprise emergency, SupplyChain Sentinel deterministically analyzes warehouse inventory on hand, inbound shipment schedules, safety stock thresholds, and pending customer delivery commitments to calculate true business impact and formulate dynamic, cost-quantified mitigation plans.

---

## Architecture Overview

```
                      +---------------------------------------+
                      |   Unstructured Disruption Intake      |
                      |   (Emails, Carrier Alerts, Notices)   |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |       Information Extraction          |
                      |  - Gemini 2.5 Structured JSON Schema  |
                      |  - Deterministic Regex/Rule Fallback  |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |      Cross-Reference & Validation     |
                      |  - Suppliers & Product SKU Matching   |
                      |  - Active Inbound Shipment Matching   |
                      |  - Conflict & Contradiction Detection |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |   Deterministic Allocation Engine     |
                      |  - Strict FIFO Order Queue Allocation |
                      |  - Partial Fulfillment Tracking       |
                      |  - Contract Unit Price Exposure (INR) |
                      |  - Temporal ETA & Delay Calendar Math |
                      |  - Safety Stock Buffer Preservation   |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |      Dynamic Mitigation Engine        |
                      |  - Air Expedite Surcharge Model       |
                      |  - Real Stock Reallocation Logic      |
                      |  - Cost-to-Risk Tradeoff Ratios       |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |    Human-in-the-Loop Decision State   |
                      |  - Approval: Real Operational Actions |
                      |  - State Updates & Activity Auditing  |
                      +---------------------------------------+
```

---

## Core Technical Improvements & Engineering Rigor

### 1. Security & Hardening
- **SQL Injection Prevention:** Fixed vulnerable dynamic SQL formatting in `/api/data/update` by enforcing strict server-side table and column whitelists.
- **Relational Integrity:** Explicitly enabled SQLite foreign key constraints (`PRAGMA foreign_keys = ON;`) across all connection handles.
- **Production Configuration:** Disabled Flask debug mode by default (`FLASK_DEBUG=false`), with secure environment-based overrides.
- **Centralized Error Handling:** All API endpoints return structured JSON errors with consistent HTTP status codes (400, 404, 500).

### 2. Relational Database & Inventory Synchronization
- **Multi-Shipment Tracking:** Supports multiple active inbound shipments for the same product and supplier, matching exact shipment tracking codes, active status, or earliest expected delivery date.
- **Atomic Stock Synchronization:** Implemented atomic stock adjustments (`adjust_inventory_stock()` and `sync_product_inventory()`) so warehouse-level `inventory.quantity_on_hand` and master `products.current_stock` never drift.
- **Idempotent Disruption Evaluation:** In-place recalculation for existing disruptions prevents duplicate rows upon goods receipt or order fulfillment.

### 3. Deterministic Order Allocation & Financial Exposure
- **Strict FIFO Queue:** Orders are allocated based on `ORDER BY expected_ship_date ASC, order_date ASC, id ASC`.
- **Partial Fulfillment Awareness:** Recognizes previously fulfilled units (`quantity_ordered - quantity_fulfilled`) to compute true pending demand.
- **Actual Contract Pricing:** Multiplies shortages by the customer's negotiated order `unit_price`, avoiding misleading catalog-average pricing.
- **Temporal Schedule Math:** Computes revised delivery dates from calendar offsets (`expected_delivery_date + delay_days`) and compares them against promised customer delivery windows.
- **Safety Stock Buffer Analysis:** Distinguishes between zero-shortage scenarios that deplete safety stock versus those that maintain safe inventory reserves.

### 4. Dynamic Mitigation & Closed-Loop Execution
- **Zero Hardcoded Cost Literals:** Removed all hardcoded string figures (`₹3,50,000`, `0.82%`, `₹4,27,50,000`, etc.).
- **Parametric Freight Model:** Dynamic logistics model computes air expedite costs, customs fees, and cost-to-risk ratios from actual shortage quantities.
- **Closed-Loop Decision Workflow:** Clicking **Approve**, **Modify**, or **Reject** triggers verified operational state transitions in the database:
  - *Expedite Air:* Updates inbound shipment status to `In Transit (Expedited Air)`, recalculates ETA, persists mitigation cost, assigns simulated air tracking (`[Simulated Air Cargo]`), and protects customer SLAs.
  - *Mitigation Lifecycle Separation:* Approving a strategy marks it `In Progress` (`is_active = 1`), preserving auditability. Disruption resolution only occurs upon physical goods receipt/order fulfillment (`is_active = 0`, `resolved_at = timestamp`, `mitigation_status = 'Resolved'`).
  - *Idempotency & Safety:* Prevents duplicate mitigation executions; rolls back database transactions on failure.
  - *Reject:* Discards mitigation, recording reasons and timestamp.

### 5. Grounded AI Integration (Google Gemini)
- **Structured Schema Extraction:** Uses Google Gemini with structured Pydantic JSON output to extract supplier, product, claimed quantity, delay days, and disruption reasons.
- **Resilient Fallback:** Automatically falls back to deterministic rule-based NLP extraction if API keys are missing, network calls fail, or malformed JSON is returned.
- **Grounded Assistant (`/api/qa`):** Answers operations inquiries using live database queries for orders, shipments, inventory, and active disruptions. Refuses out-of-domain questions with an explicit insufficient data disclaimer.

### 6. Responsive Frontend SPA
- **Zero Demo Text Artifacts:** Removed misleading hardcoded alert banners from the UI template.
- **Dynamic Metric Synchronization:** Executive dashboard numbers, disruption summaries, and audit logs are powered directly by backend APIs.
- **Responsive Layout:** Complete CSS Grid and Flexbox responsiveness with `@media` breakpoints for desktop, tablet, and mobile devices, including a collapsible mobile navigation drawer.

---

## Directory Structure

```
supply-chain-sentinel/
├── app.py                  # Flask application & REST API endpoints
├── database.py             # SQLite schema, migrations, connection pool & seed data
├── engine.py               # Deterministic FIFO allocation, Gemini NLP & dynamic mitigation
├── verify_all.py           # Verification script for hackathon demonstration scenarios
├── requirements.txt        # Python dependency manifest
├── .env.example            # Template for environment configuration
├── .gitignore              # Git ignore rules
├── static/
│   ├── app.js              # Single Page Application controller & Chart.js logic
│   └── styles.css          # Responsive dark-theme enterprise design
├── templates/
│   └── index.html          # Clean dashboard UI markup
└── tests/
    └── test_sentinel.py    # Automated test suite (16 pytest cases)
```

---

## Quickstart & Installation

### Prerequisites
- Python 3.10, 3.11, or 3.12
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/Vyshali1301/supply-chain-sentinel.git
cd supply-chain-sentinel
```

### 2. Create a Virtual Environment & Install Dependencies
```bash
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to configure:
```env
# Optional: Set your Gemini API key for live LLM extraction.
# If omitted, Sentinel runs deterministically using built-in rule extractors.
GEMINI_API_KEY=your_gemini_api_key_here

PORT=8000
HOST=127.0.0.1
FLASK_DEBUG=false
```

### 4. Initialize Database
Initialize the database with the enterprise catalog, multi-warehouse inventory, and active customer orders:
```bash
python database.py
```

### 5. Launch Application
```bash
python app.py
```
Open your browser and navigate to: **`http://localhost:8000`**

---

## Automated Test Suite

SupplyChain Sentinel includes a comprehensive automated test suite covering database integrity, SQL injection prevention, FIFO allocation, partial fulfillment, multiple shipments, and grounded QA.

Run all tests via pytest:
```bash
pytest tests/test_sentinel.py -v
```

### Test Suite Coverage (16 Automated Tests):
| Test Name | Verification Focus |
|---|---|
| `test_database_foreign_keys_enabled` | Enforces SQLite foreign keys (`PRAGMA foreign_keys = 1`) |
| `test_inventory_atomic_adjustment` | Verifies atomic sync between `inventory` and `products` |
| `test_sql_injection_prevention` | Confirms unauthorized table and column updates are rejected (HTTP 400) |
| `test_disruption_impact_and_fifo_order_allocation` | Verifies FIFO order allocation and exposure calculations |
| `test_disruption_no_business_impact` | Tests buffer retention and NO IMPACT status detection |
| `test_disruption_contradiction_detection` | Validates contradiction detection on supplier mismatch and quantity variance |
| `test_multiple_shipments_resolution` | Tests matching of specific active shipments among multiple in transit |
| `test_partial_receiving_and_in_place_recalculation` | Confirms partial goods receipt reduces net shortage in place |
| `test_customer_order_partial_fulfillment` | Ensures fulfilled order quantities are subtracted from demand |
| `test_human_decision_option1_mitigation_lifecycle` | Validates Option 1 approval, persisted cost, revised air ETA, and customer SLA protection |
| `test_duplicate_approval_prevention_idempotency` | Verifies duplicate approvals return idempotent status without duplicate activity logs |
| `test_transaction_rollback_and_validation` | Verifies transaction rollback on validation failure and error responses |
| `test_impact_trace_and_data_consistency` | Verifies consistency between master data, shipment dropdown, and Impact Trace |
| `test_genuine_disruption_resolution_upon_goods_receipt` | Verifies disruption is resolved only when inbound receipt eliminates shortage |
| `test_operations_assistant_grounded_qa` | Tests grounded Q&A responses and out-of-domain disclaimers |
| `test_dashboard_metrics` | Verifies accuracy of executive financial and inventory metrics |

You can also run the verification script:
```bash
python verify_all.py
```

---

## REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web Application Command Center UI |
| `GET` | `/api/dashboard` | Executive KPIs, stock valuation, and 30-day sales analytics |
| `GET` | `/api/data` | Master datasets (products, suppliers, inventory, shipments, orders, disruptions) |
| `POST` | `/api/data/update` | Whitelisted cell-level record updater (`table`, `id`, `field`, `value`) |
| `POST` | `/api/data/orders` | Create a new customer order and trigger dynamic impact checks |
| `POST` | `/api/disruptions/report` | Process disruption message, match records, and generate assessment |
| `GET` | `/api/disruptions/<id>` | Fetch detailed disruption record and evidence trace |
| `POST` | `/api/disruptions/<id>/decision` | Commit human operational decision (`decision`, optional `modified_action`, `notes`) |
| `POST` | `/api/qa` | Query the grounded operations assistant |
| `POST` | `/api/seed/reset` | Reset database to clean enterprise seed state |

---

## Transparent System Assumptions & Limitations

1. **Database Architecture:** SupplyChain Sentinel currently uses SQLite with foreign key enforcement and timeout protections. For high-concurrency multi-tenant enterprise deployments, migrate to PostgreSQL.
2. **Logistics Rate Modeling:** When live freight APIs (e.g., Freightos, project44) are not connected, the dynamic mitigation engine relies on transparent baseline formulas (₹650/unit air freight + ₹25,000 priority customs surcharge) clearly labeled as estimates.
3. **LLM Output Boundary:** LLM extractions from Google Gemini are strictly sandboxed as informational candidates. They are cross-referenced and validated against database master tables before any mathematical calculation occurs. Under no circumstances can an LLM directly mutate ERP records.

---

## License
MIT License. Developed for enterprise supply chain visibility and disruption response.
