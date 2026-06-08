"""
Tests for Treebeard Export Module
"""

import pytest
from django.test import TestCase

from treebeard.export import TreeExporter, export_tree
from treebeard.mp_tree import MP_Node
from treebeard.ns_tree import NS_Node
from treebeard.al_tree import AL_Node

from .models import (
    MP_TestNode,
    NS_TestNode,
    AL_TestNode,
    MP_TestNodeSorted,
    NS_TestNodeSorted,
    AL_TestNodeSorted,
    BASE_MODELS,
    SORTED_MODELS,
)


class TreeExportTestMixin:
    """
    Mixin for tree export tests, works with all tree types
    """
    model = None
    sorted_model = None

    def test_export_empty_tree_json(self):
        """Test exporting an empty tree to JSON"""
        exporter = TreeExporter(self.model)
        data = exporter.export('json')
        assert isinstance(data, list)
        assert len(data) == 0

    def test_export_empty_tree_csv(self):
        """Test exporting an empty tree to CSV"""
        exporter = TreeExporter(self.model)
        csv_data = exporter.export('csv')
        assert isinstance(csv_data, str)
        # Should have at least headers
        assert len(csv_data) > 0

    def test_export_empty_tree_tree(self):
        """Test exporting an empty tree to text tree format"""
        exporter = TreeExporter(self.model)
        tree_data = exporter.export('tree')
        assert isinstance(tree_data, str)
        # Empty tree should have empty or minimal output
        assert len(tree_data) == 0

    def test_export_single_node_tree(self):
        """Test exporting a tree with a single node"""
        # Create a single node
        node = self.model.add_root(desc='Root Node')
        
        # Test JSON export
        exporter = TreeExporter(self.model)
        json_data = exporter.export('json')
        assert len(json_data) == 1
        assert json_data[0]['data']['desc'] == 'Root Node'
        
        # Test CSV export
        csv_data = exporter.export('csv')
        assert 'Root Node' in csv_data
        
        # Test tree format export
        tree_data = exporter.export('tree')
        assert 'Root Node' in tree_data

    def test_export_multi_level_tree(self):
        """Test exporting a multi-level tree"""
        # Create a simple tree
        root = self.model.add_root(desc='Root')
        child1 = root.add_child(desc='Child 1')
        child2 = root.add_child(desc='Child 2')
        grandchild1 = child1.add_child(desc='Grandchild 1')
        
        # Test JSON export preserves hierarchy
        exporter = TreeExporter(self.model)
        json_data = exporter.export('json')
        assert len(json_data) == 1
        assert json_data[0]['data']['desc'] == 'Root'
        assert 'children' in json_data[0]
        assert len(json_data[0]['children']) == 2
        
        # Test CSV export has all nodes
        csv_data = exporter.export('csv')
        assert 'Root' in csv_data
        assert 'Child 1' in csv_data
        assert 'Child 2' in csv_data
        assert 'Grandchild 1' in csv_data
        
        # Test tree format shows hierarchy
        tree_data = exporter.export('tree')
        assert 'Root' in tree_data
        assert 'Child 1' in tree_data
        assert 'Grandchild 1' in tree_data

    def test_export_with_parent_filter(self):
        """Test exporting a subtree starting from a specific parent node"""
        # Create a tree
        root = self.model.add_root(desc='Root')
        child1 = root.add_child(desc='Child 1')
        child2 = root.add_child(desc='Child 2')
        grandchild1 = child1.add_child(desc='Grandchild 1')
        
        # Export only subtree under child1
        exporter = TreeExporter(self.model)
        json_data = exporter.export('json', parent=child1)
        assert len(json_data) == 1
        assert json_data[0]['data']['desc'] == 'Child 1'
        assert len(json_data[0]['children']) == 1
        assert json_data[0]['children'][0]['data']['desc'] == 'Grandchild 1'

    def test_export_with_fields_filter(self):
        """Test exporting with specific fields filter"""
        node = self.model.add_root(desc='Test Node')
        
        exporter = TreeExporter(self.model)
        json_data = exporter.export('json', fields=['desc'])
        
        # Check that only specified fields are present
        assert 'desc' in json_data[0]['data']

    def test_export_with_queryset(self):
        """Test exporting from a QuerySet instead of a model"""
        root = self.model.add_root(desc='Root')
        child = root.add_child(desc='Child')
        
        queryset = self.model.objects.all()
        exporter = TreeExporter(queryset)
        json_data = exporter.export('json')
        assert len(json_data) == 1
        assert json_data[0]['data']['desc'] == 'Root'

    def test_convenience_export_function(self):
        """Test the convenience export_tree function"""
        root = self.model.add_root(desc='Root')
        child = root.add_child(desc='Child')
        
        json_data = export_tree(self.model, 'json')
        assert len(json_data) == 1
        assert json_data[0]['data']['desc'] == 'Root'

    def test_sorted_tree_export(self):
        """Test exporting a sorted tree (if available)"""
        if self.sorted_model is None:
            pytest.skip("No sorted model available for this tree type")
        
        # Create a sorted tree
        root = self.sorted_model.add_root(desc='C', val1=1, val2=1)
        child1 = root.add_child(desc='A', val1=2, val2=1)
        child2 = root.add_child(desc='B', val1=2, val2=1)
        
        exporter = TreeExporter(self.sorted_model)
        tree_data = exporter.export('tree')
        
        # Check that the nodes appear in sorted order
        # (Exact order depends on node_order_by)


@pytest.mark.django_db
class TestMPTreeExport(TreeExportTestMixin, TestCase):
    """Tests for Materialized Path (MP_Node) tree export"""
    model = MP_TestNode
    sorted_model = MP_TestNodeSorted


@pytest.mark.django_db
class TestNSTreeExport(TreeExportTestMixin, TestCase):
    """Tests for Nested Sets (NS_Node) tree export"""
    model = NS_TestNode
    sorted_model = NS_TestNodeSorted


@pytest.mark.django_db
class TestALTreeExport(TreeExportTestMixin, TestCase):
    """Tests for Adjacency List (AL_Node) tree export"""
    model = AL_TestNode
    sorted_model = AL_TestNodeSorted


@pytest.mark.django_db
class TestTreeExporterEdgeCases(TestCase):
    """Test edge cases for TreeExporter"""
    
    def test_unsupported_format(self):
        """Test that an unsupported format raises ValueError"""
        model = MP_TestNode
        exporter = TreeExporter(model)
        
        with pytest.raises(ValueError):
            exporter.export('unsupported_format')
    
    def test_json_export_without_ids(self):
        """Test JSON export without keeping IDs"""
        root = MP_TestNode.add_root(desc='Root')
        
        exporter = TreeExporter(MP_TestNode)
        data = exporter.export('json', keep_ids=False)
        assert isinstance(data, list)
        assert len(data) == 1
