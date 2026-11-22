import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'supply_chain.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Ensure foreign key constraints are strictly enforced in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(reset=False):
    if reset:
        # Instead of deleting the file which can trigger WinError 32 on Windows due to file locks,
        # drop all tables cleanly if the DB exists.
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                conn.execute("PRAGMA foreign_keys = OFF;")
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                tables = [row[0] for row in cursor.fetchall()]
                for t in tables:
                    cursor.execute(f"DROP TABLE IF EXISTS {t};")
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Error resetting tables: {e}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Products Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        selling_price REAL NOT NULL,
        current_stock INTEGER NOT NULL,
        safety_stock INTEGER NOT NULL
    )
    ''')

    # 2. Suppliers Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        contact_email TEXT NOT NULL,
        country TEXT NOT NULL,
        reliability_rating REAL NOT NULL
    )
    ''')

    # 3. Inventory Table (Warehouse-level stock)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        warehouse_name TEXT NOT NULL,
        quantity_on_hand INTEGER NOT NULL,
        reserved_quantity INTEGER NOT NULL,
        available_quantity INTEGER NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    )
    ''')

    # 4. Inbound Shipments Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shipment_code TEXT UNIQUE NOT NULL,
        supplier_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        received_quantity INTEGER DEFAULT 0,
        remaining_quantity INTEGER NOT NULL,
        status TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        expected_delivery_date TEXT NOT NULL,
        original_delivery_date TEXT,
        tracking_number TEXT NOT NULL,
        mitigation_notes TEXT,
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    ''')

    # 5. Customer Orders Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_email TEXT NOT NULL,
        product_id INTEGER NOT NULL,
        quantity_ordered INTEGER NOT NULL,
        quantity_fulfilled INTEGER DEFAULT 0,
        unit_price REAL NOT NULL,
        total_price REAL NOT NULL,
        order_date TEXT NOT NULL,
        expected_ship_date TEXT NOT NULL,
        original_ship_date TEXT,
        sla_status TEXT DEFAULT 'On Schedule',
        notes TEXT,
        status TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    ''')

    # 6. Sales Operations History
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        quantity_sold INTEGER NOT NULL,
        total_amount REAL NOT NULL,
        sale_date TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    ''')

    # 7. Disruptions Table (With Lifecycle, Action, and Resolution tracking)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS disruptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        raw_text TEXT NOT NULL,
        extracted_json TEXT NOT NULL,
        status TEXT NOT NULL,
        impact_summary_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL,
        trace_json TEXT NOT NULL,
        human_decision TEXT DEFAULT 'Pending Review',
        is_active INTEGER DEFAULT 1,
        resolved_at TEXT,
        product_id INTEGER,
        shipment_id INTEGER,
        mitigation_action TEXT,
        mitigation_cost REAL DEFAULT 0.0,
        mitigation_status TEXT DEFAULT 'Pending Review',
        mitigation_notes TEXT,
        original_impact_summary_json TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # 8. Activity Log Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        description TEXT NOT NULL,
        entity_ref TEXT,
        created_at TEXT NOT NULL
    )
    ''')

    # Apply Schema Migrations
    apply_migrations(cursor=cursor)
    conn.commit()

    # Seed data if empty
    cursor.execute('SELECT COUNT(*) FROM products')
    if cursor.fetchone()[0] == 0:
        seed_data(cursor)
        conn.commit()

    conn.close()

def apply_migrations(cursor=None):
    """
    Applies schema additions safely to existing databases without data loss.
    """
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True

    # 1. Customer Orders Table Migrations
    cursor.execute("PRAGMA table_info(customer_orders)")
    order_cols = [r[1] for r in cursor.fetchall()]
    if 'quantity_fulfilled' not in order_cols:
        cursor.execute("ALTER TABLE customer_orders ADD COLUMN quantity_fulfilled INTEGER DEFAULT 0")
    if 'original_ship_date' not in order_cols:
        cursor.execute("ALTER TABLE customer_orders ADD COLUMN original_ship_date TEXT")
    if 'sla_status' not in order_cols:
        cursor.execute("ALTER TABLE customer_orders ADD COLUMN sla_status TEXT DEFAULT 'On Schedule'")
    if 'notes' not in order_cols:
        cursor.execute("ALTER TABLE customer_orders ADD COLUMN notes TEXT")

    # 2. Shipments Table Migrations
    cursor.execute("PRAGMA table_info(shipments)")
    ship_cols = [r[1] for r in cursor.fetchall()]
    if 'original_delivery_date' not in ship_cols:
        cursor.execute("ALTER TABLE shipments ADD COLUMN original_delivery_date TEXT")
    if 'mitigation_notes' not in ship_cols:
        cursor.execute("ALTER TABLE shipments ADD COLUMN mitigation_notes TEXT")

    # 3. Disruptions Table Migrations
    cursor.execute("PRAGMA table_info(disruptions)")
    disrupt_cols = [r[1] for r in cursor.fetchall()]
    if 'is_active' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN is_active INTEGER DEFAULT 1")
    if 'resolved_at' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN resolved_at TEXT")
    if 'product_id' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN product_id INTEGER")
    if 'shipment_id' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN shipment_id INTEGER")
    if 'mitigation_action' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN mitigation_action TEXT")
    if 'mitigation_cost' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN mitigation_cost REAL DEFAULT 0.0")
    if 'mitigation_status' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN mitigation_status TEXT DEFAULT 'Pending Review'")
    if 'mitigation_notes' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN mitigation_notes TEXT")
    if 'original_impact_summary_json' not in disrupt_cols:
        cursor.execute("ALTER TABLE disruptions ADD COLUMN original_impact_summary_json TEXT")

    if close_conn:
        conn.commit()
        conn.close()

def sync_product_inventory(product_id, cursor=None):
    """
    Ensures products.current_stock matches the sum of quantity_on_hand across warehouses.
    """
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True

    cursor.execute("SELECT SUM(quantity_on_hand) FROM inventory WHERE product_id = ?", (product_id,))
    total_on_hand = cursor.fetchone()[0] or 0

    cursor.execute("UPDATE products SET current_stock = ? WHERE id = ?", (total_on_hand, product_id))

    if close_conn:
        conn.commit()
        conn.close()

def adjust_inventory_stock(product_id, delta_qty, warehouse_name=None, cursor=None):
    """
    Atomically updates both inventory table and products table by delta_qty (positive or negative).
    """
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True

    if warehouse_name:
        cursor.execute('''
        UPDATE inventory 
        SET quantity_on_hand = max(0, quantity_on_hand + ?), 
            available_quantity = max(0, available_quantity + ?)
        WHERE product_id = ? AND warehouse_name = ?
        ''', (delta_qty, delta_qty, product_id, warehouse_name))
    else:
        # Default to first warehouse
        cursor.execute('''
        UPDATE inventory 
        SET quantity_on_hand = max(0, quantity_on_hand + ?), 
            available_quantity = max(0, available_quantity + ?)
        WHERE id = (SELECT id FROM inventory WHERE product_id = ? LIMIT 1)
        ''', (delta_qty, delta_qty, product_id))

    # Synchronize products master stock
    cursor.execute("SELECT SUM(quantity_on_hand) FROM inventory WHERE product_id = ?", (product_id,))
    new_stock = cursor.fetchone()[0] or 0
    cursor.execute("UPDATE products SET current_stock = ? WHERE id = ?", (new_stock, product_id))

    if close_conn:
        conn.commit()
        conn.close()

    return new_stock

def seed_data(cursor):
    today = datetime.now()
    
    # 1. Suppliers
    suppliers = [
        ('SUP-01', 'ABC Supplier Co', 'logistics@abcsupplier.com', 'Taiwan', 4.8),
        ('SUP-02', 'FastFab Logistics', 'orders@fastfab.com', 'Vietnam', 4.2),
        ('SUP-03', 'DisplayWorld Ltd', 'support@displayworld.com', 'South Korea', 4.9),
        ('SUP-04', 'Global Microchip Co', 'sales@globalmicrochip.com', 'Singapore', 4.0)
    ]
    cursor.executemany('''
    INSERT INTO suppliers (supplier_code, name, contact_email, country, reliability_rating)
    VALUES (?, ?, ?, ?, ?)
    ''', suppliers)

    # 2. Products (Master Enterprise Catalog - INR Pricing)
    products = [
        ('PROD-101', 'Laptop X', 'Electronics', 60000.0, 95000.0, 150, 100),
        ('PROD-102', 'Ergonomic Chair Pro', 'Office Furniture', 12000.0, 22000.0, 400, 50),
        ('PROD-103', 'UltraHD Monitor 27"', 'Electronics', 18000.0, 32000.0, 80, 30),
        ('PROD-104', 'Mechanical Keyboard K1', 'Accessories', 3500.0, 7500.0, 300, 40)
    ]
    cursor.executemany('''
    INSERT INTO products (sku, name, category, unit_cost, selling_price, current_stock, safety_stock)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', products)

    # 3. Inventory Allocation (Warehouse Master)
    inventory = [
        (1, 'Central Warehouse W-01 (Mumbai)', 150, 150, 0),    # Laptop X: 150 physical on hand
        (2, 'Warehouse W-02 (Bengaluru)', 400, 30, 370),        # Chair: 400 on hand, 30 reserved, 370 available
        (3, 'Central Warehouse W-01 (Mumbai)', 80, 50, 30),      # Monitor: 80 on hand, 50 reserved, 30 available
        (4, 'North Distribution Center (Delhi)', 300, 40, 260)   # Keyboard: 300 on hand, 40 reserved, 260 available
    ]
    cursor.executemany('''
    INSERT INTO inventory (product_id, warehouse_name, quantity_on_hand, reserved_quantity, available_quantity)
    VALUES (?, ?, ?, ?, ?)
    ''', inventory)

    # 4. Inbound Shipments
    deliv_date1 = (today + timedelta(days=3)).strftime('%Y-%m-%d')
    deliv_date2 = (today + timedelta(days=5)).strftime('%Y-%m-%d')
    deliv_date3 = (today + timedelta(days=2)).strftime('%Y-%m-%d')
    deliv_date4 = (today + timedelta(days=8)).strftime('%Y-%m-%d')

    shipments = [
        ('SHP-5001', 1, 1, 500, 0, 500, 'In Transit', 'Taipei Port', 'JNP Port (Mumbai)', deliv_date1, 'TRK-990123'),
        ('SHP-5002', 2, 2, 200, 0, 200, 'In Transit', 'Hai Phong Port', 'Chennai Port', deliv_date2, 'TRK-881204'),
        ('SHP-5003', 3, 3, 150, 0, 150, 'In Transit', 'Incheon Port', 'JNP Port (Mumbai)', deliv_date3, 'TRK-774431'),
        ('SHP-5004', 1, 1, 200, 0, 200, 'Scheduled', 'Taipei Port', 'JNP Port (Mumbai)', deliv_date4, 'TRK-990124')
    ]
    cursor.executemany('''
    INSERT INTO shipments (shipment_code, supplier_id, product_id, quantity, received_quantity, remaining_quantity, status, origin, destination, expected_delivery_date, tracking_number)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', shipments)

    # 5. Customer Orders Master
    order_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    exp_ship1 = (today + timedelta(days=4)).strftime('%Y-%m-%d')
    exp_ship2 = (today + timedelta(days=6)).strftime('%Y-%m-%d')
    exp_ship3 = (today + timedelta(days=5)).strftime('%Y-%m-%d')

    orders = [
        ('ORD-901', 'Enterprise Hub Pvt Ltd', 'procurement@enterprisehub.in', 1, 350, 0, 95000.0, 33250000.0, order_date, exp_ship1, 'Pending'),
        ('ORD-902', 'Acme Systems India', 'buying@acmesystems.in', 1, 250, 0, 95000.0, 23750000.0, order_date, exp_ship2, 'Pending'),
        ('ORD-903', 'Zenith Workspaces', 'admin@zenithwork.in', 2, 30, 0, 22000.0, 660000.0, order_date, exp_ship3, 'Pending'),
        ('ORD-904', 'Apex Tech Solutions', 'orders@apextech.in', 3, 50, 0, 32000.0, 1600000.0, order_date, exp_ship1, 'Pending')
    ]
    cursor.executemany('''
    INSERT INTO customer_orders (order_number, customer_name, customer_email, product_id, quantity_ordered, quantity_fulfilled, unit_price, total_price, order_date, expected_ship_date, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', orders)

    # 6. Sales History (30 Days)
    sales = []
    for i in range(30):
        sale_dt = (today - timedelta(days=30-i)).strftime('%Y-%m-%d')
        qty1 = 5 + (i * 2) % 10
        sales.append((1, qty1, qty1 * 95000.0, sale_dt))
        qty2 = 4 + (i * 3) % 8
        sales.append((2, qty2, qty2 * 22000.0, sale_dt))
        qty3 = 3 + (i * 2) % 6
        sales.append((3, qty3, qty3 * 32000.0, sale_dt))

    cursor.executemany('''
    INSERT INTO sales (product_id, quantity_sold, total_amount, sale_date)
    VALUES (?, ?, ?, ?)
    ''', sales)

    # 7. Initial Activity Log
    seed_activities = [
        ('Master Data Initialized', 'Database loaded with enterprise catalogue and verified records', 'SYSTEM'),
        ('Inbound Shipment Logged', 'SHP-5001 registered for ABC Supplier Co (500 Laptop X units)', 'SHP-5001'),
        ('Inbound Shipment Logged', 'SHP-5002 registered for FastFab Logistics (200 Ergonomic Chair Pro units)', 'SHP-5002'),
        ('Customer Order Registered', 'ORD-901 created for Enterprise Hub Pvt Ltd (350 Laptop X units)', 'ORD-901')
    ]
    for act in seed_activities:
        ts = (today - timedelta(minutes=45)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
        INSERT INTO activity_log (event_type, description, entity_ref, created_at)
        VALUES (?, ?, ?, ?)
        ''', (act[0], act[1], act[2], ts))

def log_activity(event_type, description, entity_ref=None, cursor=None):
    close_conn = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        close_conn = True

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
    INSERT INTO activity_log (event_type, description, entity_ref, created_at)
    VALUES (?, ?, ?, ?)
    ''', (event_type, description, entity_ref, ts))

    if close_conn:
        conn.commit()
        conn.close()

if __name__ == '__main__':
    init_db(reset=True)
    print("Database initialized with foreign keys and multi-shipment lifecycle tracking.")
