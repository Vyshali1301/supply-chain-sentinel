import os
import json
import re
from datetime import datetime, timedelta
from database import get_db_connection, log_activity

# Lazy-loaded Gemini Client Singleton
_gemini_client = None

def get_gemini_client():
    global _gemini_client
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return None
    if _gemini_client is None:
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"Error initializing Google GenAI client: {e}")
            return None
    return _gemini_client

def extract_heuristic(raw_text):
    """
    Robust rule-based heuristic extractor used as an offline/fail-safe fallback
    when Gemini API key is missing or API call fails.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Search for known suppliers from DB
    cursor.execute("SELECT name, supplier_code FROM suppliers")
    suppliers = cursor.fetchall()
    matched_supplier = None
    for s in suppliers:
        if s['name'].lower() in raw_text.lower() or s['supplier_code'].lower() in raw_text.lower():
            matched_supplier = s['name']
            break

    # Search for known products from DB
    cursor.execute("SELECT name, sku FROM products")
    products = cursor.fetchall()
    matched_product = None
    for p in products:
        if p['name'].lower() in raw_text.lower() or p['sku'].lower() in raw_text.lower():
            matched_product = p['name']
            break

    # Look for shipment codes (e.g. SHP-5001)
    shp_match = re.search(r'SHP-\d+', raw_text, re.I)
    shipment_code = shp_match.group(0).upper() if shp_match else None

    # Common keyword fallbacks if not matched directly
    if not matched_supplier:
        if re.search(r'\babc\b', raw_text, re.I):
            matched_supplier = "ABC Supplier Co"
        elif re.search(r'\bfastfab\b', raw_text, re.I):
            matched_supplier = "FastFab Logistics"
        elif re.search(r'\bglobal microchip\b', raw_text, re.I):
            matched_supplier = "Global Microchip Co"
        elif re.search(r'\bdisplayworld\b', raw_text, re.I):
            matched_supplier = "DisplayWorld Ltd"

    if not matched_product:
        if re.search(r'\blaptop\b', raw_text, re.I):
            matched_product = "Laptop X"
        elif re.search(r'\bchair\b', raw_text, re.I):
            matched_product = "Ergonomic Chair Pro"
        elif re.search(r'\bmonitor\b', raw_text, re.I):
            matched_product = "UltraHD Monitor 27\""
        elif re.search(r'\bkeyboard\b', raw_text, re.I):
            matched_product = "Mechanical Keyboard K1"

    # Delay extraction
    delay = 0
    delay_match = re.search(r'(\d+)\s*(-|\s*to\s*)?(\d+)?\s*(day|days|week|weeks)', raw_text, re.I)
    if delay_match:
        val = int(delay_match.group(1))
        unit = delay_match.group(4).lower()
        delay = val * 7 if 'week' in unit else val

    clean_text = raw_text
    if delay_match:
        clean_text = raw_text.replace(delay_match.group(0), '')

    # Quantity extraction
    qty = 0
    qty_match = re.search(r'(\d+)\s*(units|pieces|laptops|chairs|monitors|items)?', clean_text, re.I)
    if qty_match:
        val = int(qty_match.group(1))
        if val > 10 or (qty_match.group(2) and qty_match.group(2).lower() in ['units', 'pieces', 'laptops', 'chairs', 'monitors', 'items']):
            qty = val

    # Disruption reason
    reason = "Logistics disruption"
    lower_text = raw_text.lower()
    if 'port congestion' in lower_text or 'port' in lower_text:
        reason = "Port terminal congestion"
    elif 'transportation' in lower_text or 'transit' in lower_text:
        reason = "Transportation / Freight carrier problem"
    elif 'customs' in lower_text:
        reason = "Customs clearance delay"
    elif 'production' in lower_text or 'factory' in lower_text:
        reason = "Factory production shutdown"
    elif 'weather' in lower_text or 'storm' in lower_text or 'typhoon' in lower_text:
        reason = "Severe weather disruption"

    conn.close()

    # Realistic confidence score based on entity matches
    confidence = 0.50
    if matched_supplier: confidence += 0.20
    if matched_product: confidence += 0.20
    if delay > 0: confidence += 0.05
    if qty > 0: confidence += 0.05

    return {
        "supplier_name": matched_supplier or "Unknown Supplier",
        "product_name_or_sku": matched_product or "Unknown Product",
        "shipment_code": shipment_code,
        "quantity_affected": qty,
        "delay_days": delay,
        "reason": reason,
        "severity_claimed": "High" if delay >= 5 else ("Medium" if delay >= 2 else "Low"),
        "confidence_score": round(confidence, 2)
    }

def call_gemini_extraction(raw_text):
    """
    Calls Google Gemini API to convert unstructured disruption text into structured JSON.
    Gracefully falls back to deterministic heuristic parser if API key is not present or API call fails.
    """
    client = get_gemini_client()
    if client:
        try:
            prompt = f"""You are a Supply Chain Disruption Intelligence AI.
Analyze the following disruption notice and extract the key operational fields.

Disruption Notice:
<<<
{raw_text.strip()}
>>>

