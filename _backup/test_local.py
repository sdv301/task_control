import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'parser'))

from pdf_engine import RE_ITEM_HEADER, _parse_executor, _parse_deadline

with open('data/extracted_text.txt', 'r', encoding='utf-8') as f:
    text = f.read()

segments = RE_ITEM_HEADER.split(text)
count = 0
for i in range(1, len(segments) - 1, 2):
    item_num = segments[i].strip().rstrip('.')
    content = segments[i + 1].strip()
    
    if '.' not in item_num and item_num.isdigit() and int(item_num) > 30:
        continue
        
    if len(content) < 5:
        continue
        
    executor = _parse_executor(content)
    deadline = _parse_deadline(content)
    first_line = content.split('\n')[0].strip()[:50]
    count += 1
    dlstr = str(deadline)[:10] if deadline else '-'
    print(f"P.{item_num:8s} | {executor:25s} | {dlstr:12s} | {first_line}")

print(f"\nTotal: {count} items")
