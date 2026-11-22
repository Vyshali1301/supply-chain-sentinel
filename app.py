import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from database import init_db, get_db_connection, log_activity, adjust_inventory_stock
from engine import analyze_disruption, ask_system_question

app = Flask(__name__, static_folder='static', template_folder='templates')

# Initialize DB on startup
init_db(reset=False)

# Whitelist allowed tables and columns for dynamic updates to prevent SQL injection
ALLOWED_UPDATE_FIELDS = {
    'products': {'current_stock', 'safety_stock', 'selling_price', 'unit_cost', 'name', 'category'},
    'inventory': {'quantity_on_hand', 'reserved_quantity', 'available_quantity', 'warehouse_name'},
    'shipments': {'status', 'expected_delivery_date', 'original_delivery_date', 'received_quantity', 'remaining_quantity', 'mitigation_notes'},
    'customer_orders': {'status', 'quantity_ordered', 'quantity_fulfilled', 'expected_ship_date', 'original_ship_date', 'sla_status', 'notes'},
    'suppliers': {'name', 'contact_email', 'country', 'reliability_rating'}
}

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/activity', methods=['GET'])
def get_activity_log():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 25")
    activities = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"activities": activities})

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total Sales Revenue
    cursor.execute("SELECT SUM(total_amount) FROM sales")
    total_sales = cursor.fetchone()[0] or 0.0

    # Total Network Inventory Units
    cursor.execute("SELECT SUM(current_stock) FROM products")
    total_inventory = cursor.fetchone()[0] or 0

    # Open Customer Orders
    cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE status = 'Pending'")
    open_orders_count = cursor.fetchone()[0] or 0

    # Inbound Shipments in Transit or Scheduled
    cursor.execute("SELECT COUNT(*) FROM shipments WHERE status NOT IN ('Received', 'Delivered')")
    incoming_shipments_count = cursor.fetchone()[0] or 0

    # Active Disruptions (Currently affecting operations)
    cursor.execute("SELECT COUNT(*) FROM disruptions WHERE is_active = 1 AND status != 'NO IMPACT'")
    active_disruptions_count = cursor.fetchone()[0] or 0

    # Aggregate Revenue At Risk across all active disruptions
    cursor.execute("SELECT impact_summary_json FROM disruptions WHERE is_active = 1 AND status = 'IMPACT DETECTED'")
    active_impact_rows = cursor.fetchall()
    revenue_at_risk = 0.0
    at_risk_orders_set = set()

    for row in active_impact_rows:
        if row[0]:
            try:
                imp = json.loads(row[0])
                revenue_at_risk += float(imp.get('order_value_at_risk', 0.0))
                for o in imp.get('affected_customer_orders', []):
                    at_risk_orders_set.add(o.get('order_number'))
            except Exception:
                pass

    # Order Breakdown Metrics
    cursor.execute("SELECT COUNT(*) FROM customer_orders")
    total_orders = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE status = 'Pending'")
    pending_orders = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE status = 'Processing'")
    processing_orders = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE status = 'Completed'")
    completed_orders = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(quantity_ordered), SUM(quantity_fulfilled) FROM customer_orders")
    sum_row = cursor.fetchone()
    total_qty_ordered = sum_row[0] or 0
    total_qty_fulfilled = sum_row[1] or 0

    fulfillment_rate = round((total_qty_fulfilled / total_qty_ordered * 100.0), 1) if total_qty_ordered > 0 else 100.0
    last_updated_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Sales Chart Aggregations
    cursor.execute("SELECT sale_date, SUM(total_amount) FROM sales GROUP BY sale_date ORDER BY sale_date ASC")
    daily_rows = cursor.fetchall()
    daily_labels = [r[0] for r in daily_rows]
    daily_data = [r[1] for r in daily_rows]

    cursor.execute("SELECT strftime('%Y-W%W', sale_date) as wk, SUM(total_amount) FROM sales GROUP BY wk ORDER BY wk ASC")
    weekly_rows = cursor.fetchall()
    weekly_labels = [r[0] for r in weekly_rows]
    weekly_data = [r[1] for r in weekly_rows]

    cursor.execute("SELECT strftime('%Y-%m', sale_date) as mo, SUM(total_amount) FROM sales GROUP BY mo ORDER BY mo ASC")
    monthly_rows = cursor.fetchall()
    monthly_labels = [r[0] for r in monthly_rows]
    monthly_data = [r[1] for r in monthly_rows]

    conn.close()

    return jsonify({
        "metrics": {
            "total_sales": total_sales,
            "total_inventory": total_inventory,
            "open_orders": open_orders_count,
            "incoming_shipments": incoming_shipments_count,
            "active_disruptions": active_disruptions_count,
            "revenue_at_risk": revenue_at_risk,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "processing_orders": processing_orders,
            "completed_orders": completed_orders,
            "at_risk_orders": len(at_risk_orders_set),
            "fulfillment_rate": fulfillment_rate,
            "last_updated": last_updated_str
        },
        "sales_charts": {
            "daily": {"labels": daily_labels, "data": daily_data},
            "weekly": {"labels": weekly_labels, "data": weekly_data},
            "monthly": {"labels": monthly_labels, "data": monthly_data}
        }
    })

