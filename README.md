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

## 3. Conflict and Contradiction Detection

The platform performs validation checks before treating a disruption as an actionable business incident.

It can identify conditions such as:

- Supplier mismatch
- Shipment mismatch
- Quantity discrepancy
- Missing product records
- Conflicting master-data information

When contradictory information is detected, the incident is marked:

`NEEDS VERIFICATION`

This prevents potentially incorrect disruption information from automatically driving operational decisions.

---

# 4. Deterministic Business Impact Analysis

Business-impact calculations are performed by the Python impact engine using operational database records.

The calculation engine determines:

- Available inventory
- Open customer demand
- Incoming shipment quantities
- Inventory buffer
- Shortage quantity
- Affected customer orders
- Order value at risk
- Potential fulfillment impact

The system distinguishes between three primary outcomes:

### NO IMPACT

The available inventory can satisfy current open demand without depending on the delayed shipment.

Example:

```text
Inventory On Hand: 400 units
Open Demand: 30 units
Remaining Buffer: 370 units

Status: NO IMPACT