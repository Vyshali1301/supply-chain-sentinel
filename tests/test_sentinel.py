import os
import json
import pytest
from datetime import datetime, timedelta

# Ensure testing against local SQLite
os.environ['PORT'] = '8000'
os.environ['HOST'] = '127.0.0.1'

import database
import engine
import app as flask_app

@pytest.fixture(autouse=True)
def clean_db():
    """Reset the database to clean master seed state before each test."""
    database.init_db(reset=True)
    yield

@pytest.fixture
def client():
    """Flask test client."""
    flask_app.app.config['TESTING'] = True
    with flask_app.app.test_client() as client:
        yield client

# 1. Database & Foreign Key Integrity
def test_database_foreign_keys_enabled():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    fk_status = cursor.fetchone()[0]
    conn.close()
    assert fk_status == 1, "SQLite foreign keys must be strictly enforced"

def test_inventory_atomic_adjustment():
    # Adjust Laptop X (product_id = 1) by +50 units
    new_stock = database.adjust_inventory_stock(1, 50)
    assert new_stock == 200

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_stock FROM products WHERE id = 1")
    prod_stock = cursor.fetchone()['current_stock']
    cursor.execute("SELECT SUM(quantity_on_hand) FROM inventory WHERE product_id = 1")
    inv_stock = cursor.fetchone()[0]
    conn.close()

    assert prod_stock == 200
    assert inv_stock == 200, "products.current_stock and inventory.quantity_on_hand must remain synchronized"

# 2. Security: Whitelist Protection against SQL Injection
def test_sql_injection_prevention(client):
    # Attempt unauthorized column injection in update endpoint
    malicious_payload = {
        "table": "products",
        "id": 1,
        "field": "selling_price = 0; DROP TABLE sales; --",
        "value": 100
    }
    res = client.post('/api/data/update', json=malicious_payload)
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data
    assert "Unauthorized update" in data["error"]

    # Attempt updating a table not in whitelist
    res2 = client.post('/api/data/update', json={"table": "disruptions", "id": 1, "field": "status", "value": "Hacked"})
    assert res2.status_code == 400

    # Authorized update should succeed
    res3 = client.post('/api/data/update', json={"table": "products", "id": 1, "field": "selling_price", "value": 98000.0})
    assert res3.status_code == 200

# 3. Disruption Impact Detection & FIFO Order Allocation
def test_disruption_impact_and_fifo_order_allocation():
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days because of freight transport issues."
    result = engine.analyze_disruption(notice)

    assert result['status'] == "IMPACT DETECTED"
    impact = result['impact_summary']
    assert impact['current_stock'] == 150
    assert impact['open_order_demand'] == 600
    assert impact['inventory_shortage'] == 450

    # Verify FIFO allocation: ORD-901 (demand 350) gets 150 from stock, 200 unfulfilled.
    # ORD-902 (demand 250) gets 0 from stock, 250 unfulfilled.
    orders = impact['affected_customer_orders']
    assert len(orders) == 2
    assert orders[0]['order_number'] == 'ORD-901'
    assert orders[0]['qty_unfulfilled'] == 200
    assert orders[1]['order_number'] == 'ORD-902'
    assert orders[1]['qty_unfulfilled'] == 250

    # Exposure: 200 * 95000 + 250 * 95000 = 42,750,000
    assert impact['order_value_at_risk'] == 42750000.0

    # Dynamic mitigation checks: no hardcoded strings
    options = result['response_options']
    assert len(options) == 4
    opt1 = options[0]
    assert "Taipei Port" in opt1['action'] or "JNP Port" in opt1['action']
    assert "Estimated Air Cargo Surcharge" in opt1['cost']
    assert "%" in opt1['trade_off']

# 4. Disruption No Business Impact
def test_disruption_no_business_impact():
    notice = "Supplier FastFab announced a 3-day delay on Ergonomic Chair Pro shipments due to port congestion."
    result = engine.analyze_disruption(notice)

    assert result['status'] == "NO IMPACT"
    impact = result['impact_summary']
    assert impact['inventory_shortage'] == 0
    assert impact['remaining_buffer'] == 370
    assert "completely fulfills all open customer commitments" in impact['expected_delivery_impact']

# 5. Data Contradiction Detection
def test_disruption_contradiction_detection():
    # Disruption attributes Laptop X to Global Microchip Co (which actually belongs to ABC Supplier Co)
    # and claims 1000 units (while active shipment is 500 units)
    notice = "Supplier Global Microchip Co reports 1000 units of Laptop X delayed by 10 days."
    result = engine.analyze_disruption(notice)

    assert result['status'] == "NEEDS VERIFICATION"
    evidence = result['evidence']
    assert evidence['contradiction_found'] is True
    assert len(evidence['contradiction_items']) >= 1

# 6. Multiple Shipments Support
def test_multiple_shipments_resolution():
    # Laptop X has SHP-5001 (500 units) and SHP-5004 (200 units)
    notice = "Carrier reports shipment SHP-5004 containing Laptop X is delayed by 3 days."
    result = engine.analyze_disruption(notice)

    evidence = result['evidence']
    assert evidence['shipment_match']['shipment_code'] == 'SHP-5004'
    assert evidence['shipment_match']['remaining_qty'] == 200

