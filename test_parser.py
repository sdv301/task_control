import sys
sys.path.insert(0, '/app')
from pdf_parser.pdf_engine import parse_pdf

result = parse_pdf(file_path='/tmp/test.pdf', filename='test.pdf')
if result:
    tasks = result.get('tasks', [])
    print('Total tasks:', len(tasks))
    # Count tasks by item_number prefix
    from collections import Counter
    prefix_counter = Counter()
    for t in tasks:
        item = t.get('item_number', '-')
        top_level = item.split('.')[0]
        prefix_counter[top_level] += 1
    print('\nTasks per top-level item:')
    for k in sorted(prefix_counter.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        print(f'  P.{k}: {prefix_counter[k]} tasks')
    
    # Check which items under 10 are districts
    print('\nAll item 10.x tasks:')
    for t in tasks:
        item = t.get('item_number', '')
        if item.startswith('10'):
            print(f'  {item}: {t["executor"][:40]}')
else:
    print('None')
