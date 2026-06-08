import csv
import io
import json
from typing import Any, Dict, List, Optional, Type, Union

from django.db import models
from django.db.models import Model, QuerySet

from treebeard.al_tree import AL_Node
from treebeard.mp_tree import MP_Node
from treebeard.ns_tree import NS_Node


class ExportFormat:
    JSON = "json"
    CSV = "csv"
    TEXT = "text"


def export_tree(
    source: Union[Type[Model], QuerySet, Model],
    format: str = ExportFormat.JSON,
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
    include_primary_key: bool = True,
) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
    if isinstance(source, Model):
        model = source.__class__
        nodes = model.get_tree(parent=source)
        if isinstance(nodes, QuerySet):
            nodes = list(nodes)
        elif not isinstance(nodes, (list, tuple)):
            nodes = list(nodes)
    elif isinstance(source, QuerySet):
        model = source.model
        nodes = get_flattened_nodes_from_queryset(source, parent)
    else:
        model = source
        nodes = get_flattened_nodes(model, parent)

    if format == ExportFormat.JSON:
        return export_json(model, parent, fields, include_primary_key)
    elif format == ExportFormat.CSV:
        return export_csv(nodes, fields)
    elif format == ExportFormat.TEXT:
        return export_text(nodes, fields)
    else:
        raise ValueError(f"Unsupported export format: {format}. Use one of: json, csv, text")


def get_flattened_nodes(model: Type[Model], parent: Optional[Model]) -> List[Model]:
    result = model.get_tree(parent)
    if isinstance(result, (list, tuple)):
        return list(result)
    return list(result)


def get_flattened_nodes_from_queryset(queryset: QuerySet, parent: Optional[Model]) -> List[Model]:
    model = queryset.model

    if not issubclass(model, AL_Node):
        if parent is not None:
            return model.get_tree(parent)
        return list(queryset.order_by()) or list(queryset)

    all_nodes = list(queryset)
    if parent is not None:
        root_pks = {parent.pk}
        filtered = [n for n in all_nodes if n.parent_id in root_pks or n.pk == parent.pk]
    else:
        filtered = [n for n in all_nodes if n.parent_id is None]

    nodes = []
    visited = set()

    def collect_dfs(node):
        if node.pk in visited:
            return
        visited.add(node.pk)
        nodes.append(node)
        for child in [n for n in all_nodes if n.parent_id == node.pk]:
            collect_dfs(child)

    for root in filtered:
        collect_dfs(root)

    return nodes


def export_json(
    model: Type[Model],
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
    include_primary_key: bool = True,
) -> Dict[str, Any]:
    data = model.dump_bulk(parent=parent, keep_ids=include_primary_key)

    if fields is not None:
        data = filter_fields_in_dump(data, fields)

    return data


def filter_fields_in_dump(data: List[Dict], fields: List[str]) -> List[Dict]:
    result = []
    for item in data:
        filtered_item = {}
        if "id" in item:
            filtered_item["id"] = item["id"]
        if "pk" in item:
            filtered_item["pk"] = item["pk"]
        if "data" in item:
            filtered_item["data"] = {
                key: value for key, value in item["data"].items()
                if key in fields
            }
        result.append(filtered_item)
        if "children" in filtered_item and "children" in item:
            filtered_item["children"] = filter_fields_in_dump(item["children"], fields)
        elif "children" in item:
            filtered_item["children"] = filter_fields_in_dump(item["children"], fields)
    return result


def export_csv(nodes: List[Model], fields: Optional[List[str]] = None) -> str:
    if not nodes:
        return ""

    sample_node = nodes[0]
    available_fields = get_node_fields(sample_node)

    default_fields = ["pk", "depth", "numchild"]
    if hasattr(sample_node, "path"):
        default_fields.insert(1, "path")
    if hasattr(sample_node, "lft") and hasattr(sample_node, "rgt") and hasattr(sample_node, "tree_id"):
        default_fields.extend(["lft", "rgt", "tree_id"])
    if hasattr(sample_node, "parent_id"):
        default_fields.append("parent_id")

    output_fields = list(default_fields)

    if fields:
        for field in fields:
            if field not in output_fields:
                output_fields.append(field)
    else:
        for field in sorted(available_fields):
            if field not in output_fields:
                output_fields.append(field)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=output_fields)
    writer.writeheader()

    for node in nodes:
        row = {}
        for field_name in output_fields:
            row[field_name] = get_node_field_value(node, field_name)
        writer.writerow(row)

    return output.getvalue()


