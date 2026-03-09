import mysql.connector
import json

conn = mysql.connector.connect(host='localhost', user='root', password='sai#1919', database='intelli_credit')
cur = conn.cursor(dictionary=True)
cur.execute('SELECT layer2_output FROM applications ORDER BY id DESC LIMIT 1')
r = cur.fetchone()
if r and r['layer2_output']:
    data = json.loads(r['layer2_output'])
    if isinstance(data, str):
        data = json.loads(data)
    print("TOP INFO:", data.get('extracted', {}).keys() if 'extracted' in data else 'NO EXTRACTED KEY')
    l2 = data.get('extracted', {}).get('financial_data', {}) or data
    print("L2 ITEMS:", list(l2.items())[:5])
    
    # Check what inventory is
    inventory = l2.get("inventory", 0) or l2.get("closing_stock", 0) or 0
    print("Inventory value read:", inventory)
    print("Type of inventory:", type(inventory))
else:
    print("NO DATA")
