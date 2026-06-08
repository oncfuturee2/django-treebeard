import sys
sys.path.append('/app')
import django
from django.conf import settings
settings.configure(
    INSTALLED_APPS=[
        'treebeard',
        'tests',
    ],
    DATABASES={
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
)
django.setup()
from treebeard.models import Node
print(Node.get_annotated_list.__doc__)
