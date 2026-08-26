import json
import os
import sys
# Ensure repo root is on sys.path so ec_parser can be imported when running from tools/labeler
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
	sys.path.insert(0, ROOT)

from ec_parser import parse_ec_text

s = "The project shall maintain a 100 metre buffer from the perennial river and no permanent structures shall be within this distance."
out = parse_ec_text(s)
print(json.dumps(out, indent=2))
