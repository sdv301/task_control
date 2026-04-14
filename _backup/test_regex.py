content = """Органам местного самоуправления республики
саха (якутия)"""

content_clean = content.replace('\n', ' ').lower()
print(content_clean)
if 'органам местного самоуправления' in content_clean:
    print("MATCH 1: True")
else:
    print("MATCH 1: False")

import re
print("MATCH 2:", bool(re.search(r'органам местного самоуправления', content, re.IGNORECASE | re.DOTALL)))