@app.route('/api/data', methods=['GET'])
def get_all_data():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM products")
    products = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM suppliers")
    raw_suppliers = [dict(r) for r in cursor.fetchall()]
    suppliers = []

    for s in raw_suppliers:
        s_id = s['id']
        cursor.execute("SELECT COUNT(*) FROM shipments WHERE supplier_id = ? AND status NOT IN ('Received', 'Delivered')", (s_id,))
        active_shps = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM shipments WHERE supplier_id = ? AND status = 'Delayed'", (s_id,))
        delayed_shps = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM shipments WHERE supplier_id = ?", (s_id,))
        total_shps = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(remaining_quantity) FROM shipments WHERE supplier_id = ? AND status IN ('In Transit', 'Delayed', 'Partially Received', 'Scheduled')", (s_id,))
        units_transit = cursor.fetchone()[0] or 0

        delivery_status = f"Delayed ({delayed_shps} shipment)" if delayed_shps > 0 else "On Schedule"
        on_time_pct = round(((total_shps - delayed_shps) / max(1, total_shps)) * 100.0, 1)

        s['active_shipments'] = active_shps
        s['delayed_shipments'] = delayed_shps
        s['units_in_transit'] = units_transit
        s['delivery_status'] = delivery_status
        s['on_time_delivery'] = f"{on_time_pct}% on-time performance"
        suppliers.append(s)

    cursor.execute('''
    SELECT i.*, p.name as product_name, p.sku 
    FROM inventory i 
    JOIN products p ON i.product_id = p.id
    ''')
    inventory = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT s.*, p.name as product_name, sup.name as supplier_name 
    FROM shipments s 
    JOIN products p ON s.product_id = p.id
    JOIN suppliers sup ON s.supplier_id = sup.id
    ORDER BY s.id ASC
    ''')
    shipments = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT co.*, p.name as product_name 
    FROM customer_orders co 
    JOIN products p ON co.product_id = p.id
    ORDER BY co.id DESC
    ''')
    raw_orders = cursor.fetchall()
    orders = []
    for r in raw_orders:
        o = dict(r)
        fulfilled = o.get('quantity_fulfilled') or 0
        o['quantity_fulfilled'] = fulfilled
        o['quantity_remaining'] = max(0, o['quantity_ordered'] - fulfilled)
        orders.append(o)

    cursor.execute("SELECT * FROM disruptions ORDER BY id DESC")
    raw_disruptions = cursor.fetchall()
    disruptions = []
    for d in raw_disruptions:
        d_dict = dict(d)
        d_dict['extracted_json'] = json.loads(d['extracted_json']) if d['extracted_json'] else {}
        d_dict['impact_summary_json'] = json.loads(d['impact_summary_json']) if d['impact_summary_json'] else {}
        d_dict['evidence_json'] = json.loads(d['evidence_json']) if d['evidence_json'] else {}
        d_dict['trace_json'] = json.loads(d['trace_json']) if d['trace_json'] else {}
        disruptions.append(d_dict)

    conn.close()

    return jsonify({
        "products": products,
        "suppliers": suppliers,
        "inventory": inventory,
        "shipments": shipments,
        "customer_orders": orders,
        "disruptions": disruptions
    })