# 7. Partial Goods Receiving Without Duplicate Disruptions
def test_partial_receiving_and_in_place_recalculation(client):
    # 1. Report initial disruption
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    assert rep['status'] == "IMPACT DETECTED"
    initial_d_id = rep['disruption_id']

    # Check count of disruptions in DB
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM disruptions")
    initial_count = c.fetchone()[0]
    conn.close()

    # 2. Receive 200 units of SHP-5001
    res = client.post('/api/shipments/1/receive', json={"received_qty": 200})
    assert res.status_code == 200
    data = res.get_json()
    assert data['updated_stock'] == 350
    assert data['new_status'] == 'Partially Received'

    # Recalculated report in response must reflect reduced shortage (450 - 200 = 250)
    assert data['recalculated_report'] is not None
    assert data['recalculated_report']['impact_summary']['inventory_shortage'] == 250

    # Ensure no duplicate disruption records were created
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM disruptions")
    new_count = c.fetchone()[0]
    conn.close()
    assert new_count == initial_count, "Receiving goods must not create duplicate disruption records in the database"

# 8. Order Partial Fulfillment Logic
def test_customer_order_partial_fulfillment(client):
    # ORD-901 ordered 350 units. Laptop X has 150 on hand.
    # Try fulfilling 200 (should fail due to insufficient stock)
    fail_res = client.post('/api/orders/1/fulfill', json={"fulfill_qty": 200})
    assert fail_res.status_code == 400

    # Fulfill 100 units
    succ_res = client.post('/api/orders/1/fulfill', json={"fulfill_qty": 100})
    assert succ_res.status_code == 200
    data = succ_res.get_json()
    assert data['total_fulfilled'] == 100
    assert data['remaining_qty'] == 250
    assert data['new_status'] == 'Partially Fulfilled'
    assert data['updated_stock'] == 50

# 9. Operational Human Decision Execution & Mitigation Lifecycle
def test_human_decision_option1_mitigation_lifecycle(client):
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']

    # Step A: Approve Expedite Air Freight
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res.status_code == 200
    data = res.get_json()
    
    # Mitigation lifecycle: Approval marks it in progress; does NOT resolve until goods received
    assert data['is_active'] == 1, "Disruption must remain active (in progress) until operational receipt"
    assert data['mitigation_status'] == 'In Progress'
    assert data['mitigation_cost'] == 350000.0, "Expected calculated cost of Rs. 350,000.00"
    assert data['revised_eta'] is not None

    # Step B: Verify database records
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status, expected_delivery_date, original_delivery_date, tracking_number FROM shipments WHERE id = 1")
    shp = c.fetchone()
    c.execute("SELECT is_active, human_decision, mitigation_status, mitigation_cost, resolved_at FROM disruptions WHERE id = ?", (d_id,))
    d_row = c.fetchone()
    c.execute("SELECT sla_status, notes FROM customer_orders WHERE product_id = 1")
    orders = c.fetchall()
    c.execute("SELECT event_type, description, entity_ref FROM activity_log WHERE entity_ref = 'SHP-5001' ORDER BY id DESC")
    act = c.fetchone()
    conn.close()

    assert shp['status'] == 'In Transit (Expedited Air)'
    assert shp['original_delivery_date'] is not None, "Original delivery date must be preserved"
    assert "[Simulated Air Cargo]" in shp['tracking_number'], "Simulated tracking must be clearly labeled"
    assert d_row['is_active'] == 1
    assert d_row['resolved_at'] is None, "Disruption cannot be marked resolved merely because mitigation was approved"
    assert d_row['mitigation_status'] == 'In Progress'
    assert d_row['mitigation_cost'] == 350000.0
    assert "Expedite" in d_row['human_decision']

    # Step C: Verify customer orders protected
    assert len(orders) >= 2
    for o in orders:
        assert 'Protected' in o['sla_status']

    # Step D: Verify activity log created
    assert act is not None
    assert act['event_type'] == 'Mitigation Action Approved'
    assert 'SHP-5001' in act['description']

def test_duplicate_approval_prevention_idempotency(client):
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']

    # Initial approval
    res1 = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res1.status_code == 200

    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM activity_log WHERE event_type = 'Mitigation Action Approved'")
    initial_log_count = c.fetchone()[0]
    conn.close()

    # Second approval of identical decision
    res2 = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2.get('already_applied') is True, "Second approval must be idempotent"

    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM activity_log WHERE event_type = 'Mitigation Action Approved'")
    final_log_count = c.fetchone()[0]
    conn.close()

    assert final_log_count == initial_log_count, "Idempotent approval must not duplicate activity log records"