def export_text(nodes: List[Model], fields: Optional[List[str]] = None) -> str:
    if not nodes:
        return ""

    tree_data = build_tree_structure(nodes)

    lines = []

    def render_children(children: List[Dict], prefix: str = "") -> None:
        for i, child_info in enumerate(children):
            is_last = i == len(children) - 1

            label = get_node_label(child_info["node"], fields)

            if is_last:
                connector = "└── "
                new_prefix = prefix + "    "
            else:
                connector = "├── "
                new_prefix = prefix + "│   "

            lines.append(prefix + connector + label)
            render_children(child_info["children"], new_prefix)

    if len(tree_data["children"]) == 0:
        return ""
    elif len(tree_data["children"]) == 1:
        root_info = tree_data["children"][0]
        root_label = get_node_label(root_info["node"], fields)
        lines.append(root_label)
        render_children(root_info["children"], "")
    else:
        for i, root_info in enumerate(tree_data["children"]):
            is_last = i == len(tree_data["children"]) - 1
            root_label = get_node_label(root_info["node"], fields)

            if is_last:
                connector = "└── "
                new_prefix = "    "
            else:
                connector = "├── "
                new_prefix = "│   "

            lines.append(connector + root_label)
            render_children(root_info["children"], new_prefix)

    return "\n".join(lines)


def build_tree_structure(nodes: List[Model]) -> Dict:
    root = {"children": []}
    parent_map: Dict[Any, List] = {}

    for node in nodes:
        parent_map[node.pk] = []

    for node in nodes:
        parent_pk = get_parent_pk(node)
        node_info = {"node": node, "children": parent_map[node.pk]}
        if parent_pk is None or parent_pk not in parent_map:
            root["children"].append(node_info)
        else:
            parent_map[parent_pk].append(node_info)

    return root


def get_parent_pk(node: Model) -> Optional[Any]:
    if isinstance(node, MP_Node):
        if node.is_root():
            return None
        parent = node.get_parent()
        return parent.pk if parent else None
    elif isinstance(node, NS_Node):
        if node.is_root():
            return None
        parent = node.get_parent()
        return parent.pk if parent else None
    elif isinstance(node, AL_Node):
        return node.parent_id
    return None


def get_node_fields(node: Model) -> List[str]:
    return [field.name for field in node._meta.fields]


def get_node_field_value(node: Model, field: str) -> Any:
    if field == "pk":
        return node.pk
    if field == "depth":
        return node.get_depth()
    if hasattr(node, field):
        return getattr(node, field)
    return None


def get_node_label(node: Model, fields: Optional[List[str]] = None) -> str:
    if hasattr(node, "__str__"):
        default_str = str(node)
    else:
        default_str = f"Node {node.pk}"

    if fields is None:
        return default_str

    if len(fields) == 1:
        value = get_node_field_value(node, fields[0])
        return str(value)

    parts = []
    for field in fields:
        value = get_node_field_value(node, field)
        parts.append(f"{field}={value}")
    return ", ".join(parts)


def export_to_json(
    source: Union[Type[Model], QuerySet],
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
    include_primary_key: bool = True,
) -> str:
    data = export_tree(source, ExportFormat.JSON, parent, fields, include_primary_key)
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_to_csv(
    source: Union[Type[Model], QuerySet],
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
) -> str:
    return export_tree(source, ExportFormat.CSV, parent, fields)


def export_to_text(
    source: Union[Type[Model], QuerySet],
    parent: Optional[Model] = None,
    fields: Optional[List[str]] = None,
) -> str:
    return export_tree(source, ExportFormat.TEXT, parent, fields)