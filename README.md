TRACK_ID=PS08

# SupplyChain Sentinel — AI-Powered Supply Chain Disruption Response

SupplyChain Sentinel is an enterprise supply-chain operations platform that connects unstructured disruption signals with structured operational data to determine the actual downstream impact of supply-chain disruptions.

The platform helps operations teams move from a disruption report to a verified business-impact assessment and prioritized response by connecting supplier information, shipment records, inventory availability, customer demand, and fulfillment requirements.

> **Core capability:** Match disruption information to enterprise records, determine which customer orders are affected, calculate the resulting business impact, and provide a prioritized response plan with cost and risk trade-offs.

---

## Overview

Supply-chain disruptions are frequently communicated through unstructured channels such as supplier emails, carrier notices, procurement alerts, logistics messages, and other operational communications.

A reported disruption does not necessarily mean that customers will be affected.

For example:

- A shipment may be delayed while sufficient inventory is available to satisfy existing demand.
- A disruption notice may contain supplier or quantity information that conflicts with enterprise records.
- A shipment delay may create a shortage across multiple customer orders.
- A relatively small shortage may expose a significant amount of customer order value to risk.

SupplyChain Sentinel brings these signals and operational records together into a single decision-support workflow.

---

# Core Capabilities

## 1. Disruption Signal Processing

The platform accepts unstructured disruption information from operational sources such as:

- Supplier logistics emails
- Carrier status notices
- Procurement alerts
- WhatsApp messages
- Logistics notifications
- Other disruption communications

The system extracts relevant operational facts including:

- Supplier
- Product / SKU
- Affected quantity
- Delay duration
- Disruption reason

The original disruption signal is retained for evidence and traceability.

---

## 2. Master Data Matching

Extracted disruption information is cross-referenced against enterprise records stored in the operational database.

Relevant records include:

- Suppliers
- Products
- Shipments
- Warehouse inventory
- Customer orders

Evidence is attributed to its source, allowing operators to distinguish between information reported in the disruption notice and information recorded in the enterprise database.

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
