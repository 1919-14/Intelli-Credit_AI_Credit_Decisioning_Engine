import os
import json
import pymysql

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', 'sai#1919'),
    'database': os.getenv('DB_NAME', 'intelli_credit'),
}

conn = pymysql.connect(**DB_CONFIG)
cur = conn.cursor(pymysql.cursors.DictCursor)
cur.execute("SELECT layer2_output FROM applications ORDER BY id DESC LIMIT 1")
row = cur.fetchone()
if row and row['layer2_output']:
    print("Fetched L2 Output!")
    data = json.loads(row['layer2_output'])
    # Simulate app.py parsing
    if isinstance(data, str): data = json.loads(data)
    l2_data = data.get('extracted', {}).get('financial_data', {}) or data
    print("Parsed l2_data keys:", list(l2_data.keys()))
    print("Sample values:")
    for k in ["inventory", "closing_stock", "sundry_debtors", "trade_receivables", "advances", "cash_and_bank", "sundry_creditors", "provisions", "bank_borrowings"]:
        print(f"  {k}: {l2_data.get(k, 'MISSING')}")
else:
    print("No L2 data found.")
cur.close()
conn.close()
