TRACK_ID=PS08

# SupplyChain Sentinel - AI Supply Chain Disruption Response Assistant

SupplyChain Sentinel is an enterprise-grade command center designed for the **PS08 — Supply Chain Disruption Response Assistant** track. It bridges unstructured real-world logistics signals (emails, WhatsApp notices, news alerts, supplier reports) with structured enterprise database records.

It directly solves the core PS08 requirement:
> *"Matches vague disruption notes to actual system records, calculates which customer orders will slip, and creates a prioritized action plan with trade-offs."*

---

## 🎯 Core PS08 Pillars

1. **MATCH**:
   - Uses Gemini LLM to parse unstructured disruption text into structured entity attributes (Supplier Name, Product/SKU, Quantity, Delay Duration, Reason).
   - Cross-references extracted facts against local SQLite database tables with explicit source attribution tags (`Disruption Note`, `Database Supplier Master`, `Database Shipment Master`, `Warehouse Inventory Record`).
   - Performs **Contradiction & Conflict Detection**: Flags supplier mismatches, quantity discrepancies (>50 units), or missing product records, setting status to `NEEDS VERIFICATION` and pausing automated execution until verified.

2. **IMPACT**:
   - **100% Deterministic Python Calculation Engine** (Zero LLM numerical hallucinations).
   - Computes exact stock shortages, FIFO customer order allocation, promised ship date delays, and order values at risk in **Indian Rupees (₹ INR)**.
   - Evaluates three primary statuses:
     - `NO IMPACT`: When stock on hand completely satisfies open customer orders before shipment arrival. Shows explicit stock buffer calculation (`Stock On Hand - Open Demand = Buffer`).
     - `IMPACT DETECTED`: When stock shortfall causes customer order delays and revenue at risk.
     - `NEEDS VERIFICATION`: When safety checks flag data conflicts or missing master records.

3. **ACTION PLAN**:
   - Generates a grounded, prioritized response matrix with concrete Indian Rupee costs, orders protected, customer SLA impacts, key assumptions, and trade-off analyses:
     - **Option 1: Expedite Air Freight** (₹3,50,000 surcharge)
     - **Option 2: Split Shipment & Air Cargo Hybrid** (₹1,80,000)
     - **Option 3: Reallocate Stock & Prioritize VIP Accounts** (Grounded check: verifies if unreserved stock actually exists)
     - **Option 4: Accept Delay & Issue Delay Credit Vouchers** (5% credit voucher compensation)
   - Holds human decision-making in the loop with explicit approval controls (`Approve Action`, `Modify Strategy`, `Reject / Standby`).

---

## 🏗️ Architecture Overview

- **Backend**: Python 3 (Flask)
- **Database**: SQLite3 (`supply_chain.db`)
- **AI Integration**: Google Gemini API (`google-genai` / REST) with a robust rule-based NLP fallback engine for offline execution.
- **Frontend**: Glassmorphic SPA Dashboard (HTML5, Vanilla CSS, JS ES6, Chart.js).
- **Currency**: Indian Rupees (₹ INR) across database, calculations, and visual analytics.

---

## ⚡ Quick Setup & Launch

### 1. Prerequisites
- Python 3.10+
- (Optional) Gemini API Key set in environment

### 2. Environment Configuration
```bash
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_gemini_key if available
```

### 3. Installation & Server Start
```bash
pip install -r requirements.txt
python app.py
```
The application will start on **`http://localhost:8000`**.

---

## 💾 Database Schema

- `products`: SKU, Name, Category, Unit Cost (₹), Selling Price (₹), Current Stock, Safety Stock.
- `suppliers`: Code, Name, Email, Country, Reliability Rating.
- `inventory`: Warehouse Name, Quantity On Hand, Reserved Qty, Available Qty.
- `shipments`: Code, Supplier ID, Product ID, Quantity, Status, Origin, Destination, ETA.
- `customer_orders`: Order #, Customer Name, Product ID, Qty Ordered, Unit Price (₹), Total Price (₹), Expected Ship Date, Status.
- `sales`: Sales history records for daily/weekly/monthly analytics.
- `disruptions`: Raw notice, extracted JSON, status, impact summary, evidence, trace graph, human decision.

---

## 🧪 Hackathon Demonstration Scenarios

1. **Scenario A (Impact Detected)**:
   - Input: *"ABC supplier informed us that 500 Laptop X units will be delayed by 5 days because of a transportation problem."*
   - Outcome: `IMPACT DETECTED`. Shortage: 450 units. Order Value at Risk: ₹4,27,50,000 (₹4.275 Crore) across customer orders `ORD-901` and `ORD-902`.

2. **Scenario B (NO IMPACT Case)**:
   - Input: *"Supplier FastFab announced a 3-day delay on Ergonomic Chair Pro shipments due to port congestion."*
   - Outcome: `NO IMPACT`. On-hand inventory (400 units) > Open customer demand (30 units). Remaining stock buffer: 370 units.

3. **Scenario C (Contradiction Flagged)**:
   - Input: *"Supplier Global Microchip Co reports 1000 units of Laptop X delayed by 10 days."*
   - Outcome: `NEEDS VERIFICATION`. Flags Supplier Mismatch (Disruption claims Global Microchip Co vs DB master shows ABC Supplier Co) and Quantity Discrepancy (1000 units claimed vs 500 in DB).

4. **Scenario D (Dynamic New Order Recalculation)**:
   - Action: Add new customer order `ORD-999` for 450 units of Ergonomic Chair Pro via `+ New Order` modal.
   - Outcome: Re-running Scenario B dynamically switches status from `NO IMPACT` to `IMPACT DETECTED` (Shortage: 80 units, Order Value at Risk: ₹17,60,000).

---

## 💻 API Endpoints

- `GET /` - Main SPA Command Center UI
- `GET /api/dashboard` - Executive stats & Chart.js sales analytics (₹ INR)
- `GET /api/data` - Master dataset (Products, Suppliers, Inventory, Shipments, Customer Orders, Disruptions)
- `POST /api/data/update` - Dynamic record editor
- `POST /api/data/orders` - Add new customer order (Scenario D)
- `POST /api/disruptions/report` - Run PS08 impact analysis pipeline
- `GET /api/disruptions/<id>` - Retrieve structured disruption report & trace payload
- `POST /api/disruptions/<id>/decision` - Record human decision (`Approved Action`, `Modify Strategy`, `Reject`)
- `POST /api/qa` - Grounded database question answering
- `POST /api/seed/reset` - Reset database to clean seed state

---

## ⚠️ Limitations
- Local SQLite database suitable for single-developer hackathon demonstration.
- Grounded QA engine uses pattern matching on active DB tables and disruption summaries; queries outside current DB schema return *"Insufficient data in database to answer reliably."*