@app.route('/api/data/update', methods=['POST'])
def update_data():
    payload = request.json or {}
    table = payload.get('table')
    item_id = payload.get('id')
    field = payload.get('field')
    value = payload.get('value')

    if not table or not field or item_id is None:
        return jsonify({"error": "Missing required fields (table, id, field, value)"}), 400

    # Enforce strict table and field whitelisting (Prevents SQL Injection)
    if table not in ALLOWED_UPDATE_FIELDS or field not in ALLOWED_UPDATE_FIELDS[table]:
        return jsonify({"error": f"Unauthorized update on table '{table}', field '{field}'"}), 400

    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid item ID"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Parameterized query with strictly whitelisted identifiers
    query = f"UPDATE {table} SET {field} = ? WHERE id = ?"
    cursor.execute(query, (value, item_id))

    # Synchronize stock if products or inventory are edited directly
    if table == 'products' and field == 'current_stock':
        cursor.execute("UPDATE inventory SET quantity_on_hand = ?, available_quantity = ? WHERE product_id = ?", (value, value, item_id))
    elif table == 'inventory' and field == 'quantity_on_hand':
        cursor.execute("SELECT product_id FROM inventory WHERE id = ?", (item_id,))
        p_row = cursor.fetchone()
        if p_row:
            cursor.execute("SELECT SUM(quantity_on_hand) FROM inventory WHERE product_id = ?", (p_row['product_id'],))
            sum_stock = cursor.fetchone()[0] or 0
            cursor.execute("UPDATE products SET current_stock = ? WHERE id = ?", (sum_stock, p_row['product_id']))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Updated {table} id {item_id}"})

