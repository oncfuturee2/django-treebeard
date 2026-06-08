import pytest
import json
import csv
import io
from django.core.management import call_command
from tests.models import MP_TestNode, NS_TestNode, AL_TestNode, MP_TestNodeSorted
from treebeard.export import export_tree

@pytest.fixture(autouse=True)
def setup_db(db):
    pass

@pytest.fixture
def mp_tree():
    yield MP_TestNode
    MP_TestNode.objects.all().delete()

@pytest.fixture
def ns_tree():
    yield NS_TestNode
    NS_TestNode.objects.all().delete()

@pytest.fixture
def al_tree():
    yield AL_TestNode
    AL_TestNode.objects.all().delete()

@pytest.fixture
def mp_sorted_tree():
    yield MP_TestNodeSorted
    MP_TestNodeSorted.objects.all().delete()

def build_sample_tree(model_class):
    root = model_class.add_root(desc='root')
    child1 = root.add_child(desc='child1')
    child2 = root.add_child(desc='child2')
    child1.add_child(desc='grandchild1')
    child1.add_child(desc='grandchild2')
    return root

def test_export_empty_tree(mp_tree):
    # JSON
    assert export_tree(mp_tree, format='json') == '[]'
    
    # CSV
    csv_out = export_tree(mp_tree, format='csv')
    assert 'id' in csv_out
    assert len(csv_out.strip().split('\n')) == 1  # Only header
    
    # Text
    assert export_tree(mp_tree, format='text') == ''

def test_export_single_node(mp_tree):
    root = mp_tree.add_root(desc='root')
    
    # JSON
    json_out = json.loads(export_tree(mp_tree, format='json'))
    assert len(json_out) == 1
    assert json_out[0]['data']['desc'] == 'root'
    
    # Text
    text_out = export_tree(mp_tree, format='text')
    assert 'root' in text_out

def test_export_multi_level_tree_mp(mp_tree):
    root = build_sample_tree(mp_tree)
    
    # JSON
    json_out = json.loads(export_tree(mp_tree, format='json'))
    assert len(json_out) == 1
    root_node = json_out[0]
    assert len(root_node['children']) == 2
    assert len(root_node['children'][0]['children']) == 2
    
    # CSV
    csv_out = export_tree(mp_tree, format='csv')
    reader = csv.DictReader(io.StringIO(csv_out))
    rows = list(reader)
    assert len(rows) == 5
    assert all('path' in row for row in rows)
    assert all('depth' in row for row in rows)
    
    # Text
    text_out = export_tree(mp_tree, format='text')
    assert '├──' in text_out
    assert '└──' in text_out

def test_export_multi_level_tree_ns(ns_tree):
    root = build_sample_tree(ns_tree)
    
    json_out = json.loads(export_tree(ns_tree, format='json'))
    assert len(json_out) == 1
    root_node = json_out[0]
    assert len(root_node['children']) == 2
    
    # Test exporting from a specific parent
    child1 = ns_tree.objects.get(desc='child1')
    json_out_parent = json.loads(export_tree(ns_tree, format='json', parent=child1))
    assert len(json_out_parent) == 1
    assert len(json_out_parent[0]['children']) == 2
    
def test_export_multi_level_tree_al(al_tree):
    root = build_sample_tree(al_tree)
    
    # AL_Node uses parent foreign key
    csv_out = export_tree(al_tree, format='csv')
    reader = csv.DictReader(io.StringIO(csv_out))
    rows = list(reader)
    assert len(rows) == 5
    assert all('parent' in row for row in rows)
    
    # Test exporting from instance
    json_out = json.loads(export_tree(root, format='json'))
    assert len(json_out) == 1
    assert len(json_out[0]['children']) == 2

def test_export_fields_filter(mp_tree):
    build_sample_tree(mp_tree)
    
    json_out = json.loads(export_tree(mp_tree, format='json', fields=['desc']))
    root_node = json_out[0]
    assert 'desc' in root_node['data']
    assert 'path' not in root_node['data']
    
    csv_out = export_tree(mp_tree, format='csv', fields=['id', 'desc'])
    reader = csv.DictReader(io.StringIO(csv_out))
    assert reader.fieldnames == ['id', 'desc']

def test_export_queryset(mp_tree):
    build_sample_tree(mp_tree)
    qs = mp_tree.objects.all()
    
    json_out = json.loads(export_tree(qs, format='json'))
    assert len(json_out) == 1
    
    text_out = export_tree(qs, format='text')
    assert '└──' in text_out

def test_export_sorted_tree(mp_sorted_tree):
    root = mp_sorted_tree.add_root(val1=1, val2=1, desc='root')
    child2 = root.add_child(val1=2, val2=2, desc='child2')
    child1 = root.add_child(val1=1, val2=1, desc='child1') # Will be sorted before child2
    
    json_out = json.loads(export_tree(mp_sorted_tree, format='json'))
    assert json_out[0]['children'][0]['data']['desc'] == 'child1'
    assert json_out[0]['children'][1]['data']['desc'] == 'child2'
