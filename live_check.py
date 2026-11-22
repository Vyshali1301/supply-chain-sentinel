"""Live API functional verification against running server."""
import urllib.request, json, sys

base = 'http://127.0.0.1:8000'

def get(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

errors = []

print('1. Dashboard metrics...')
dash = get('/api/dashboard')
m = dash['metrics']
print(f"   total_sales={m['total_sales']:.0f}, inventory={m['total_inventory']}, open_orders={m['open_orders']}, disruptions={m['active_disruptions']}")
if not m['total_inventory'] > 0:
    errors.append('Dashboard: total_inventory is 0')

print()
print('2. Data endpoint...')
data = get('/api/data')
print(f"   Products={len(data['products'])}, Suppliers={len(data['suppliers'])}, Shipments={len(data['shipments'])}, Orders={len(data['customer_orders'])}, Disruptions={len(data['disruptions'])}")
for s in data['shipments']:
    print(f"   {s['shipment_code']} | Status: {s['status']} | Received: {s['received_quantity']} | Remaining: {s['remaining_quantity']}")

print()
print('3. Activity log...')
acts = get('/api/activity')
print(f"   Log entries: {len(acts['activities'])}")
if acts['activities']:
    a = acts['activities'][0]
    print(f"   Latest: {a['event_type']} - {a['description'][:60]}")

print()
print('4. Post disruption analysis...')
rep = post('/api/disruptions/report', {'raw_text': 'ABC Supplier Co reports 500 Laptop X units will be delayed by 5 days due to freight issues.'})
print(f"   Status: {rep['status']}")
print(f"   Shortage: {rep['impact_summary']['inventory_shortage']}")
print(f"   Value at Risk: Rs.{rep['impact_summary']['order_value_at_risk']:,.2f}")
print(f"   Disruption ID: {rep['disruption_id']}")
did = rep['disruption_id']
if rep['status'] != 'IMPACT DETECTED':
    errors.append(f"Disruption status should be IMPACT DETECTED, got {rep['status']}")

print()
print('5. GET disruption by ID (simulates alert card click)...')
drep = get(f'/api/disruptions/{did}')
print(f"   id={drep['id']}, status={drep['status']}, mitigation_status={drep['mitigation_status']}")
ext_keys = list((drep.get('extracted_json') or {}).keys())
imp_keys = list((drep.get('impact_summary_json') or {}).keys())[:8]
print(f"   extracted_json keys: {ext_keys}")
print(f"   impact_summary_json keys (first 8): {imp_keys}")
has_opts = 'response_options' in (drep.get('impact_summary_json') or {})
print(f"   response_options in impact_summary_json: {has_opts}")
if not has_opts:
    errors.append('response_options missing from impact_summary_json — alert card click would show no mitigation options')

print()
print('6. Approve mitigation (Option 1 - Air Cargo)...')
dec = post(f'/api/disruptions/{did}/decision', {'decision': 'Approved: Expedite Air Freight'})
print(f"   success={dec['success']}, is_active={dec['is_active']}, mitigation_status={dec['mitigation_status']}")
print(f"   cost=Rs.{dec['mitigation_cost']:,.2f}, revised_eta={dec['revised_eta']}")
if dec['is_active'] != 1:
    errors.append('Disruption should remain is_active=1 after approval (not resolved until goods received)')
if dec['mitigation_status'] != 'In Progress':
    errors.append(f"mitigation_status should be In Progress, got {dec['mitigation_status']}")

print()
print('7. Verify shipment DB fields post-approval...')
data2 = get('/api/data')
shp5001 = None
for s in data2['shipments']:
    if s['shipment_code'] == 'SHP-5001':
        shp5001 = s
        break
if shp5001:
    print(f"   SHP-5001 Status: {shp5001['status']}")
    print(f"   ETA: {shp5001['expected_delivery_date']} | Orig ETA: {shp5001.get('original_delivery_date')}")
    print(f"   Tracking: {shp5001['tracking_number']}")
    notes = shp5001.get('mitigation_notes') or ''
    print(f"   Notes prefix: {notes[:80]}")
    if shp5001['status'] != 'In Transit (Expedited Air)':
        errors.append(f"SHP-5001 should be In Transit (Expedited Air), got {shp5001['status']}")
    if '[Simulated Air Cargo]' not in shp5001.get('tracking_number', ''):
        errors.append('SHP-5001 tracking_number should contain [Simulated Air Cargo]')
    if not shp5001.get('original_delivery_date'):
        errors.append('SHP-5001 original_delivery_date should be preserved')
else:
    errors.append('SHP-5001 not found in shipments data')

print()
print('8. Customer orders SLA status post-approval...')
for o in data2['customer_orders']:
    sla = o.get('sla_status', 'On Schedule')
    notes = (o.get('notes') or '')[:60]
    print(f"   {o['order_number']} | sla_status={sla}")
    if o.get('product_id') == 1 and sla == 'On Schedule':
        print(f"     WARNING: Laptop X order {o['order_number']} still shows sla_status=On Schedule after air expedite approval")

print()
print('9. Duplicate approval prevention...')
dec2 = post(f'/api/disruptions/{did}/decision', {'decision': 'Approved: Expedite Air Freight'})
print(f"   already_applied={dec2.get('already_applied')}, success={dec2['success']}")
if dec2.get('already_applied') is not True:
    errors.append('Second approval should return already_applied=True')

print()
print('10. GET disruption after approval (trace refresh)...')
drep2 = get(f'/api/disruptions/{did}')
trace_nodes = (drep2.get('trace_json') or {}).get('nodes', [])
shipment_nodes = [n for n in trace_nodes if n.get('type') == 'shipment']
print(f"   Trace nodes: {len(trace_nodes)}, Shipment nodes: {len(shipment_nodes)}")
if shipment_nodes:
    shp_node = shipment_nodes[0]
    print(f"   Shipment node status: {shp_node.get('details', {}).get('Status', 'N/A')}")
    if shp_node.get('details', {}).get('Status') != 'In Transit (Expedited Air)':
        errors.append('Impact Trace shipment node Status not updated to In Transit (Expedited Air)')

print()
print('11. QA engine...')
qa = post('/api/qa', {'question': 'What is the current stock of Laptop X?'})
print(f"   Answer: {qa['answer'][:120]}")
if 'Laptop' not in qa['answer'] and 'stock' not in qa['answer'].lower():
    errors.append('QA engine answer does not mention Laptop or stock')

print()
print('12. Activity log has mitigation entry...')
acts2 = get('/api/activity')
mitigation_entries = [a for a in acts2['activities'] if 'Mitigation' in a['event_type'] or 'mitigation' in a['description'].lower()]
print(f"   Mitigation log entries: {len(mitigation_entries)}")
if not mitigation_entries:
    errors.append('No mitigation activity log entries found after approval')

print()
print('=' * 50)
if errors:
    print(f'FAILED: {len(errors)} errors found:')
    for e in errors:
        print(f'  - {e}')
    sys.exit(1)
else:
    print('ALL LIVE API CHECKS PASSED')