@app.route('/api/data/orders', methods=['POST'])
def add_customer_order():
    payload = request.json or {}
    try:
        product_id = int(payload.get('product_id'))
        customer_name = payload.get('customer_name', '').strip()
        quantity = int(payload.get('quantity'))
        if quantity <= 0:
            return jsonify({"error": "Order quantity must be greater than zero"}), 400
        if not customer_name:
            return jsonify({"error": "Customer name is required"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid order parameters"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT selling_price FROM products WHERE id = ?", (product_id,))
    prod = cursor.fetchone()
    if not prod:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    price = prod['selling_price']
    total_price = price * quantity
    order_num = f"ORD-99{int(datetime.now().timestamp()) % 1000:03d}"
    order_date = datetime.now().strftime('%Y-%m-%d')
    exp_ship = (datetime.now() + timedelta(days=4)).strftime('%Y-%m-%d')

    cursor.execute('''
    INSERT INTO customer_orders (order_number, customer_name, customer_email, product_id, quantity_ordered, quantity_fulfilled, unit_price, total_price, order_date, expected_ship_date, status)
    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'Pending')
    ''', (order_num, customer_name, f"orders@{customer_name.lower().replace(' ', '')}.in", product_id, quantity, price, total_price, order_date, exp_ship))

    log_activity("Customer Order Created", f"{order_num} — {customer_name} ({quantity} units)", entity_ref=order_num, cursor=cursor)

    conn.commit()
    conn.close()

    return jsonify({"success": True, "order_number": order_num})

@app.route('/api/disruptions/report', methods=['POST'])
def report_disruption():
    payload = request.json or {}
    raw_text = payload.get('raw_text', '').strip()
    intake_ts = payload.get('timestamp')

    if not raw_text:
        return jsonify({"error": "No disruption text provided"}), 400

    result = analyze_disruption(raw_text, intake_timestamp=intake_ts, save_record=True)
    return jsonify(result)

@app.route('/api/disruptions/<int:d_id>', methods=['GET'])
def get_disruption_report(d_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM disruptions WHERE id = ?", (d_id,))
    d = cursor.fetchone()
    conn.close()

    if not d:
        return jsonify({"error": "Disruption report not found"}), 404

    d_dict = dict(d)
    d_dict['extracted_json'] = json.loads(d['extracted_json']) if d['extracted_json'] else {}
    d_dict['impact_summary_json'] = json.loads(d['impact_summary_json']) if d['impact_summary_json'] else {}
    d_dict['evidence_json'] = json.loads(d['evidence_json']) if d['evidence_json'] else {}
    d_dict['trace_json'] = json.loads(d['trace_json']) if d['trace_json'] else {}

    # Aliases for frontend and test compatibility
    d_dict['extracted'] = d_dict['extracted_json']
    d_dict['impact_summary'] = d_dict['impact_summary_json']
    d_dict['evidence'] = d_dict['evidence_json']
    d_dict['trace'] = d_dict['trace_json']
    d_dict['disruption_id'] = d_dict['id']

    return jsonify(d_dict)

@app.route('/api/disruptions/<int:d_id>/decision', methods=['POST'])
def record_decision(d_id):
    payload = request.json or {}
    decision = payload.get('decision', '').strip()

    if not decision:
        return jsonify({"error": "Missing 'decision' parameter in request payload"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM disruptions WHERE id = ?", (d_id,))
    d = cursor.fetchone()
    if not d:
        conn.close()
        return jsonify({"error": f"Disruption #{d_id} not found"}), 404

    # 1. Validation: Prevent modifying already resolved and archived disruptions
    if d['is_active'] == 0 and d['resolved_at'] and d['mitigation_status'] == 'Resolved':
        conn.close()
        return jsonify({"error": f"Disruption #{d_id} has already been resolved and archived. Mitigation cannot be modified."}), 400

    # 2. Conflict Detection: Block approval if any contradictions exist unless explicitly overridden
    evidence = json.loads(d['evidence_json']) if d['evidence_json'] else {}
    if evidence.get('contradiction_found'):
        # Log conflict detection
        log_activity(
            "Conflict Detected",
            f"Disruption #{d_id} has contradictions: {evidence.get('contradiction_items', [])}",
            entity_ref=str(d_id),
            cursor=cursor
        )
        # Check for explicit override flag in payload
        if not payload.get('override'):
            conn.close()
            return jsonify({
                "error": "Conflict detected (supplier or quantity mismatch). Resolution required before mitigation approval.",
                "conflicts": evidence.get('contradiction_items', []),
                "message": "Provide 'override': true in payload to force approval after manual reconciliation."
            }), 400
        else:
            # Log that user manually overrode conflict
            log_activity(
                "Conflict Override",
                f"User overridden conflicts for disruption #{d_id}: {evidence.get('contradiction_items', [])}",
                entity_ref=str(d_id),
                cursor=cursor
            )
    # 2. Idempotency Check: Prevent duplicate execution of identical strategy
    if d['human_decision'] == decision and d['mitigation_status'] == 'In Progress':
        conn.close()
        return jsonify({
            "success": True, 
            "already_applied": True, 
            "message": f"Strategy '{decision}' has already been approved and is currently in progress.",
            "is_active": d['is_active'],
            "mitigation_status": d['mitigation_status'],
            "mitigation_cost": d['mitigation_cost']
        }), 200

    shipment_id = d['shipment_id']
    if not shipment_id:
        conn.close()
        return jsonify({"error": f"No shipment is associated with Disruption #{d_id}. Cannot execute logistics mitigation."}), 400

    cursor.execute("SELECT * FROM shipments WHERE id = ?", (shipment_id,))
    shp = cursor.fetchone()
    if not shp:
        conn.close()
        return jsonify({"error": f"Associated shipment #{shipment_id} not found in database master records"}), 404

    # Parse disruption context
    # Preserve original impact summary for auditability
    impact_summary = json.loads(d['impact_summary_json']) if d['impact_summary_json'] else {}
    extracted = json.loads(d['extracted_json']) if d['extracted_json'] else {}
    shortage = impact_summary.get('inventory_shortage', 0)
    val_at_risk = impact_summary.get('order_value_at_risk', 0.0)
    qty_claimed = extracted.get('quantity_affected', 0)
    # Use verified shipment quantity (remaining or total) as upper bound for mitigation quantity
    verified_qty = shp['remaining_quantity'] or shp['quantity']
    units_to_expedite = min(qty_claimed, verified_qty) if qty_claimed > 0 else (shp['remaining_quantity'] or shortage or shp['quantity'])
    shp_code = shp['shipment_code']

    # Update trace to include mitigation execution details
    # (Will be set later after mitigation actions)

    # Duplicate parsing removed – retain earlier verified_qty calculation.


    # Preserve original impact summary for auditability
    orig_impact_json = d['original_impact_summary_json'] or d['impact_summary_json']

    # Rate Model Constants (Documented transparent assumptions)
    unit_freight_rate = 650.0
    customs_surcharge = 25000.0

    # Database Transaction
    try:
        is_active = 1  # Mitigation lifecycle: Approval marks it In Progress; does NOT resolve until goods received
        resolved_at = None
        mitigation_status = "In Progress"
        mitigation_action = decision
        mitigation_cost = 0.0
        mitigation_notes = ""
        revised_eta_str = shp['expected_delivery_date']
        orig_eta_str = shp['original_delivery_date'] or shp['expected_delivery_date']

        # Determine strategy execution
        if "Expedite" in decision or "Air" in decision:
            # OPTION 1: Priority Air Cargo
            mitigation_cost = customs_surcharge + (units_to_expedite * unit_freight_rate)
            mitigation_action = "Priority Air Cargo Expedited"

            # Revised ETA Calculation (Documented Assumptions):
            # Assumption: 48h international air transit + 24h priority customs clearance = 3 calendar days total.
            # Bypasses 5-day ocean port congestion; arrives within 3 days or restores original scheduled ETA.
            try:
                base_orig_dt = datetime.strptime(orig_eta_str, '%Y-%m-%d')
            except Exception:
                base_orig_dt = datetime.now()

            air_eta = datetime.now() + timedelta(days=3)
            if air_eta > (base_orig_dt + timedelta(days=1)):
                air_eta = base_orig_dt + timedelta(days=1)
            revised_eta_str = air_eta.strftime('%Y-%m-%d')

            simulated_tracking = f"[Simulated Air Cargo] AWB-AIR-{shp_code}"
            mitigation_notes = (
                f"Approved Priority Air Cargo for {units_to_expedite} units. "
                f"Assumptions: 48h air transit + 24h customs clearance from {shp['origin']} to {shp['destination']}. "
                f"Surcharge: ₹{mitigation_cost:,.2f} (₹{unit_freight_rate:.0f}/unit + ₹{customs_surcharge:,.0f} priority customs). "
                f"Simulated airway bill assigned: {simulated_tracking}."
            )

            # Update Shipment Record
            cursor.execute('''
            UPDATE shipments 
            SET status = 'In Transit (Expedited Air)',
                expected_delivery_date = ?,
                original_delivery_date = COALESCE(original_delivery_date, ?),
                tracking_number = ?,
                mitigation_notes = ?
            WHERE id = ?
            ''', (revised_eta_str, orig_eta_str, simulated_tracking, mitigation_notes, shipment_id))

            # Update Customer Orders where allocation & delivery logic supports it
            cursor.execute("SELECT * FROM customer_orders WHERE product_id = ? AND status = 'Pending'", (shp['product_id'],))
            cust_orders = cursor.fetchall()
            for co in cust_orders:
                try:
                    ord_expected = datetime.strptime(co['expected_ship_date'], '%Y-%m-%d')
                    can_fulfill_on_time = air_eta <= ord_expected
                except Exception:
                    can_fulfill_on_time = True

                sla_status = 'Protected (Air Expedited)' if can_fulfill_on_time else 'Rescheduled (Air Expedited)'
                order_note = f"SLA Protected: Inbound shipment {shp_code} expedited via air cargo (ETA: {revised_eta_str}). Commitment preserved." if can_fulfill_on_time else f"Air expedite reduces delivery delay to {revised_eta_str}."

                cursor.execute('''
                UPDATE customer_orders 
                SET original_ship_date = COALESCE(original_ship_date, expected_ship_date),
                    sla_status = ?,
                    notes = ?
                WHERE id = ?
                ''', (sla_status, order_note, co['id']))

            log_activity("Mitigation Action Approved", f"Shipment {shp_code} expedited via priority air cargo. Revised ETA: {revised_eta_str}. Mitigation cost: ₹{mitigation_cost:,.2f}.", entity_ref=shp_code, cursor=cursor)

        elif "Split" in decision:
            # OPTION 2: Split Shipment & Air Cargo Hybrid
            mitigation_cost = customs_surcharge + (shortage * unit_freight_rate)
            mitigation_action = "Split Shipment (Hybrid Air/Ocean)"
            simulated_tracking = f"[Simulated Hybrid] AWB-SPLIT-{shp_code}"
            mitigation_notes = (
                f"Approved Hybrid Split: {shortage} deficit units prioritized via air cargo; remainder continues via ocean schedule. "
                f"Mitigation cost: ₹{mitigation_cost:,.2f}."
            )

            cursor.execute('''
            UPDATE shipments 
            SET status = 'In Transit (Hybrid Air/Ocean)',
                original_delivery_date = COALESCE(original_delivery_date, ?),
                tracking_number = ?,
                mitigation_notes = ?
            WHERE id = ?
            ''', (orig_eta_str, simulated_tracking, mitigation_notes, shipment_id))

            # Protect primary orders with available stock, secondary orders with split batch
            cursor.execute("SELECT * FROM customer_orders WHERE product_id = ? AND status = 'Pending' ORDER BY expected_ship_date ASC, id ASC", (shp['product_id'],))
            cust_orders = cursor.fetchall()
            if cust_orders:
                cursor.execute("UPDATE customer_orders SET sla_status = 'Allocated (On-Hand Stock)', notes = 'Covered by available warehouse stock' WHERE id = ?", (cust_orders[0]['id'],))
                for sec_order in cust_orders[1:]:
                    cursor.execute("UPDATE customer_orders SET sla_status = 'Protected (Air Split Batch)', notes = 'Covered by expedited air split batch arrival' WHERE id = ?", (sec_order['id'],))

            log_activity("Mitigation Action Approved", f"Shipment {shp_code} split into hybrid air/ocean batches. Net deficit {shortage} units prioritized at ₹{mitigation_cost:,.2f}.", entity_ref=shp_code, cursor=cursor)

        elif "Reallocation" in decision or "Stock" in decision:
            # OPTION 3: Stock Reallocation
            mitigation_cost = 0.0
            mitigation_action = "Stock Reallocation & Key Account Prioritization"
            mitigation_notes = "Stock reallocation approved: Available on-hand inventory prioritized for top customer order; secondary commitments deferred."

            cursor.execute('''
            UPDATE shipments 
            SET status = 'Delayed',
                original_delivery_date = COALESCE(original_delivery_date, ?),
                mitigation_notes = ?
            WHERE id = ?
            ''', (orig_eta_str, mitigation_notes, shipment_id))

            cursor.execute("SELECT * FROM customer_orders WHERE product_id = ? AND status = 'Pending' ORDER BY expected_ship_date ASC, id ASC", (shp['product_id'],))
            cust_orders = cursor.fetchall()
            if cust_orders:
                cursor.execute("UPDATE customer_orders SET sla_status = 'Prioritized (Stock Reallocated)', notes = 'Prioritized with available on-hand stock' WHERE id = ?", (cust_orders[0]['id'],))
                for sec_order in cust_orders[1:]:
                    cursor.execute("UPDATE customer_orders SET sla_status = 'Deferred Pending Shipment', notes = 'Delivery deferred pending ocean shipment arrival' WHERE id = ?", (sec_order['id'],))

            log_activity("Mitigation Action Approved", f"Stock reallocation approved for product {shp['product_id']}. Available stock prioritized for top accounts.", entity_ref=shp_code, cursor=cursor)

        elif "Reject" in decision or "Standby" in decision:
            # OPTION 4: Reject / Standby
            mitigation_status = "Rejected / Unmitigated"
            mitigation_action = "Rejected - Accept Schedule Slippage"
            mitigation_cost = val_at_risk * 0.05
            mitigation_notes = "Mitigation rejected. Operational decision made to accept ocean transit delay and issue customer apology vouchers."

            cursor.execute('''
            UPDATE shipments 
            SET status = 'Delayed',
                original_delivery_date = COALESCE(original_delivery_date, ?),
                mitigation_notes = ?
            WHERE id = ?
            ''', (orig_eta_str, mitigation_notes, shipment_id))

            cursor.execute("SELECT * FROM customer_orders WHERE product_id = ? AND status = 'Pending'", (shp['product_id'],))
            cust_orders = cursor.fetchall()
            for co in cust_orders:
                cursor.execute("UPDATE customer_orders SET sla_status = 'Delivery Delayed', notes = 'Customer delivery postponed due to unmitigated shipment delay.' WHERE id = ?", (co['id'],))

            log_activity("Mitigation Rejected", f"Mitigation rejected for {shp_code}. Shipment marked Delayed. Customer orders will experience delivery slippage.", entity_ref=shp_code, cursor=cursor)

        else:
            conn.rollback()
            conn.close()
            return jsonify({"error": f"Unknown or invalid mitigation strategy: '{decision}'"}), 400

        # Update trace_json for visual consistency
        trace = json.loads(d['trace_json']) if d['trace_json'] else {"nodes": [], "edges": []}
        if "nodes" in trace:
            for node in trace["nodes"]:
                if node.get("type") == "shipment":
                    node["label"] = f"Shipment: {shp_code} ({decision.replace('Approved: ', '')})"
                    if "details" in node:
                        node["details"]["Status"] = "In Transit (Expedited Air)" if ("Expedite" in decision or "Air" in decision) else ("In Transit (Hybrid Air/Ocean)" if "Split" in decision else "Delayed")
                        node["details"]["Revised ETA"] = revised_eta_str
                        node["details"]["Mitigation Strategy"] = mitigation_action
                elif node.get("type") in ("response", "mitigation"):
                    node["label"] = f"Mitigation: {mitigation_action} ({mitigation_status})"
                    if "details" in node:
                        node["details"]["Status"] = mitigation_status
                        node["details"]["Committed Cost"] = f"₹{mitigation_cost:,.2f}"
                        node["details"]["Notes"] = mitigation_notes

        updated_trace_json = json.dumps(trace)

        # Update Disruption Master Record
        cursor.execute('''
        UPDATE disruptions 
        SET human_decision = ?, 
            is_active = ?, 
            resolved_at = ?, 
            mitigation_action = ?, 
            mitigation_cost = ?,
            mitigation_status = ?,
            mitigation_notes = ?,
            original_impact_summary_json = ?,
            trace_json = ?
        WHERE id = ?
        ''', (decision, is_active, resolved_at, mitigation_action, mitigation_cost, mitigation_status, mitigation_notes, orig_impact_json, updated_trace_json, d_id))

        conn.commit()
        conn.close()

        return jsonify({
            "success": True, 
            "decision": decision, 
            "is_active": is_active,
            "mitigation_status": mitigation_status,
            "mitigation_cost": mitigation_cost,
            "revised_eta": revised_eta_str,
            "mitigation_notes": mitigation_notes
        })

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": f"Failed to execute operational mitigation: {str(e)}"}), 500

@app.route('/api/qa', methods=['POST'])
def qa_query():
    payload = request.json or {}
    question = payload.get('question', '').strip()
    if not question:
        return jsonify({"error": "No question provided"}), 400

    answer = ask_system_question(question)
    return jsonify({"question": question, "answer": answer})

@app.route('/api/shipments/<int:s_id>/receive', methods=['POST'])
def receive_shipment_goods(s_id):
    """
    Goods Receiving Handler:
    1. Updates shipment received_quantity, remaining_quantity, and status.
    2. Atomically increments product inventory stock across tables.
    3. If an active disruption exists for this product, recalculates impact without inserting duplicates.
    """
    payload = request.json or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shipments WHERE id = ?", (s_id,))
    shipment = cursor.fetchone()
    if not shipment:
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

    try:
        qty_to_receive = int(payload.get('received_qty', shipment['remaining_quantity']))
        if qty_to_receive <= 0:
            conn.close()
            return jsonify({"error": "Invalid receive quantity"}), 400
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"error": "Receive quantity must be a valid integer"}), 400

    if qty_to_receive > shipment['remaining_quantity']:
        qty_to_receive = shipment['remaining_quantity']

    new_received = shipment['received_quantity'] + qty_to_receive
    new_remaining = max(0, shipment['quantity'] - new_received)
    new_status = 'Received' if new_remaining == 0 else 'Partially Received'

    # Update shipment record
    cursor.execute('''
    UPDATE shipments 
    SET received_quantity = ?, remaining_quantity = ?, status = ? 
    WHERE id = ?
    ''', (new_received, new_remaining, new_status, s_id))

    # Atomically adjust inventory stock across tables
    adjust_inventory_stock(shipment['product_id'], qty_to_receive, cursor=cursor)

    cursor.execute("SELECT current_stock, name FROM products WHERE id = ?", (shipment['product_id'],))
    prod = cursor.fetchone()

    # Log activity
    if new_remaining == 0:
        log_activity("Shipment Fully Received", f"{shipment['shipment_code']} — {qty_to_receive} units received into inventory", entity_ref=shipment['shipment_code'], cursor=cursor)
    else:
        log_activity("Shipment Partially Received", f"{shipment['shipment_code']} — {qty_to_receive} units received ({new_remaining} remaining)", entity_ref=shipment['shipment_code'], cursor=cursor)

    log_activity("Inventory Stock Updated", f"{prod['name']} — {qty_to_receive} units added to stock (Total: {prod['current_stock']} units)", entity_ref=prod['name'], cursor=cursor)

    # Check for active disruptions specific to THIS product only
    cursor.execute('''
    SELECT * FROM disruptions 
    WHERE product_id = ? AND is_active = 1
    ORDER BY id DESC LIMIT 1
    ''', (shipment['product_id'],))
    active_d = cursor.fetchone()

    conn.commit()
    conn.close()

    # Recalculate impact in-memory without inserting duplicate disruption records
    recalculated_report = None
    if active_d:
        recalculated_report = analyze_disruption(active_d['raw_text'], save_record=False)
        recalculated_report['disruption_id'] = active_d['id']

        # If shortage is completely resolved, genuinely resolve the disruption in the DB
        if recalculated_report['impact_summary']['inventory_shortage'] == 0:
            recalc_conn = get_db_connection()
            recalc_cursor = recalc_conn.cursor()
            resolved_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            recalc_cursor.execute('''
            UPDATE disruptions 
            SET is_active = 0, 
                status = 'NO IMPACT',
                mitigation_status = 'Resolved',
                resolved_at = ?
            WHERE id = ?
            ''', (resolved_ts, active_d['id']))
            log_activity("Disruption Resolved", f"Inbound goods receipt of {qty_to_receive} units on {shipment['shipment_code']} eliminated net shortage. Disruption #{active_d['id']} genuinely resolved.", entity_ref=f"INC-#{active_d['id']}", cursor=recalc_cursor)
            recalc_conn.commit()
            recalc_conn.close()

    return jsonify({
        "success": True,
        "shipment_code": shipment['shipment_code'],
        "product_name": prod['name'],
        "received_qty": qty_to_receive,
        "total_received": new_received,
        "remaining_qty": new_remaining,
        "new_status": new_status,
        "updated_stock": prod['current_stock'],
        "recalculated_report": recalculated_report
    })

@app.route('/api/orders/<int:o_id>/fulfill', methods=['POST'])
def fulfill_customer_order(o_id):
    """
    Order Fulfillment Handler:
    1. Validates quantity against available inventory.
    2. Atomically updates order and decrements inventory across tables.
    3. Re-evaluates active disruption for this product without creating duplicates.
    """
    payload = request.json or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM customer_orders WHERE id = ?", (o_id,))
    order = cursor.fetchone()
    if not order:
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    current_fulfilled = order['quantity_fulfilled'] or 0
    remaining_demand = max(0, order['quantity_ordered'] - current_fulfilled)

    try:
        qty_to_fulfill = int(payload.get('fulfill_qty', remaining_demand))
        if qty_to_fulfill <= 0:
            conn.close()
            return jsonify({"error": "Invalid fulfillment quantity"}), 400
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"error": "Fulfillment quantity must be a valid integer"}), 400

    if qty_to_fulfill > remaining_demand:
        qty_to_fulfill = remaining_demand

    cursor.execute("SELECT current_stock, name FROM products WHERE id = ?", (order['product_id'],))
    prod = cursor.fetchone()
    if not prod:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    if prod['current_stock'] < qty_to_fulfill:
        conn.close()
        return jsonify({"error": f"Insufficient stock. Available: {prod['current_stock']} units, requested: {qty_to_fulfill} units."}), 400

    new_fulfilled = current_fulfilled + qty_to_fulfill
    new_remaining = max(0, order['quantity_ordered'] - new_fulfilled)
    new_status = 'Completed' if new_remaining == 0 else 'Partially Fulfilled'

    cursor.execute('''
    UPDATE customer_orders 
    SET quantity_fulfilled = ?, status = ? 
    WHERE id = ?
    ''', (new_fulfilled, new_status, o_id))

    # Atomically deduct stock
    adjust_inventory_stock(order['product_id'], -qty_to_fulfill, cursor=cursor)

    cursor.execute("SELECT current_stock FROM products WHERE id = ?", (order['product_id'],))
    updated_prod = cursor.fetchone()

    log_activity("Customer Order Fulfillment", f"{order['order_number']} — {qty_to_fulfill} units fulfilled for {order['customer_name']}", entity_ref=order['order_number'], cursor=cursor)
    if new_status == 'Completed':
        log_activity("Customer Order Completed", f"{order['order_number']} — Order fully fulfilled and closed", entity_ref=order['order_number'], cursor=cursor)

    # Check for active disruptions specific to this product
    cursor.execute('''
    SELECT * FROM disruptions 
    WHERE product_id = ? AND is_active = 1
    ORDER BY id DESC LIMIT 1
    ''', (order['product_id'],))
    active_d = cursor.fetchone()

    conn.commit()
    conn.close()

    recalculated_report = None
    if active_d:
        recalculated_report = analyze_disruption(active_d['raw_text'], save_record=False)
        recalculated_report['disruption_id'] = active_d['id']

    return jsonify({
        "success": True,
        "order_number": order['order_number'],
        "product_name": prod['name'],
        "fulfilled_qty": qty_to_fulfill,
        "total_fulfilled": new_fulfilled,
        "remaining_qty": new_remaining,
        "new_status": new_status,
        "updated_stock": updated_prod['current_stock'],
        "recalculated_report": recalculated_report
    })

