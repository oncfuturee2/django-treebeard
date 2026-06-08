import csv
import json
from io import StringIO
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import QuerySet

from treebeard.al_tree import AL_Node
from treebeard.models import Node
from treebeard.mp_tree import MP_Node
from treebeard.ns_tree import NS_Node

CORE_FIELDS = ("id", "parent_id", "path", "depth", "numchild")


def export_tree(source: Node | QuerySet, export_format: str, parent: Node | None = None, fields: list[str] | None = None):
    export_format = export_format.lower()
    model, nodes = _resolve_source(source, parent)
    selected_fields = _resolve_fields(model, fields)
    tree, rows = _serialize_nodes(model, nodes, selected_fields)

    if export_format == "json":
        return json.dumps(tree, cls=DjangoJSONEncoder)
    if export_format == "csv":
        return _render_csv(rows, selected_fields)
    if export_format == "text":
        return _render_text(tree, fields)
    raise ValueError(f"Unsupported export format: {export_format}")


def _resolve_source(source: Node | QuerySet, parent: Node | None) -> tuple[type[Node], list[Node]]:
    if isinstance(source, QuerySet):
        model = source.model.tree_model()
        candidate_ids = set(source.values_list("pk", flat=True))
        if not candidate_ids:
            return model, []
        nodes = [node for node in model.get_tree(parent) if node.pk in candidate_ids]
        return model, nodes
    if isinstance(source, Node):
        model = source.__class__.tree_model()
        return model, list(model.get_tree(parent or source))
    raise TypeError("source must be a treebeard node instance or queryset")


def _resolve_fields(model: type[Node], fields: list[str] | None) -> list[str]:
    default_fields = _default_model_fields(model)
    if fields is None:
        return default_fields
    invalid_fields = [field for field in fields if field not in default_fields]
    if invalid_fields:
        raise ValueError(f"Unsupported export fields: {', '.join(invalid_fields)}")
    return fields


def _default_model_fields(model: type[Node]) -> list[str]:
    internal_fields = _internal_field_names(model)
    return [
        field.name
        for field in model._meta.concrete_fields
        if not field.primary_key and field.name not in internal_fields and field.attname not in internal_fields
    ]


def _internal_field_names(model: type[Node]) -> set[str]:
    field_names = set()
    if issubclass(model, MP_Node):
        field_names.update({"path", "depth", "numchild"})
    if issubclass(model, NS_Node):
        field_names.update({"lft", "rgt", "tree_id", "depth"})
    if issubclass(model, AL_Node):
        field_names.update({"parent", "parent_id", "sib_order"})
    return field_names


def _serialize_nodes(
    model: type[Node], nodes: list[Node], selected_fields: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tree = []
    rows = []
    export_by_pk = {}

    for node in nodes:
        parent_id = _parent_id(node)
        parent_export = export_by_pk.get(parent_id)
        data = {field: node._meta.get_field(field).value_from_object(node) for field in selected_fields}
        serialized = {
            "id": node.pk,
            "parent_id": parent_id,
            "path": _path_value(model, node, parent_export),
            "depth": node.get_depth(),
            "numchild": node.get_children_count(),
            "data": data,
            "label": str(node),
            "children": [],
        }
        export_by_pk[node.pk] = serialized
        rows.append(serialized)
        if parent_export is None:
            tree.append(serialized)
        else:
            parent_export["children"].append(serialized)

    return tree, rows


def _parent_id(node: Node):
    if node.is_root():
        return None
    parent = node.get_parent()
    return parent.pk if parent is not None else None


def _path_value(model: type[Node], node: Node, parent_export: dict[str, Any] | None) -> str:
    if issubclass(model, MP_Node):
        return node.path
    if parent_export is not None:
        return f"{parent_export['path']}/{node.pk}"
    return "/".join(str(ancestor.pk) for ancestor in [*node.get_ancestors(), node])


def _render_csv(rows: list[dict[str, Any]], selected_fields: list[str]) -> str:
    output = StringIO()
    headers = [*CORE_FIELDS, *selected_fields]
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        csv_row = {field: row[field] for field in CORE_FIELDS}
        csv_row.update(row["data"])
        writer.writerow(csv_row)
    return output.getvalue()


def _render_text(tree: list[dict[str, Any]], label_fields: list[str] | None) -> str:
    lines = []
    for node in tree:
        lines.append(_node_label(node, label_fields))
        lines.extend(_render_text_children(node["children"], label_fields, ""))
    return "\n".join(lines)


def _render_text_children(children: list[dict[str, Any]], label_fields: list[str] | None, prefix: str) -> list[str]:
    lines = []
    for index, child in enumerate(children):
        is_last = index == len(children) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{_node_label(child, label_fields)}")
        child_prefix = f"{prefix}{'    ' if is_last else '│   '}"
        lines.extend(_render_text_children(child["children"], label_fields, child_prefix))
    return lines


def _node_label(node: dict[str, Any], label_fields: list[str] | None) -> str:
    if label_fields is None:
        return node["label"]
    if not label_fields:
        return str(node["id"])
    if len(label_fields) == 1:
        return str(node["data"][label_fields[0]])
    return ", ".join(f"{field}={node['data'][field]}" for field in label_fields)
