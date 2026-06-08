import sys
sys.path.append('/app')
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()

from tests.models import MP_TestNode

django.core.management.call_command('migrate', verbosity=0, interactive=False)

root = MP_TestNode.add_root()
child = root.add_child()
print(MP_TestNode.dump_bulk())
from django.core.serializers import serialize
import json
print(json.dumps(serialize("python", [root, child]), indent=2))
