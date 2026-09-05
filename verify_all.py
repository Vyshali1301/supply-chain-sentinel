import engine
import database
import json

def clean_str(val):
    return str(val).replace('₹', 'Rs. ')

def run_tests():
    print("--- 1. Resetting Database to Clean Master Seed State (INR Currency) ---")
    database.init_db(reset=True)

    print("\n--- 2. Testing High Impact Delay ---")
    s1 = engine.analyze_disruption("ABC supplier informed us that 500 Laptop X units will be delayed by 5 days because of a transportation problem.")
    print(f"Status: {s1['status']}")
    print(f"Shortage: {s1['impact_summary']['inventory_shortage']} units")
    print(f"Order Value at Risk: Rs. {s1['impact_summary']['order_value_at_risk']:,.2f}")
    print(f"Affected Orders: {[o['order_number'] for o in s1['impact_summary']['affected_customer_orders']]}")
    print(f"Evidence Attribution Source: {s1['evidence']['supplier_match']['source']}")
    print(f"AI Recommendation: {clean_str(s1['ai_recommendation'])}")
    assert s1['status'] == "IMPACT DETECTED", "Expected IMPACT DETECTED"
    assert s1['impact_summary']['inventory_shortage'] == 450, "Expected shortage of 450 units"
    assert len(s1['impact_summary']['affected_customer_orders']) == 2, "Expected 2 affected orders"
    assert s1['impact_summary']['order_value_at_risk'] == 42750000.0, "Expected Rs. 42,750,000 order value at risk"

    print("\n--- 3. Testing No Business Impact Case ---")
    s2 = engine.analyze_disruption("Supplier FastFab announced a 3-day delay on Ergonomic Chair Pro shipments due to port congestion.")
    print(f"Status: {s2['status']}")
    print(f"Shortage: {s2['impact_summary']['inventory_shortage']} units")
    print(f"Remaining Buffer: {s2['impact_summary'].get('remaining_buffer')} units")
    print(f"Explanation: {clean_str(s2['impact_summary']['expected_delivery_impact'])}")
    assert s2['status'] == "NO IMPACT", "Expected NO IMPACT"
    assert s2['impact_summary']['remaining_buffer'] == 370, "Expected remaining stock buffer of 370 units"

    print("\n--- 4. Testing Data Conflict ---")
    s3 = engine.analyze_disruption("Supplier Global Microchip Co reports 1000 units of Laptop X delayed by 10 days.")
    print(f"Status: {s3['status']}")
    print(f"Contradiction Count: {len(s3['evidence']['contradiction_items'])}")
    for item in s3['evidence']['contradiction_items']:
        print(f"  - Issue: {item['issue']} | Claim: {clean_str(item['disruption_claim'])} vs DB: {clean_str(item['db_record'])}")
    assert s3['status'] == "NEEDS VERIFICATION", "Expected NEEDS VERIFICATION"
    assert len(s3['evidence']['contradiction_items']) == 2, "Expected 2 contradiction items"

    print("\n--- 5. Testing Dynamic New Customer Order Impact Recalculation ---")
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO customer_orders (order_number, customer_name, customer_email, product_id, quantity_ordered, unit_price, total_price, order_date, expected_ship_date, status)
    VALUES ('ORD-999', 'Zenith Workspaces', 'orders@zenith.in', 2, 450, 22000.0, 9900000.0, '2026-09-05', '2026-09-09', 'Pending')
    ''')
    conn.commit()
    conn.close()

    s2_new = engine.analyze_disruption("Supplier FastFab announced a 3-day delay on Ergonomic Chair Pro shipments due to port congestion.")
    print(f"Status After New Customer Order: {s2_new['status']}")
    print(f"Recalculated Shortage: {s2_new['impact_summary']['inventory_shortage']} units")
    print(f"Recalculated Order Value at Risk: Rs. {s2_new['impact_summary']['order_value_at_risk']:,.2f}")
    assert s2_new['status'] == "IMPACT DETECTED", "Expected status to dynamically update to IMPACT DETECTED after adding new customer order"
    assert s2_new['impact_summary']['inventory_shortage'] == 80, "Expected recalculated shortage of 80 units"
    assert s2_new['impact_summary']['order_value_at_risk'] == 1760000.0, "Expected recalculated order value at risk of Rs. 1,760,000"

    print("\n--- 6. Testing Grounded Question Answering Engine ---")
    qa1 = engine.ask_system_question("Which orders are currently at risk?")
    print(f"QA (Orders at Risk):\n  {clean_str(qa1)}")

    qa2 = engine.ask_system_question("Why is Order #901 affected?")
    print(f"QA (Order #901):\n  {clean_str(qa2)}")

    qa3 = engine.ask_system_question("Which supplier is causing the largest current impact?")
    print(f"QA (Largest Impact Supplier):\n  {clean_str(qa3)}")

    qa4 = engine.ask_system_question("What is the quantum mechanics equation?")
    print(f"QA (Out of Domain Query):\n  {clean_str(qa4)}")
    assert qa4 == "Insufficient data in database to answer reliably.", "Expected insufficient data response for out of domain query"

    print("\n--- 7. Testing Shipment Lifecycle Management & Goods Receiving (Partial & Full Receipt) ---")
    database.init_db(reset=True)

    disruption_text = "ABC supplier informed us that 500 Laptop X units will be delayed by 5 days because of a transportation problem."
    s_init = engine.analyze_disruption(disruption_text)
    assert s_init['status'] == "IMPACT DETECTED"
    assert s_init['impact_summary']['inventory_shortage'] == 450
    assert s_init['impact_summary']['current_stock'] == 150

    # 7B. Partial Goods Receipt of 200 units on SHP-5001
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE shipments SET received_quantity = 200, remaining_quantity = 300, status = 'Partially Received' WHERE shipment_code = 'SHP-5001'")
    cursor.execute("UPDATE products SET current_stock = current_stock + 200 WHERE id = 1")
    cursor.execute("UPDATE inventory SET quantity_on_hand = quantity_on_hand + 200, available_quantity = available_quantity + 200 WHERE product_id = 1")
    conn.commit()

    cursor.execute("SELECT current_stock FROM products WHERE id = 1")
    stock_after_partial = cursor.fetchone()['current_stock']
    assert stock_after_partial == 350, f"Expected stock 350 after partial receipt of 200, got {stock_after_partial}"

    s_partial = engine.analyze_disruption(disruption_text)
    print(f"Status after Partial Receipt (200 units): {s_partial['status']}")
    print(f"Recalculated Stock: {s_partial['impact_summary']['current_stock']} units")
    print(f"Recalculated Shortage: {s_partial['impact_summary']['inventory_shortage']} units")
    print(f"Recalculated Order Value at Risk: Rs. {s_partial['impact_summary']['order_value_at_risk']:,.2f}")
    assert s_partial['status'] == "IMPACT DETECTED", "Expected status still IMPACT DETECTED after partial receipt"
    assert s_partial['impact_summary']['inventory_shortage'] == 250, "Expected shortage to drop from 450 to 250 units"
    assert s_partial['impact_summary']['order_value_at_risk'] == 23750000.0, "Expected value at risk to drop to Rs. 23,750,000"

    # 7C. Receive remaining 300 units on SHP-5001
    cursor.execute("UPDATE shipments SET received_quantity = 500, remaining_quantity = 0, status = 'Received' WHERE shipment_code = 'SHP-5001'")
    cursor.execute("UPDATE products SET current_stock = current_stock + 300 WHERE id = 1")
    cursor.execute("UPDATE inventory SET quantity_on_hand = quantity_on_hand + 300, available_quantity = available_quantity + 300 WHERE product_id = 1")
    conn.commit()

    cursor.execute("SELECT current_stock FROM products WHERE id = 1")
    stock_after_full = cursor.fetchone()['current_stock']
    assert stock_after_full == 650, f"Expected stock 650 after full receipt of remaining 300, got {stock_after_full}"

    cursor.execute("SELECT status FROM shipments WHERE shipment_code = 'SHP-5001'")
    shipment_status = cursor.fetchone()['status']
    assert shipment_status == "Received", f"Expected shipment status 'Received', got '{shipment_status}'"

    s_full = engine.analyze_disruption(disruption_text)
    print(f"Status after Full Receipt (Remaining 300 units): {s_full['status']}")
    print(f"Recalculated Stock Buffer: {s_full['impact_summary']['remaining_buffer']} units")
    assert s_full['status'] == "NO IMPACT", "Expected status to update to NO IMPACT after full receipt"
    assert s_full['impact_summary']['remaining_buffer'] == 50, "Expected remaining stock buffer of 50 units"

    conn.close()

    print("\n==========================================")
    print("[SUCCESS] ALL ENTERPRISE VERIFICATION TESTS PASSED!")
    print("==========================================")

if __name__ == '__main__':
    run_tests()