@app.route('/api/shipments/<int:s_id>/status', methods=['POST'])
def update_shipment_status(s_id):
    payload = request.json or {}
    new_status = payload.get('status', 'In Transit')
    valid_statuses = ['Scheduled', 'In Transit', 'Delayed', 'Partially Received', 'Received', 'In Transit (Expedited Air)', 'In Transit (Hybrid Air/Ocean)']
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status '{new_status}'"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT shipment_code FROM shipments WHERE id = ?", (s_id,))
    shp = cursor.fetchone()
    if not shp:
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

    cursor.execute("UPDATE shipments SET status = ? WHERE id = ?", (new_status, s_id))
    log_activity("Shipment Status Changed", f"{shp['shipment_code']} updated to '{new_status}'", entity_ref=shp['shipment_code'], cursor=cursor)
    conn.commit()
    conn.close()

    return jsonify({"success": True, "status": new_status})

@app.route('/api/seed/reset', methods=['POST'])
def reset_seed():
    init_db(reset=True)
    log_activity("Master Data Reset", "Database reset to clean master seed state", entity_ref="SYSTEM")
    return jsonify({"success": True, "message": "Database reset to clean verified seed state!"})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '127.0.0.1')
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1')
    print(f"--> SupplyChain Sentinel starting on http://{host}:{port} (Debug: {debug_mode})")
    app.run(host=host, port=port, debug=debug_mode)