def test_transaction_rollback_and_validation(client):
    # Missing decision parameter
    res1 = client.post('/api/disruptions/1/decision', json={})
    assert res1.status_code == 400
    assert "Missing 'decision'" in res1.get_json()['error']

    # Non-existent disruption
    res2 = client.post('/api/disruptions/9999/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res2.status_code == 404
    assert "not found" in res2.get_json()['error']

def test_impact_trace_and_data_consistency(client):
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']

    # Approve Option 1
    client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})

    # Check /api/data shipments
    res_data = client.get('/api/data').get_json()
    shp_5001 = [s for s in res_data['shipments'] if s['shipment_code'] == 'SHP-5001'][0]
    assert shp_5001['status'] == 'In Transit (Expedited Air)'

    # Check /api/disruptions/<d_id> trace_json
    res_d = client.get(f'/api/disruptions/{d_id}').get_json()
    trace = res_d['trace']
    shipment_nodes = [n for n in trace['nodes'] if n.get('type') == 'shipment']
    assert len(shipment_nodes) > 0
    assert shipment_nodes[0]['details']['Status'] == 'In Transit (Expedited Air)'

def test_genuine_disruption_resolution_upon_goods_receipt(client):
    notice = "ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']

    # Approve mitigation
    client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})

    # Goods receipt: receive 500 units into warehouse
    res_rec = client.post('/api/shipments/1/receive', json={"received_qty": 500})
    assert res_rec.status_code == 200

    # Verify disruption is now genuinely resolved
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT is_active, mitigation_status, resolved_at FROM disruptions WHERE id = ?", (d_id,))
    d_row = c.fetchone()
    conn.close()

    assert d_row['is_active'] == 0, "Disruption must be resolved when incoming goods eliminate shortage"
    assert d_row['mitigation_status'] == 'Resolved'
    assert d_row['resolved_at'] is not None

# 10. Operations Assistant Grounded QA
def test_operations_assistant_grounded_qa(client):
    # Query specific order
    res1 = client.post('/api/qa', json={"question": "What is the status of Order ORD-901?"}).get_json()
    assert "ORD-901" in res1['answer']
    assert "Enterprise Hub Pvt Ltd" in res1['answer']

    # Query stock of laptops
    res2 = client.post('/api/qa', json={"question": "What is the current stock of Laptop X?"}).get_json()
    assert "Laptop X" in res2['answer']

    # Query out-of-domain query
    res3 = client.post('/api/qa', json={"question": "What is the weather in Antarctica?"}).get_json()
    assert "Insufficient data" in res3['answer'] or "not found" in res3['answer'].lower()

# 11. Dashboard Metrics Integrity
def test_dashboard_metrics(client):
    res = client.get('/api/dashboard')
    assert res.status_code == 200
    data = res.get_json()
    metrics = data['metrics']
    assert metrics['total_inventory'] > 0
    assert metrics['open_orders'] > 0
    assert metrics['total_sales'] > 0
    assert 'daily' in data['sales_charts']

# 12. Conflict Detection & Override Tests

def test_supplier_mismatch_blocks_approval(client):
    # Notice with supplier mismatch (Global Microchip Co vs actual ABC Supplier)
    notice = "Supplier Global Microchip Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res.status_code == 400
    data = res.get_json()
    assert "conflict" in data["error"].lower()

def test_quantity_mismatch_blocks_approval(client):
    # Notice claims 1000 units but shipment only 500
    notice = "Supplier Global Microchip Co reports 1000 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res.status_code == 400
    data = res.get_json()
    assert "conflict" in data["error"].lower()

def test_override_allows_approval_and_cost_calculation(client):
    notice = "Supplier Global Microchip Co reports 1000 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    # Override conflict
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight", "override": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('mitigation_cost') is not None
    # Expected cost uses verified shipment quantity (500) not claimed 1000
    expected_units = 500
    expected_cost = 25000.0 + expected_units * 650.0
    assert abs(data['mitigation_cost'] - expected_cost) < 1e-2

# 12. Conflict Detection & Override Tests

def test_supplier_mismatch_blocks_approval(client):
    # Notice with supplier mismatch (Global Microchip Co vs actual ABC Supplier)
    notice = "Supplier Global Microchip Co reports 500 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res.status_code == 400
    data = res.get_json()
    assert "conflict" in data["error"].lower()

def test_quantity_mismatch_blocks_approval(client):
    # Notice claims 1000 units but shipment only 500
    notice = "Supplier Global Microchip Co reports 1000 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight"})
    assert res.status_code == 400
    data = res.get_json()
    assert "conflict" in data["error"].lower()

def test_override_allows_approval_and_cost_calculation(client):
    notice = "Supplier Global Microchip Co reports 1000 Laptop X units will be delayed by 5 days."
    rep = client.post('/api/disruptions/report', json={"raw_text": notice}).get_json()
    d_id = rep['disruption_id']
    # Override conflict
    res = client.post(f'/api/disruptions/{d_id}/decision', json={"decision": "Approved: Expedite Air Freight", "override": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data.get('mitigation_cost') is not None
    # Expected cost uses verified shipment quantity (500) not claimed 1000
    expected_units = 500
    expected_cost = 25000.0 + expected_units * 650.0
    assert abs(data['mitigation_cost'] - expected_cost) < 1e-2
