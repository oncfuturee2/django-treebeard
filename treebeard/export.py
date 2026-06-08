import json
import csv
import io
from django.db.models import QuerySet
from django.core.serializers import serialize
from treebeard.models import Node

def _build_tree_structure(qs, model_class, fields=None):
    ret = []
    stack = []
    pk_field = model_class._meta.pk.attname
    
    for node in qs:
        depth = node.get_depth()
        pyobj = serialize("python", [node])[0]
        node_fields = pyobj["fields"]
        
        if fields is not None:
            node_fields = {k: v for k, v in node_fields.items() if k in fields}
            
        newobj = {"data": node_fields, pk_field: pyobj["pk"]}
        newobj["_str"] = str(node)
        newobj["children"] = []
        
        if len(stack) == 0:
            ret.append(newobj)
            stack.append((depth, newobj))
        else:
            while stack and stack[-1][0] >= depth:
                stack.pop()
            
            if not stack:
                ret.append(newobj)
            else:
                stack[-1][1]["children"].append(newobj)
                
            stack.append((depth, newobj))
            
    return ret

def _export_json(qs, model_class, fields):
    tree_struct = _build_tree_structure(qs, model_class, fields)
    
    def _clean(nodes):
        for node in nodes:
            node.pop("_str", None)
            _clean(node.get("children", []))
            
    _clean(tree_struct)
    return json.dumps(tree_struct, indent=2, ensure_ascii=False)

def _export_csv(qs, model_class, fields):
    output = io.StringIO()
    pk_field = model_class._meta.pk.attname
    
    if fields is not None:
        header = fields
    else:
        opts = model_class._meta
        header = [pk_field] + [f.name for f in opts.fields if f.name != opts.pk.name]
        
    writer = csv.DictWriter(output, fieldnames=header)
    writer.writeheader()
    
    for node in qs:
        pyobj = serialize("python", [node])[0]
        row = pyobj["fields"]
        row[pk_field] = pyobj["pk"]
        
        if fields is not None:
            row = {k: v for k, v in row.items() if k in fields}
            
        filtered_row = {k: v for k, v in row.items() if k in header}
        writer.writerow(filtered_row)
        
    return output.getvalue()

def _export_text(qs, model_class, fields):
    tree_struct = _build_tree_structure(qs, model_class, fields)
    lines = []
    
    def _draw_tree(node_dict, is_last_list):
        prefix_parts = []
        if is_last_list:
            for is_last in is_last_list[:-1]:
                prefix_parts.append("    " if is_last else "│   ")
            prefix_parts.append("└── " if is_last_list[-1] else "├── ")
            
        prefix = "".join(prefix_parts)
        node_str = node_dict.get("_str", "")
        lines.append(prefix + node_str)
        
        children = node_dict.get("children", [])
        for i, child_dict in enumerate(children):
            is_last = (i == len(children) - 1)
            _draw_tree(child_dict, is_last_list + [is_last])
            
    for root_node in tree_struct:
        _draw_tree(root_node, [])
        
    return "\n".join(lines)

def export_tree(tree_model_or_qs, format='json', parent=None, fields=None):
    """
    Export treebeard tree into json, csv, or text format.
    
    :param tree_model_or_qs: A treebeard Node subclass, Node instance, or QuerySet.
    :param format: 'json', 'csv', or 'text'.
    :param parent: Optional parent node to filter the tree.
    :param fields: Optional list of fields to include.
    """
    if isinstance(tree_model_or_qs, QuerySet):
        qs = tree_model_or_qs
        model_class = qs.model
    elif isinstance(tree_model_or_qs, Node):
        model_class = tree_model_or_qs.__class__
        if parent is None:
            parent = tree_model_or_qs
        qs = model_class.get_tree(parent)
    elif issubclass(tree_model_or_qs, Node):
        model_class = tree_model_or_qs
        qs = model_class.get_tree(parent)
    else:
        raise ValueError("tree_model_or_qs must be a treebeard Node subclass, instance, or QuerySet")
        
    if not isinstance(qs, (QuerySet, list, tuple)):
        qs = list(qs)
        
    if format == 'json':
        return _export_json(qs, model_class, fields)
    elif format == 'csv':
        return _export_csv(qs, model_class, fields)
    elif format == 'text':
        return _export_text(qs, model_class, fields)
    else:
        raise ValueError(f"Unsupported format: {format}")
