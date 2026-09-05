import os
import json
from flask import Flask, render_template, request, jsonify
from database import init_db, get_db_connection, log_activity
from engine import analyze_disruption
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='static', template_folder='templates')

# Initialize DB on startup
init_db(reset=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/activity', methods=['GET'])
def get_activity_log():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 20")
    activities = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"activities": activities})

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total Sales
    cursor.execute("SELECT SUM(total_amount) FROM sales")
    total_sales = cursor.fetchone()[0] or 0.0

    # Current Total Inventory Units
    cursor.execute("SELECT SUM(current_stock) FROM products")
    total_inventory = cursor.fetchone()[0] or 0

    # Open Orders Count
    cursor.execute("SELECT COUNT(*) FROM customer_orders WHERE status = 'Pending'")
    open_orders_count = cursor.fetchone()[0] or 0

    # Incoming Shipments Count
    cursor.execute("SELECT COUNT(*) FROM shipments WHERE status NOT IN ('Received', 'Delivered')")
    incoming_shipments_count = cursor.fetchone()[0] or 0

    # Active Disruptions Count
    cursor.execute("SELECT COUNT(*) FROM disruptions WHERE status != 'NO IMPACT'")
    active_disruptions_count = cursor.fetchone()[0] or 0

    # Revenue At Risk from active disruption
    cursor.execute("SELECT impact_summary_json FROM disruptions WHERE status = 'IMPACT DETECTED' ORDER BY id DESC LIMIT 1")
    latest_impact_row = cursor.fetchone()
    revenue_at_risk = 0.0
    at_risk_orders_count = 0
    if latest_impact_row and latest_impact_row[0]:
        try:
            imp = json.loads(latest_impact_row[0])
            revenue_at_risk = float(imp.get('order_value_at_risk', 0.0))
            at_risk_orders_count = len(imp.get('affected_customer_orders', []))
        except Exception:
            pass

    # Dynamic Customer Order Breakdown Metrics
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

    if total_qty_ordered > 0:
        fulfillment_rate = round((total_qty_fulfilled / total_qty_ordered * 100.0), 1)
    else:
        fulfillment_rate = "N/A"

    last_updated_str = datetime.now().strftime('%d %b %Y, %I:%M %p')

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
            "at_risk_orders": at_risk_orders_count,
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

        cursor.execute("SELECT SUM(remaining_quantity) FROM shipments WHERE supplier_id = ? AND status IN ('In Transit', 'Delayed', 'Partially Received')", (s_id,))
        units_transit = cursor.fetchone()[0] or 0

        delivery_status = f"Delayed ({delayed_shps} shipment)" if delayed_shps > 0 else "On Schedule"
        s['active_shipments'] = active_shps
        s['delayed_shipments'] = delayed_shps
        s['units_in_transit'] = units_transit
        s['delivery_status'] = delivery_status
        s['on_time_delivery'] = "Insufficient historical data"
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
    payload = request.json
    table = payload.get('table')
    item_id = payload.get('id')
    field = payload.get('field')
    value = payload.get('value')

    valid_tables = ['products', 'inventory', 'shipments', 'customer_orders', 'suppliers']
    if table not in valid_tables:
        return jsonify({"error": "Invalid table"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = f"UPDATE {table} SET {field} = ? WHERE id = ?"
    cursor.execute(query, (value, item_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": f"Updated {table} id {item_id}"})

@app.route('/api/data/orders', methods=['POST'])
def add_customer_order():
    """
    Allows adding a new customer order dynamically (Scenario D: Dynamic recalculation).
    """
    payload = request.json
    product_id = int(payload.get('product_id'))
    customer_name = payload.get('customer_name')
    quantity = int(payload.get('quantity'))

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
    INSERT INTO customer_orders (order_number, customer_name, customer_email, product_id, quantity_ordered, unit_price, total_price, order_date, expected_ship_date, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (order_num, customer_name, f"orders@{customer_name.lower().replace(' ', '')}.com", product_id, quantity, price, total_price, order_date, exp_ship, 'Pending'))

    log_activity("Customer Order Created", f"{order_num} — {customer_name} ({quantity} units)", entity_ref=order_num, cursor=cursor)

    conn.commit()
    conn.close()

    return jsonify({"success": True, "order_number": order_num})

@app.route('/api/disruptions/report', methods=['POST'])
def report_disruption():
    payload = request.json
    raw_text = payload.get('raw_text', '')
    if not raw_text.strip():
        return jsonify({"error": "No disruption text provided"}), 400

    result = analyze_disruption(raw_text)
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

    return jsonify(d_dict)

@app.route('/api/disruptions/<int:d_id>/decision', methods=['POST'])
def record_decision(d_id):
    payload = request.json
    decision = payload.get('decision', 'Pending Review')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE disruptions SET human_decision = ? WHERE id = ?", (decision, d_id))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "decision": decision})

from engine import analyze_disruption, ask_system_question

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
    Goods Receiving & Partial Receiving Handler:
    1. Updates shipment received_quantity, remaining_quantity, and status ('Partially Received' or 'Received').
    2. Increments product's current_stock in products table by received quantity.
    3. Re-runs active disruption analysis to automatically update shortage, affected orders, and order value at risk.
    """
    payload = request.json or {}
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM shipments WHERE id = ?", (s_id,))
    shipment = cursor.fetchone()
    if not shipment:
        conn.close()
        return jsonify({"error": "Shipment not found"}), 404

    qty_to_receive = int(payload.get('received_qty', shipment['remaining_quantity']))
    if qty_to_receive <= 0:
        conn.close()
        return jsonify({"error": "Invalid receive quantity"}), 400

    if qty_to_receive > shipment['remaining_quantity']:
        qty_to_receive = shipment['remaining_quantity']

    new_received = shipment['received_quantity'] + qty_to_receive
    new_remaining = max(0, shipment['quantity'] - new_received)
    new_status = 'Received' if new_remaining == 0 else 'Partially Received'

    # 1. Update Shipment record
    cursor.execute('''
    UPDATE shipments 
    SET received_quantity = ?, remaining_quantity = ?, status = ? 
    WHERE id = ?
    ''', (new_received, new_remaining, new_status, s_id))

    # 2. Update Product Inventory stock
    cursor.execute('''
    UPDATE products 
    SET current_stock = current_stock + ? 
    WHERE id = ?
    ''', (qty_to_receive, shipment['product_id']))

    # Also update inventory table for consistency
    cursor.execute('''
    UPDATE inventory 
    SET quantity_on_hand = quantity_on_hand + ?, available_quantity = available_quantity + ?
    WHERE product_id = ?
    ''', (qty_to_receive, qty_to_receive, shipment['product_id']))

    conn.commit()

    # Get updated stock
    cursor.execute("SELECT current_stock, name FROM products WHERE id = ?", (shipment['product_id'],))
    prod = cursor.fetchone()

    # Log operational activities
    if new_remaining == 0:
        log_activity("Shipment Fully Received", f"{shipment['shipment_code']} — {qty_to_receive} units received into inventory", entity_ref=shipment['shipment_code'], cursor=cursor)
    else:
        log_activity("Shipment Partially Received", f"{shipment['shipment_code']} — {qty_to_receive} units received into inventory ({new_remaining} remaining)", entity_ref=shipment['shipment_code'], cursor=cursor)

    log_activity("Inventory Updated", f"{prod['name']} — {qty_to_receive} units added to stock (Total: {prod['current_stock']} units)", entity_ref=prod['name'], cursor=cursor)

    # Re-run latest disruption report for this product if present
    cursor.execute("SELECT * FROM disruptions ORDER BY id DESC LIMIT 1")
    latest_d = cursor.fetchone()
    latest_raw_text = latest_d['raw_text'] if latest_d else None

    conn.commit()
    conn.close()

    recalculated_report = None
    if latest_raw_text:
        recalculated_report = analyze_disruption(latest_raw_text)
        log_activity("Customer Order Risk Recalculated", f"Stock level updated. Impact status: {recalculated_report['status']}", entity_ref=shipment['shipment_code'])

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
    1. Validates requested fulfillment quantity against available product inventory stock.
    2. Updates order's quantity_fulfilled, remaining quantity, and status ('Partially Fulfilled' or 'Completed').
    3. Decrements product's current_stock in products and inventory tables.
    4. Re-runs active disruption analysis to automatically update shortage, affected orders, and order value at risk.
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

    qty_to_fulfill = int(payload.get('fulfill_qty', remaining_demand))
    if qty_to_fulfill <= 0:
        conn.close()
        return jsonify({"error": "Invalid fulfillment quantity"}), 400

    if qty_to_fulfill > remaining_demand:
        qty_to_fulfill = remaining_demand

    # Check product stock
    cursor.execute("SELECT current_stock, name FROM products WHERE id = ?", (order['product_id'],))
    prod = cursor.fetchone()
    if not prod:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    if prod['current_stock'] < qty_to_fulfill:
        conn.close()
        return jsonify({"error": f"Insufficient stock to fulfill quantity. Current stock: {prod['current_stock']} units, requested: {qty_to_fulfill} units."}), 400

    new_fulfilled = current_fulfilled + qty_to_fulfill
    new_remaining = max(0, order['quantity_ordered'] - new_fulfilled)
    new_status = 'Completed' if new_remaining == 0 else 'Partially Fulfilled'

    # 1. Update Order record
    cursor.execute('''
    UPDATE customer_orders 
    SET quantity_fulfilled = ?, status = ? 
    WHERE id = ?
    ''', (new_fulfilled, new_status, o_id))

    # 2. Decrement Product Inventory stock
    cursor.execute('''
    UPDATE products 
    SET current_stock = current_stock - ? 
    WHERE id = ?
    ''', (qty_to_fulfill, order['product_id']))

    cursor.execute('''
    UPDATE inventory 
    SET quantity_on_hand = max(0, quantity_on_hand - ?), available_quantity = max(0, available_quantity - ?)
    WHERE product_id = ?
    ''', (qty_to_fulfill, qty_to_fulfill, order['product_id']))

    # Get updated stock
    cursor.execute("SELECT current_stock FROM products WHERE id = ?", (order['product_id'],))
    updated_prod = cursor.fetchone()

    # Log operational activities
    log_activity("Customer Order Fulfillment Updated", f"{order['order_number']} — {qty_to_fulfill} units fulfilled for {order['customer_name']}", entity_ref=order['order_number'], cursor=cursor)
    if new_status == 'Completed':
        log_activity("Customer Order Completed", f"{order['order_number']} — Order fully fulfilled and closed", entity_ref=order['order_number'], cursor=cursor)
    log_activity("Inventory Updated", f"{prod['name']} — {qty_to_fulfill} units allocated to order (Remaining stock: {updated_prod['current_stock']})", entity_ref=prod['name'], cursor=cursor)

    # Re-run latest disruption report if present
    cursor.execute("SELECT * FROM disruptions ORDER BY id DESC LIMIT 1")
    latest_d = cursor.fetchone()
    latest_raw_text = latest_d['raw_text'] if latest_d else None

    conn.commit()
    conn.close()

    recalculated_report = None
    if latest_raw_text:
        recalculated_report = analyze_disruption(latest_raw_text)
        log_activity("Customer Order Risk Recalculated", f"Stock level updated. Impact status: {recalculated_report['status']}", entity_ref=order['order_number'])

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
    valid_statuses = ['Scheduled', 'In Transit', 'Delayed', 'Partially Received', 'Received']
    if new_status not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT shipment_code FROM shipments WHERE id = ?", (s_id,))
    shp = cursor.fetchone()
    shp_code = shp['shipment_code'] if shp else f"SHP-{s_id}"

    cursor.execute("UPDATE shipments SET status = ? WHERE id = ?", (new_status, s_id))
    log_activity("Shipment Status Changed", f"Status updated to '{new_status}'", entity_ref=shp_code, cursor=cursor)
    conn.commit()
    conn.close()

    return jsonify({"success": True, "status": new_status})

@app.route('/api/seed/reset', methods=['POST'])
def reset_seed():
    init_db(reset=True)
    log_activity("Master Data Reset", "Database reset to clean master seed state", entity_ref="SYSTEM")
    return jsonify({"success": True, "message": "Database reset to clean seed data state!"})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '0.0.0.0')
    print(f"--> SupplyChain Sentinel starting on http://localhost:{port}")
    app.run(host=host, port=port, debug=True)
