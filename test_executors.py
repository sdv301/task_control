import sys
sys.path.append('/app')
import json
from pdf_parser.pdf_engine import parse_pdf
tasks = parse_pdf('/tmp/test.pdf').get('tasks', [])
for t in tasks:
    i = t.get('item_number')
    if str(i) in ['2', '3', '4', '5', '5.1', '5.2', '5.3', '6', '7', '8']:
        print(f"Item: '{i}' - Exec: '{t.get('executor', '')}'")
