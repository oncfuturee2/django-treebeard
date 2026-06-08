"""
Treebeard Tree Export Module
Supports exporting tree structures to JSON, CSV, and text tree diagram formats
"""

import csv
import io
import json
from typing import Any, List, Optional, Union

from django.db.models import Model, QuerySet


class TreeExporter:
    """
    Unified tree exporter for Treebeard tree models (MP_Node, NS_Node, AL_Node)
    """

    JSON_FORMAT = "json"
    CSV_FORMAT = "csv"
    TREE_FORMAT = "tree"

    def __init__(self, tree_model_or_queryset: Union[Model, QuerySet, type]):
        """
        Initialize the exporter with a tree model class, instance, or queryset
        
        :param tree_model_or_queryset: Tree model class, instance, or queryset
        """
        if hasattr(tree_model_or_queryset, 'model'):
            # It's a QuerySet
            self.model = tree_model_or_queryset.model
            self.queryset = tree_model_or_queryset
        elif isinstance(tree_model_or_queryset, type):
            # It's a model class
            self.model = tree_model_or_queryset
            self.queryset = self.model.objects.all()
        else:
            # It's a model instance
            self.model = tree_model_or_queryset.__class__
            self.queryset = self.model.objects.all()

    def export(
        self,
        format: str,
        parent: Optional[Model] = None,
        fields: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        """
        Export the tree to the specified format
        
        :param format: Output format (json, csv, tree)
        :param parent: Optional parent node to start exporting from
        :param fields: Optional list of fields to include in the output
        :return: Exported data (dict for json, str for csv and tree)
        """
        format = format.lower()
        if format == self.JSON_FORMAT:
            return self._export_json(parent=parent, fields=fields, **kwargs)
        elif format == self.CSV_FORMAT:
            return self._export_csv(parent=parent, fields=fields, **kwargs)
        elif format == self.TREE_FORMAT:
            return self._export_tree(parent=parent, fields=fields, **kwargs)
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def _export_json(
        self,
        parent: Optional[Model] = None,
        fields: Optional[List[str]] = None,
        **kwargs
    ) -> Any:
        """
        Export to JSON format, preserving tree hierarchy
        """
        keep_ids = kwargs.get('keep_ids', True)
        bulk_data = self.model.dump_bulk(parent=parent, keep_ids=keep_ids)
        
        if fields:
            bulk_data = self._filter_fields_in_bulk(bulk_data, fields)
        
        return bulk_data

    def _filter_fields_in_bulk(self, data: List[dict], fields: List[str]) -> List[dict]:
        """
        Recursively filter fields in bulk data
        """
        filtered = []
        for item in data:
            filtered_item = {}
            # Keep pk field if present
            for key in item:
                if key != 'data' and key != 'children':
                    filtered_item[key] = item[key]
            # Filter data fields
            if 'data' in item:
                filtered_item['data'] = {k: v for k, v in item['data'].items() if k in fields}
            # Recurse on children
            if 'children' in item:
                filtered_item['children'] = self._filter_fields_in_bulk(item['children'], fields)
            filtered.append(filtered_item)
        return filtered

    def _export_csv(
        self,
        parent: Optional[Model] = None,
        fields: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Export to CSV format
        """
        output = io.StringIO()
        tree = self.model.get_tree(parent=parent)
        
        # Collect all possible field names
        all_fields = []
        for node in tree:
            node_fields = self._get_node_fields(node)
            for f in node_fields:
                if f not in all_fields:
                    all_fields.append(f)
        
        # Determine which fields to include
        csv_fields = []
        # Add core fields
        core_fields = self._get_core_field_names()
        for cf in core_fields:
            if cf in all_fields:
                csv_fields.append(cf)
        # Add user-specified fields or remaining fields
        if fields:
            for f in fields:
                if f not in csv_fields:
                    csv_fields.append(f)
        else:
            for f in all_fields:
                if f not in csv_fields:
                    csv_fields.append(f)
        
        # Write CSV
        writer = csv.DictWriter(output, fieldnames=csv_fields)
        writer.writeheader()
        
        for node in tree:
            row = self._get_node_row(node, csv_fields)
            writer.writerow(row)
        
        return output.getvalue()

    def _get_core_field_names(self) -> List[str]:
        """
        Get core field names based on tree type
        """
        from treebeard.mp_tree import MP_Node
        from treebeard.ns_tree import NS_Node
        from treebeard.al_tree import AL_Node
        
        if issubclass(self.model, MP_Node):
            return ['path', 'depth', 'numchild']
        elif issubclass(self.model, NS_Node):
            return ['lft', 'rgt', 'tree_id', 'depth']
        elif issubclass(self.model, AL_Node):
            return ['parent', 'sib_order']
        return []

    def _get_node_fields(self, node: Model) -> List[str]:
        """
        Get all field names from a node
        """
        return [f.name for f in node._meta.fields]

    def _get_node_row(self, node: Model, fields: List[str]) -> dict:
        """
        Get a CSV row from a node
        """
        row = {}
        for field_name in fields:
            value = getattr(node, field_name, None)
            # Handle None values
            if value is None:
                row[field_name] = ''
            # Handle foreign keys
            elif hasattr(value, 'pk'):
                row[field_name] = str(value.pk)
            else:
                row[field_name] = str(value)
        return row

    def _export_tree(
        self,
        parent: Optional[Model] = None,
        fields: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """
        Export to text tree diagram format
        """
        tree = self.model.get_tree(parent=parent)
        
        # Build a list of nodes with their depth and children
        node_map = {}
        root_nodes = []
        
        # First pass: build node map
        for node in tree:
            node_map[node.pk] = {
                'node': node,
                'children': [],
                'depth': self._get_node_depth(node)
            }
        
        # Second pass: build hierarchy
        for node_pk, node_data in node_map.items():
            node = node_data['node']
            parent_node = self._get_node_parent(node)
            if parent_node is None or (parent and parent_node.pk == parent.pk):
                root_nodes.append(node_data)
            elif parent_node.pk in node_map:
                node_map[parent_node.pk]['children'].append(node_data)
        
        # Render the tree
        output = []
        for root in root_nodes:
            self._render_tree_node(root, output, fields, '', True)
        
        return '\n'.join(output)

    def _render_tree_node(
        self,
        node_data: dict,
        output: List[str],
        fields: Optional[List[str]],
        prefix: str,
        is_last: bool
    ):
        """
        Recursively render a tree node
        """
        node = node_data['node']
        node_label = self._format_node_label(node, fields)
        
        if prefix:
            connector = '└── ' if is_last else '├── '
            output.append(f"{prefix}{connector}{node_label}")
        else:
            output.append(node_label)
        
        # Prepare prefix for children
        children = node_data['children']
        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            child_prefix = prefix
            if prefix:
                child_prefix += '    ' if is_last else '│   '
            self._render_tree_node(child, output, fields, child_prefix, is_last_child)

    def _format_node_label(self, node: Model, fields: Optional[List[str]]) -> str:
        """
        Format a node label
        """
        if fields:
            # Show only specified fields
            values = [f"{f}={getattr(node, f, '')}" for f in fields]
            return f"{node._meta.object_name}[{', '.join(values)}]"
        else:
            # Try to use a reasonable string representation
            return str(node)

    def _get_node_depth(self, node: Model) -> int:
        """
        Get depth of a node
        """
        if hasattr(node, 'depth'):
            return node.depth
        return node.get_depth()

    def _get_node_parent(self, node: Model) -> Optional[Model]:
        """
        Get parent of a node
        """
        if hasattr(node, 'parent'):
            return node.parent
        try:
            return node.get_parent()
        except Exception:
            return None


def export_tree(
    tree_model_or_queryset: Union[Model, QuerySet],
    format: str,
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
    **kwargs
) -> Any:
    """
    Convenience function to export a tree structure
    
    :param tree_model_or_queryset: Tree model instance or queryset
    :param format: Output format (json, csv, tree)
    :param parent: Optional parent node to start exporting from
    :param fields: Optional list of fields to include in the output
    :return: Exported data
    """
    exporter = TreeExporter(tree_model_or_queryset)
    return exporter.export(format, parent=parent, fields=fields, **kwargs)