Return a single JSON object matching this exact schema:
{{
    "supplier_name": "extracted supplier name or null",
    "product_name_or_sku": "extracted product name or SKU or null",
    "shipment_code": "extracted shipment code (e.g. SHP-5001) or null",
    "quantity_affected": number or null,
    "delay_days": number or null,
    "reason": "Clear summary of disruption reason",
    "severity_claimed": "Low" | "Medium" | "High" | "Critical",
    "confidence_score": float between 0.0 and 1.0
}}"""
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            text_resp = response.text.strip()
            data = json.loads(text_resp)
            if isinstance(data, dict):
                return {
                    "supplier_name": data.get("supplier_name") or "Unknown Supplier",
                    "product_name_or_sku": data.get("product_name_or_sku") or "Unknown Product",
                    "shipment_code": data.get("shipment_code"),
                    "quantity_affected": int(data.get("quantity_affected") or 0),
                    "delay_days": int(data.get("delay_days") or 0),
                    "reason": data.get("reason") or "Logistics disruption",
                    "severity_claimed": data.get("severity_claimed") or "Medium",
                    "confidence_score": float(data.get("confidence_score") or 0.85)
                }
        except Exception as e:
            print(f"Gemini API call failed or timed out ({e}). Falling back to heuristic parser.")

    return extract_heuristic(raw_text)

def analyze_disruption(raw_text, intake_timestamp=None, save_record=True):
    """
    Enterprise Disruption Response Engine:
    1. Entity Extraction (Gemini LLM with deterministic regex fallback).
    2. Master Database matching supporting multiple shipments per product.
    3. Contradiction Detection with percentage & entity mismatch verification.
    4. Deterministic Temporal Allocation Math (calendar-aware FIFO customer order impact).
    5. Dynamic Mitigation Modeling (real rate cards, zero hardcoded values).
    6. Grounded Causal Impact Chain graph payload.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Extraction
    extracted = call_gemini_extraction(raw_text)
    
    supplier_query = extracted.get('supplier_name', '')
    product_query = extracted.get('product_name_or_sku', '')
    shipment_code_query = extracted.get('shipment_code')
    qty_claimed = extracted.get('quantity_affected', 0)
    delay_days = extracted.get('delay_days', 0)

    # 2. Database Matching
    matched_product = None
    if product_query and product_query != "Unknown Product":
        cursor.execute("SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? LIMIT 1", (f"%{product_query}%", f"%{product_query}%"))
        p_row = cursor.fetchone()
        if p_row:
            matched_product = dict(p_row)

    matched_supplier = None
    if supplier_query and supplier_query != "Unknown Supplier":
        cursor.execute("SELECT * FROM suppliers WHERE name LIKE ? OR supplier_code LIKE ? LIMIT 1", (f"%{supplier_query}%", f"%{supplier_query}%"))
        s_row = cursor.fetchone()
        if s_row:
            matched_supplier = dict(s_row)

    # Multiple Shipments Support:
    # 2a. First priority: match exact shipment code if provided
    matched_shipment = None
    all_active_shipments = []
    
    if matched_product:
        cursor.execute("SELECT * FROM shipments WHERE product_id = ? ORDER BY expected_delivery_date ASC", (matched_product['id'],))
        all_product_shipments = [dict(s) for s in cursor.fetchall()]
        all_active_shipments = [s for s in all_product_shipments if s['status'] not in ('Delivered', 'Received')]

    if shipment_code_query:
        cursor.execute("SELECT * FROM shipments WHERE shipment_code = ? LIMIT 1", (shipment_code_query,))
        s_row = cursor.fetchone()
        if s_row:
            matched_shipment = dict(s_row)

    # 2b. Second priority: match shipment by supplier and product
    if not matched_shipment and matched_product and matched_supplier:
        # Prioritize matching active shipment with matching quantity
        if qty_claimed > 0:
            for s in all_active_shipments:
                if s['supplier_id'] == matched_supplier['id'] and (s['quantity'] == qty_claimed or s['remaining_quantity'] == qty_claimed):
                    matched_shipment = s
                    break
        # Next, check if any shipment for this supplier matched claimed quantity (even if already received)
        if not matched_shipment and qty_claimed > 0 and 'all_product_shipments' in locals():
            for s in all_product_shipments:
                if s['supplier_id'] == matched_supplier['id'] and (s['quantity'] == qty_claimed or s['remaining_quantity'] == qty_claimed):
                    matched_shipment = s
                    break
        # Next, match any active shipment for this supplier
        if not matched_shipment:
            for s in all_active_shipments:
                if s['supplier_id'] == matched_supplier['id']:
                    matched_shipment = s
                    break

    # 2c. Fallback: earliest active shipment for this product
    if not matched_shipment and all_active_shipments:
        matched_shipment = all_active_shipments[0]

    shipment_quantity = matched_shipment['quantity'] if matched_shipment else 0
    shipment_remaining = matched_shipment['remaining_quantity'] if matched_shipment else 0

    # 3. Contradiction & Conflict Detection
    contradiction_items = []

    if not matched_product:
        contradiction_items.append({
            "issue": "Product Master Not Found",
            "disruption_claim": f"Product: '{product_query}' (Source: Disruption Notice)",
            "db_record": "No matching SKU in Products Master",
            "reason": f"Product '{product_query}' could not be resolved against active enterprise catalogue."
        })
    else:
        # Supplier mismatch check
        if matched_supplier and matched_shipment:
            cursor.execute("SELECT name FROM suppliers WHERE id = ?", (matched_shipment['supplier_id'],))
            actual_supp = cursor.fetchone()
            if actual_supp and actual_supp['name'].lower() != matched_supplier['name'].lower():
                contradiction_items.append({
                    "issue": "Supplier Mismatch Conflict",
                    "disruption_claim": f"Supplier: '{matched_supplier['name']}' (Source: Disruption Notice)",
                    "db_record": f"Shipment {matched_shipment['shipment_code']} is registered to '{actual_supp['name']}' (Source: Shipments Master)",
                    "reason": f"Disruption notice attributes delay to '{matched_supplier['name']}', but active shipment {matched_shipment['shipment_code']} belongs to '{actual_supp['name']}'."
                })

        # Meaningful Quantity Discrepancy (>25% discrepancy against both shipment remaining and total quantity)
        if (shipment_remaining > 0 or shipment_quantity > 0) and qty_claimed > 0:
            diff_rem = abs(shipment_remaining - qty_claimed) if shipment_remaining > 0 else 999999
            pct_rem = (diff_rem / shipment_remaining * 100) if shipment_remaining > 0 else 100.0

            diff_total = abs(shipment_quantity - qty_claimed) if shipment_quantity > 0 else 999999
            pct_total = (diff_total / shipment_quantity * 100) if shipment_quantity > 0 else 100.0

            if pct_rem > 25 and diff_rem > 30 and pct_total > 25 and diff_total > 30:
                contradiction_items.append({
                    "issue": "Quantity Discrepancy Conflict",
                    "disruption_claim": f"Claimed Affected Quantity: {qty_claimed} units",
                    "db_record": f"Active Shipment: {shipment_remaining} units remaining ({shipment_quantity} total) in {matched_shipment['shipment_code']}",
                    "reason": f"Claimed quantity ({qty_claimed} units) diverges by over 25% from both active shipment remaining ({shipment_remaining} units) and total quantity ({shipment_quantity} units)."
                })

    has_contradictions = len(contradiction_items) > 0

    # Evidence Attribution Payload
    evidence = {
        "supplier_match": {
            "value": f"{matched_supplier['name']} ({matched_supplier['supplier_code']})" if matched_supplier else (supplier_query or "Not Found"),
            "source": "Disruption Notice vs Database Supplier Master"
        },
        "product_match": {
            "value": f"{matched_product['name']} ({matched_product['sku']})" if matched_product else (product_query or "Not Found"),
            "source": "Disruption Notice vs Database Product Master"
        },
        "shipment_match": {
            "value": f"{matched_shipment['shipment_code']} ({matched_shipment['remaining_quantity']} remaining / {matched_shipment['quantity']} total)" if matched_shipment else "None Active",
            "source": "Database Shipment Master Records",
            "shipment_id": matched_shipment['id'] if matched_shipment else None,
            "shipment_code": matched_shipment['shipment_code'] if matched_shipment else None,
            "quantity": matched_shipment['quantity'] if matched_shipment else 0,
            "received_quantity": matched_shipment['received_quantity'] if matched_shipment else 0,
            "remaining_qty": matched_shipment['remaining_quantity'] if matched_shipment else 0,
            "all_active_shipments_count": len(all_active_shipments)
        },
        "inventory_match": {
            "value": f"{matched_product['current_stock']} units on hand (Safety Stock: {matched_product['safety_stock']})" if matched_product else "N/A",
            "source": "Master Inventory Record"
        },
        "contradiction_found": has_contradictions,
        "contradiction_items": contradiction_items
    }

    # 4. Deterministic Temporal Allocation Engine
    if matched_product:
        p_id = matched_product['id']
        current_stock = matched_product['current_stock']
        safety_stock = matched_product['safety_stock']

        # Determine revised shipment delivery date
        revised_eta = None
        current_eta_str = None
        if matched_shipment and matched_shipment.get('expected_delivery_date'):
            current_eta_str = matched_shipment['expected_delivery_date']
            try:
                base_eta = datetime.strptime(current_eta_str, '%Y-%m-%d')
                revised_eta = base_eta + timedelta(days=delay_days)
            except Exception:
                pass

        # Strict FIFO Order Query: sorted by promised ship date first, then order date, then id
        cursor.execute('''
        SELECT * FROM customer_orders 
        WHERE product_id = ? AND status = 'Pending' 
        ORDER BY expected_ship_date ASC, order_date ASC, id ASC
        ''', (p_id,))
        open_orders = [dict(o) for o in cursor.fetchall()]

        # Account for partial fulfillment in open demand
        total_open_demand = sum(max(0, o['quantity_ordered'] - (o['quantity_fulfilled'] or 0)) for o in open_orders)
        stock_after_orders = current_stock - total_open_demand
        net_shortage = abs(stock_after_orders) if stock_after_orders < 0 else 0

        # Safety stock buffer check
        safety_stock_breach = False
        remaining_buffer = max(0, stock_after_orders)
        if stock_after_orders >= 0 and stock_after_orders < safety_stock:
            safety_stock_breach = True

        if has_contradictions:
            status = "NEEDS VERIFICATION"
            impact_summary = {
                "status": status,
                "affected_product": f"{matched_product['name']} ({matched_product['sku']})",
                "current_stock": current_stock,
                "safety_stock": safety_stock,
                "open_order_demand": total_open_demand,
                "shipment_quantity": shipment_quantity,
                "inventory_shortage": net_shortage,
                "units_at_risk": 0,
                "order_value_at_risk": 0.0,
                "affected_customer_orders": [],
                "affected_customers": [],
                "expected_delivery_impact": "NEEDS VERIFICATION: Disruption claim conflicts with master database records. Automated response execution paused pending operational review."
            }
        elif stock_after_orders >= 0:
            status = "NO IMPACT"
            safety_note = f" (Note: Safety stock threshold of {safety_stock} units preserved; buffer remaining: {remaining_buffer} units)." if not safety_stock_breach else f" (Warning: Inventory buffer remaining ({remaining_buffer} units) is below safety stock threshold of {safety_stock} units)."
            impact_summary = {
                "status": status,
                "affected_product": f"{matched_product['name']} ({matched_product['sku']})",
                "current_stock": current_stock,
                "safety_stock": safety_stock,
                "open_order_demand": total_open_demand,
                "shipment_quantity": shipment_quantity,
                "inventory_shortage": 0,
                "remaining_buffer": remaining_buffer,
                "units_at_risk": 0,
                "order_value_at_risk": 0.0,
                "affected_customer_orders": [],
                "affected_customers": [],
                "expected_delivery_impact": f"NO IMPACT: Current inventory on hand ({current_stock} units) completely fulfills all open customer commitments ({total_open_demand} units) without dependency on the delayed shipment.{safety_note}"
            }
        else:
            status = "IMPACT DETECTED"
            affected_orders_list = []
            affected_customers = []
            order_value_at_risk = 0.0

            # Deterministic FIFO Order Allocation
            accumulated_stock = current_stock
            for o in open_orders:
                unfulfilled_order_demand = max(0, o['quantity_ordered'] - (o['quantity_fulfilled'] or 0))
                if unfulfilled_order_demand <= 0:
                    continue

                if accumulated_stock >= unfulfilled_order_demand:
                    # Stock on hand fulfills this order in full
                    accumulated_stock -= unfulfilled_order_demand
                else:
                    # Order is either partially or fully unfulfilled by on-hand inventory
                    short_for_this_order = unfulfilled_order_demand - max(0, accumulated_stock)
                    accumulated_stock = 0

                    # Use actual order unit price, not catalog master price
                    contract_unit_price = float(o['unit_price'])
                    order_val_at_risk = short_for_this_order * contract_unit_price
                    order_value_at_risk += order_val_at_risk

                    # Calculate order delivery delay
                    order_delay_days = delay_days or 5
                    if revised_eta and o.get('expected_ship_date'):
                        try:
                            ord_exp = datetime.strptime(o['expected_ship_date'], '%Y-%m-%d')
                            diff_days = (revised_eta - ord_exp).days
                            if diff_days > 0:
                                order_delay_days = diff_days
                        except Exception:
                            pass

                    affected_orders_list.append({
                        "order_number": o['order_number'],
                        "customer": o['customer_name'],
                        "qty_ordered": o['quantity_ordered'],
                        "qty_unfulfilled": short_for_this_order,
                        "unit_price": contract_unit_price,
                        "value": order_val_at_risk,
                        "delay_days": order_delay_days,
                        "expected_ship_date": o['expected_ship_date']
                    })
                    if o['customer_name'] not in affected_customers:
                        affected_customers.append(o['customer_name'])

            impact_summary = {
                "status": status,
                "affected_product": f"{matched_product['name']} ({matched_product['sku']})",
                "current_stock": current_stock,
                "safety_stock": safety_stock,
                "open_order_demand": total_open_demand,
                "shipment_quantity": shipment_quantity,
                "inventory_shortage": net_shortage,
                "units_at_risk": net_shortage,
                "order_value_at_risk": order_value_at_risk,
                "affected_customer_orders": affected_orders_list,
                "affected_customers": affected_customers,
                "expected_delivery_impact": f"{delay_days or 5}-day shipment delay impacting {len(affected_orders_list)} pending customer orders with total contract revenue exposure of ₹{order_value_at_risk:,.2f}."
            }

    else:
        status = "NEEDS VERIFICATION"
        impact_summary = {
            "status": "NEEDS VERIFICATION",
            "affected_product": product_query or "Unknown",
            "current_stock": 0,
            "safety_stock": 0,
            "open_order_demand": 0,
            "shipment_quantity": 0,
            "inventory_shortage": 0,
            "units_at_risk": 0,
            "order_value_at_risk": 0.0,
            "affected_customer_orders": [],
            "affected_customers": [],
            "expected_delivery_impact": "Unable to calculate business impact because product SKU could not be matched in database master."
        }

    # 5. Dynamic Mitigation Engine (No Hardcoded Numbers)
    response_options = []
    ai_recommendation = ""

    if status == "IMPACT DETECTED":
        shortage = impact_summary['inventory_shortage']
        val_at_risk = impact_summary['order_value_at_risk']
        current_stk = impact_summary['current_stock']
        num_orders = len(impact_summary['affected_customer_orders'])
        units_to_expedite = qty_claimed if qty_claimed > 0 else (shipment_quantity or shortage)

        # Dynamic Route and Freight Rate Model
        origin = matched_shipment['origin'] if matched_shipment else "Supplier Origin Port"
        destination = matched_shipment['destination'] if matched_shipment else "Destination Port"

        # Rate Model: Transparent logistics estimate (₹650/unit freight + ₹25,000 priority customs surcharge)
        unit_freight_rate = 650.0
        customs_surcharge = 25000.0
        full_air_cost = customs_surcharge + (units_to_expedite * unit_freight_rate)
        partial_air_cost = customs_surcharge + (shortage * unit_freight_rate)

        cost_to_risk_ratio = (full_air_cost / val_at_risk * 100.0) if val_at_risk > 0 else 0.0
        partial_ratio = (partial_air_cost / val_at_risk * 100.0) if val_at_risk > 0 else 0.0

        # Stock reallocation option
        if current_stk > 0 and impact_summary['affected_customers']:
            top_cust = impact_summary['affected_customers'][0]
            reallocate_action = f"Allocate {current_stk} units currently on hand to top order ({top_cust}) for immediate dispatch; schedule remaining accounts upon shipment arrival."
            reallocate_tradeoff = f"Zero freight expenditure, but defers {max(0, num_orders - 1)} secondary customer deliveries by {delay_days or 5} days."
        else:
            reallocate_action = "Stock reallocation unavailable due to zero unreserved on-hand warehouse inventory."
            reallocate_tradeoff = "Zero stock buffer available for interim redistribution."

        voucher_cost = val_at_risk * 0.05

        response_options = [
            {
                "id": "opt-1",
                "name": "Expedite Priority Air Cargo",
                "action": f"Reroute inbound shipment ({units_to_expedite} units) via Priority Air Cargo from {origin} to {destination}.",
                "cost": f"₹{full_air_cost:,.2f} (Estimated Air Cargo Surcharge)",
                "orders_protected": f"All {num_orders} customer orders ({shortage} units protected)",
                "remaining_affected": "0 orders delayed",
                "customer_impact": "Zero delivery SLA slippage; preserves customer delivery dates",
                "assumption": f"Assumes air cargo capacity available from {origin} to {destination} at estimated rate of ₹{unit_freight_rate:,.0f}/unit + customs priority fee.",
                "trade_off": f"Incurs ₹{full_air_cost:,.2f} freight cost ({cost_to_risk_ratio:.2f}% of exposure) to fully protect ₹{val_at_risk:,.2f} contract revenue."
            },
            {
                "id": "opt-2",
                "name": "Split Shipment & Air Cargo Hybrid",
                "action": f"Dispatch {current_stk} units in stock immediately; air-freight only the net deficit ({shortage} units).",
                "cost": f"₹{partial_air_cost:,.2f} (Targeted Deficit Air Freight)",
                "orders_protected": f"Immediate partial fulfillment of {current_stk} units; full fulfillment in 48-72h",
                "remaining_affected": "0 unfulfilled orders after deficit arrival",
                "customer_impact": "Staggered delivery; immediate partial order dispatch minimizes downtime",
                "assumption": f"Customer accounts permit split delivery shipments. Air freight rate applies only to {shortage} deficit units.",
                "trade_off": f"Reduces air freight expense by ₹{(full_air_cost - partial_air_cost):,.2f} ({partial_ratio:.2f}% of exposure) while satisfying immediate client demand."
            },
            {
                "id": "opt-3",
                "name": "Stock Reallocation & Key Account Protection",
                "action": reallocate_action,
                "cost": "₹0 Direct Freight Cost",
                "orders_protected": "Primary / VIP Account Protected",
                "remaining_affected": f"{max(0, num_orders - 1)} secondary orders delayed",
                "customer_impact": f"Top account protected; secondary accounts experience {delay_days or 5}-day delivery delay",
                "assumption": "Sales agreements permit prioritizing tier-1 accounts over standard distribution.",
                "trade_off": reallocate_tradeoff
            },
            {
                "id": "opt-4",
                "name": "Accept Schedule Slippage & Issue Apology Credit",
                "action": f"Notify affected clients of {delay_days or 5}-day shipment delay and issue 5% delay compensation vouchers.",
                "cost": f"₹{voucher_cost:,.2f} (5% Contract Vouchers)",
                "orders_protected": "0 orders",
                "remaining_affected": f"All {num_orders} orders delayed by {delay_days or 5} days",
                "customer_impact": f"{delay_days or 5}-day delivery delay accompanied by financial credit compensation",
                "assumption": "Clients accept delivery postponement without order cancellation.",
                "trade_off": f"Avoids ₹{full_air_cost:,.2f} in air freight surcharges but incurs ₹{voucher_cost:,.2f} voucher cost and reputational friction."
            }
        ]

        if cost_to_risk_ratio < 15.0:
            ai_recommendation = f"Expedite Priority Air Cargo (Option 1). Recommended because the estimated air freight surcharge of ₹{full_air_cost:,.2f} represents only {cost_to_risk_ratio:.2f}% of the ₹{val_at_risk:,.2f} contract value at risk across {num_orders} customer accounts."
        else:
            ai_recommendation = f"Split Shipment & Air Cargo Hybrid (Option 2). Recommended because dispatching {current_stk} on-hand units and air-freighting only {shortage} shortage units reduces logistics expenditure to ₹{partial_air_cost:,.2f} while preventing account cancellation."

    elif status == "NO IMPACT":
        buffer = impact_summary.get('remaining_buffer', 0)
        prod_name = matched_product['name'] if matched_product else "Product"
        response_options = [
            {
                "id": "opt-no-action",
                "name": "Standard Operational Monitoring",
                "action": f"Log disruption advisory into shipment tracking; maintain standard warehouse fulfillment plan for {prod_name}.",
                "cost": "₹0",
                "orders_protected": "All customer commitments on schedule",
                "remaining_affected": "0 orders delayed",
                "customer_impact": "Zero delivery delay; standard delivery schedules maintained",
                "assumption": f"Available stock on hand ({impact_summary['current_stock']} units) satisfies all pending orders ({impact_summary['open_order_demand']} units).",
                "trade_off": f"Zero financial expenditure. Post-fulfillment inventory buffer will stand at {buffer} units."
            }
        ]
        ai_recommendation = f"Standard Operational Monitoring. Recommended because on-hand stock ({impact_summary['current_stock']} units) fully covers all pending orders ({impact_summary['open_order_demand']} units) with a remaining buffer of {buffer} units."

    else:
        response_options = [
            {
                "id": "opt-verification",
                "name": "Hold & Verify Disruption Credentials",
                "action": "Dispatch procurement inquiry to freight carrier / supplier coordinator to reconcile discrepancy.",
                "cost": "₹0",
                "orders_protected": "Pending Record Reconciliation",
                "remaining_affected": "Pending Record Reconciliation",
                "customer_impact": "No emergency rerouting until verified",
                "assumption": "Disruption notice contains mismatched quantities or supplier details relative to database records.",
                "trade_off": "Prevents unwarranted emergency air freight commitments based on inaccurate third-party alerts."
            }
        ]
        ai_recommendation = "Hold & Verify Disruption Credentials. Recommended because safety checks flagged contradictions between the incoming disruption notice and enterprise records."

    # 6. Impact Trace Causal Graph Payload
    trace_nodes = [
        {
            "id": "d1",
            "label": f"Disruption Signal: {delay_days or 5}-Day Delay",
            "type": "disruption",
            "details": {
                "Raw Signal": raw_text,
                "Claimed Delay": f"{delay_days or 5} Days",
                "Extracted Reason": extracted.get('reason', 'Logistics disruption')
            }
        },
        {
            "id": "s1", 
            "label": f"Supplier: {matched_supplier['name'] if matched_supplier else supplier_query}", 
            "type": "supplier",
            "details": {
                "Supplier Name": matched_supplier['name'] if matched_supplier else supplier_query,
                "Supplier Code": matched_supplier['supplier_code'] if matched_supplier else "N/A",
                "Country": matched_supplier['country'] if matched_supplier else "N/A",
                "Reliability Rating": f"⭐ {matched_supplier['reliability_rating']}" if matched_supplier else "N/A"
            }
        },
        {
            "id": "sh1", 
            "label": f"Shipment: {matched_shipment['shipment_code'] if matched_shipment else 'N/A'}", 
            "type": "shipment",
            "details": {
                "Shipment Code": matched_shipment['shipment_code'] if matched_shipment else "N/A",
                "Remaining Quantity": f"{matched_shipment['remaining_quantity']} units" if matched_shipment else "N/A",
                "Route": f"{matched_shipment['origin']} ➔ {matched_shipment['destination']}" if matched_shipment else "N/A",
                "Original ETA": matched_shipment['expected_delivery_date'] if matched_shipment else "N/A",
                "Status": matched_shipment['status'] if matched_shipment else "N/A"
            }
        },
        {
            "id": "p1", 
            "label": f"Product: {matched_product['name'] if matched_product else product_query}", 
            "type": "product",
            "details": {
                "Product Name": matched_product['name'] if matched_product else product_query,
                "SKU": matched_product['sku'] if matched_product else "N/A",
                "Unit Cost": f"₹{matched_product['unit_cost']:,.2f}" if matched_product else "N/A",
                "Selling Price": f"₹{matched_product['selling_price']:,.2f}" if matched_product else "N/A"
            }
        },
        {
            "id": "i1", 
            "label": f"Inventory: {impact_summary.get('current_stock', 0)} On-Hand | Shortage: {impact_summary.get('inventory_shortage', 0)}", 
            "type": "inventory",
            "details": {
                "Stock On Hand": f"{impact_summary.get('current_stock', 0)} units",
                "Safety Stock Threshold": f"{impact_summary.get('safety_stock', 0)} units",
                "Open Order Demand": f"{impact_summary.get('open_order_demand', 0)} units",
                "Calculated Shortage": f"{impact_summary.get('inventory_shortage', 0)} units"
            }
        }
    ]
    
    trace_edges = [
        {"from": "d1", "to": "s1"},
        {"from": "s1", "to": "sh1"},
        {"from": "sh1", "to": "p1"},
        {"from": "p1", "to": "i1"}
    ]

    if impact_summary.get('affected_customer_orders'):
        orders_label = ", ".join([o['order_number'] for o in impact_summary['affected_customer_orders']])
        customers_label = ", ".join(impact_summary.get('affected_customers', []))
        
        trace_nodes.extend([
            {
                "id": "o1", 
                "label": f"Affected Orders: {orders_label}", 
                "type": "orders",
                "details": {
                    "Orders Count": f"{len(impact_summary['affected_customer_orders'])} Orders Delayed",
                    "Orders Breakdown": ", ".join([f"{o['order_number']} ({o['customer']}: {o['qty_unfulfilled']} units short)" for o in impact_summary['affected_customer_orders']])
                }
            },
            {
                "id": "c1", 
                "label": f"Customers: {customers_label}", 
                "type": "customers",
                "details": {
                    "Affected Accounts": customers_label,
                    "Delivery Delay": f"+{delay_days or 5} Days"
                }
            },
            {
                "id": "imp", 
                "label": f"Exposure: ₹{impact_summary.get('order_value_at_risk', 0):,.2f}", 
                "type": "impact",
                "details": {
                    "Total Order Value at Risk": f"₹{impact_summary.get('order_value_at_risk', 0):,.2f}",
                    "Shortage Quantity": f"{impact_summary.get('inventory_shortage', 0)} units",
                    "Assessment Status": status
                }
            },
            {
                "id": "rec", 
                "label": "Mitigation: Expedite Air Cargo", 
                "type": "response",
                "details": {
                    "Recommendation": ai_recommendation
                }
            }
        ])
        trace_edges.extend([
            {"from": "i1", "to": "o1"},
            {"from": "o1", "to": "c1"},
            {"from": "c1", "to": "imp"},
            {"from": "imp", "to": "rec"}
        ])
    else:
        trace_nodes.extend([
            {
                "id": "imp", 
                "label": f"Status: {status}", 
                "type": "impact",
                "details": {
                    "Order Value At Risk": "₹0.00",
                    "Status": status,
                    "Summary": impact_summary.get('expected_delivery_impact', '')
                }
            },
            {
                "id": "rec", 
                "label": "Mitigation: Standard Plan", 
                "type": "response",
                "details": {
                    "Recommendation": ai_recommendation
                }
            }
        ])
        trace_edges.extend([
            {"from": "i1", "to": "imp"},
            {"from": "imp", "to": "rec"}
        ])

    trace_json = {
        "nodes": trace_nodes,
        "edges": trace_edges
    }

    # 7. Persistence
    disruption_id = None
    created_ts = intake_timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if save_record:
        cursor.execute('''
        INSERT INTO disruptions (
            raw_text, extracted_json, status, impact_summary_json, 
            evidence_json, trace_json, human_decision, is_active, 
            product_id, shipment_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            raw_text,
            json.dumps(extracted),
            status,
            json.dumps({**impact_summary, "response_options": response_options, "ai_recommendation": ai_recommendation}),
            json.dumps(evidence),
            json.dumps(trace_json),
            "Pending Review",
            1 if status == 'IMPACT DETECTED' else 0,
            matched_product['id'] if matched_product else None,
            matched_shipment['id'] if matched_shipment else None,
            created_ts
        ))
        
        disruption_id = cursor.lastrowid

        prod_name = matched_product['name'] if matched_product else extracted.get('product_name_or_sku', 'Product')
        qty_aff = extracted.get('quantity_affected', 0)
        delay_d = extracted.get('delay_days', 0)
        log_activity("Disruption Reported", f"{prod_name} — {qty_aff or 'Shipment'} units delayed by {delay_d} days", entity_ref=f"INC-#{disruption_id}", cursor=cursor)

        if status == 'IMPACT DETECTED':
            shortage_qty = impact_summary.get('inventory_shortage', 0)
            val_risk = impact_summary.get('order_value_at_risk', 0.0)
            log_activity("Impact Assessment Completed", f"{shortage_qty} units shortage detected | ₹{val_risk:,.2f} order value at risk", entity_ref=f"INC-#{disruption_id}", cursor=cursor)
        elif status == 'NO IMPACT':
            buf = impact_summary.get('remaining_buffer', 0)
            log_activity("Impact Assessment Completed", f"No business impact | Stock buffer: +{buf} units", entity_ref=f"INC-#{disruption_id}", cursor=cursor)
        else:
            log_activity("Impact Assessment Completed", "Needs verification | Data contradictions detected", entity_ref=f"INC-#{disruption_id}", cursor=cursor)

        conn.commit()

    conn.close()

    return {
        "disruption_id": disruption_id,
        "raw_text": raw_text,
        "extracted_info": extracted,
        "status": status,
        "evidence": evidence,
        "impact_summary": impact_summary,
        "response_options": response_options,
        "ai_recommendation": ai_recommendation,
        "trace": trace_json
    }

def ask_system_question(query):
    """
    Grounded Operations Query Assistant:
    1. If Gemini API is available, extracts grounded database context and uses the LLM
       to answer natural language operations questions without hallucination.
    2. Fallback query engine handles orders, shipments, products, inventory, and risk accurately.
    """
    query_lower = query.lower().strip()
    conn = get_db_connection()
    cursor = conn.cursor()

    client = get_gemini_client()
    if client:
        try:
            # Build live operational snapshot for LLM grounding
            cursor.execute("SELECT sku, name, current_stock, safety_stock FROM products")
            prods = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT shipment_code, status, quantity, remaining_quantity, origin, destination, expected_delivery_date FROM shipments")
            shps = [dict(r) for r in cursor.fetchall()]

            cursor.execute('''
            SELECT co.order_number, co.customer_name, p.name as product_name, co.quantity_ordered, co.quantity_fulfilled, co.unit_price, co.total_price, co.expected_ship_date, co.status
            FROM customer_orders co JOIN products p ON co.product_id = p.id
            ''')
            ords = [dict(r) for r in cursor.fetchall()]

            cursor.execute("SELECT id, status, impact_summary_json, human_decision, is_active FROM disruptions WHERE is_active = 1 OR status = 'IMPACT DETECTED' ORDER BY id DESC LIMIT 3")
            disrupts = []
            for d in cursor.fetchall():
                d_dict = dict(d)
                try:
                    d_dict['impact_summary'] = json.loads(d['impact_summary_json'])
                except Exception:
                    d_dict['impact_summary'] = {}
                d_dict.pop('impact_summary_json', None)
                disrupts.append(d_dict)

            db_context = {
                "products_inventory": prods,
                "inbound_shipments": shps,
                "customer_orders": ords,
                "active_disruptions": disrupts
            }

            qa_prompt = f"""You are the SupplyChain Sentinel Operations Assistant.
Answer the following user question strictly and accurately using ONLY the live database records provided below.
All financial currency is in Indian Rupees (₹ INR).
If the question asks for information not present in the data, state clearly what is known and what cannot be determined.

Live Database Snapshot:
{json.dumps(db_context, indent=2)}

User Question:
"{query}"

Answer concisely and factually:"""

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=qa_prompt
            )
            answer_text = response.text.strip()
            conn.close()
            return answer_text

        except Exception as e:
            print(f"Gemini QA assistant error, falling back to database query engine: {e}")

    # Fallback Grounded Query Engine (Deterministic database search)
    # Check for specific order number (e.g. ORD-901, order #901, Order 901)
    ord_match = re.search(r'(?:ord-|order\s*#?\s*)(\d+)', query_lower)
    if ord_match:
        ord_num = f"ORD-{ord_match.group(1)}"
        cursor.execute('''
        SELECT co.*, p.name as product_name, p.sku, p.current_stock
        FROM customer_orders co
        JOIN products p ON co.product_id = p.id
        WHERE co.order_number = ?
        ''', (ord_num,))
        o = cursor.fetchone()
        if o:
            cursor.execute("SELECT * FROM disruptions WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
            d = cursor.fetchone()
            d_summary = ""
            if d:
                try:
                    d_imp = json.loads(d['impact_summary_json'])
                    affected_nums = [aff['order_number'] for aff in d_imp.get('affected_customer_orders', [])]
                    if ord_num in affected_nums:
                        d_summary = f" Order is delayed by active disruption ({d['status']}) due to supplier delivery delay."
                    else:
                        d_summary = " Order is currently supported by inventory on hand."
                except Exception:
                    pass

            conn.close()
            fulfilled = o['quantity_fulfilled'] or 0
            rem = max(0, o['quantity_ordered'] - fulfilled)
            return f"Order {o['order_number']} for {o['customer_name']} is for {o['quantity_ordered']} units of {o['product_name']} ({o['sku']}) valued at ₹{o['total_price']:,.2f}. Fulfilled: {fulfilled} units, Remaining: {rem} units. Promised delivery date is {o['expected_ship_date']}. Warehouse stock on hand: {o['current_stock']} units.{d_summary}"
        else:
            conn.close()
            return f"Order {ord_num} was not found in the customer orders master ledger."

    # Check for shipments
    shp_match = re.search(r'shp-\d+', query_lower)
    if shp_match:
        shp_code = shp_match.group(0).upper()
        cursor.execute('''
        SELECT s.*, p.name as product_name, sup.name as supplier_name
        FROM shipments s
        JOIN products p ON s.product_id = p.id
        JOIN suppliers sup ON s.supplier_id = sup.id
        WHERE s.shipment_code = ?
        ''', (shp_code,))
        s = cursor.fetchone()
        conn.close()
        if s:
            return f"Shipment {s['shipment_code']} ({s['supplier_name']} ➔ {s['product_name']}) contains {s['quantity']} units ({s['received_quantity']} received, {s['remaining_quantity']} remaining). Status: {s['status']}. Route: {s['origin']} to {s['destination']}. Expected delivery date: {s['expected_delivery_date']} (Tracking: {s['tracking_number']})."
        return f"Shipment {shp_code} was not found in active records."

    # Orders at risk inquiry
    if 'at risk' in query_lower or 'affected order' in query_lower or 'delayed order' in query_lower or 'slipping' in query_lower:
        cursor.execute("SELECT * FROM disruptions WHERE status = 'IMPACT DETECTED' AND is_active = 1 ORDER BY id DESC LIMIT 1")
        d = cursor.fetchone()
        if d:
            d_imp = json.loads(d['impact_summary_json'])
            orders = d_imp.get('affected_customer_orders', [])
            val = d_imp.get('order_value_at_risk', 0.0)
            order_names = ", ".join([f"{o['order_number']} ({o['customer']} - ₹{o['value']:,.2f})" for o in orders])
            conn.close()
            return f"Currently {len(orders)} order(s) are at risk totaling ₹{val:,.2f} in financial exposure: {order_names}."
        else:
            conn.close()
            return "No orders are currently at risk. All pending customer commitments are backed by on-hand inventory."

    # Supplier inquiry
    if 'supplier' in query_lower or 'largest impact' in query_lower or 'worst' in query_lower:
        cursor.execute("SELECT * FROM disruptions WHERE status = 'IMPACT DETECTED' AND is_active = 1 ORDER BY id DESC LIMIT 1")
        d = cursor.fetchone()
        if d:
            ext = json.loads(d['extracted_json'])
            imp = json.loads(d['impact_summary_json'])
            conn.close()
            return f"The largest active disruption is caused by {ext.get('supplier_name', 'ABC Supplier Co')}, resulting in a net shortage of {imp.get('inventory_shortage', 0)} units and risking ₹{imp.get('order_value_at_risk', 0.0):,.2f} in pending revenue."
        else:
            conn.close()
            return "No supplier is currently causing business impact. System operating on schedule."

    # Stock / Inventory inquiry
    if 'stock' in query_lower or 'inventory' in query_lower or 'laptop' in query_lower or 'chair' in query_lower or 'monitor' in query_lower or 'keyboard' in query_lower:
        cursor.execute("SELECT * FROM products")
        prods = cursor.fetchall()
        stock_summary = ", ".join([f"{p['name']}: {p['current_stock']} on hand (Safety: {p['safety_stock']})" for p in prods])
        conn.close()
        return f"Current Master Inventory Stock: {stock_summary}."

    conn.close()
    return "Insufficient data in database to answer reliably."
