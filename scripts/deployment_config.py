"""Read private deployment settings without evaluating or printing credentials."""
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
project = os.getenv('GOOGLE_CLOUD_PROJECT', '')
zone = os.getenv('DEMO_VM_ZONE', 'us-east4-c')
instance = os.getenv('DEMO_VM_INSTANCE', '')
port = os.getenv('DEMO_APP_PORT', '8084')
checks = (
    ('GOOGLE_CLOUD_PROJECT', project, r'[a-z][a-z0-9-]{4,61}[a-z0-9]'),
    ('DEMO_VM_ZONE', zone, r'us-east4-[abc]'),
    ('DEMO_VM_INSTANCE', instance, r'[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?'),
    ('DEMO_APP_PORT', port, r'[0-9]{1,5}'),
)
for name, value, pattern in checks:
    if not re.fullmatch(pattern, value) or (name == 'DEMO_APP_PORT' and not 1 <= int(value) <= 65535):
        print(f'Set a valid {name} in the private .env file. Deployment must stay in us-east4.', file=sys.stderr)
        raise SystemExit(2)
print(project, zone, instance, port)
