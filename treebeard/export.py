import csv
import io
import json
from enum import Enum

from treebeard.al_tree import AL_Node
from treebeard.mp_tree import MP_Node
from treebeard.ns_tree import NS_Node


class ExportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    TEXT = "text"


TREE_CORE_FIELDS = {
    MP_Node: ["path", "depth", "numchild"],
    NS_Node: ["lft", "rgt", "tree_id", "depth"],
    AL_Node: ["parent_id", "depth"],
}


def _detect_tree_type(model_cls):
    if issubclass(model_cls, MP_Node):
        return MP_Node
    if issubclass(model_cls, NS_Node):
        return NS_Node
    if issubclass(model_cls, AL_Node):
        return AL_Node
    raise TypeError(f"Unsupported tree model: {model_cls}")


def _get_node_depth(node):
    try:
        return node.depth
    except AttributeError:
        return node.get_depth()


def _get_core_fields(node, tree_type):
    if tree_type == MP_Node:
        return {
            "path": node.path,
            "depth": node.depth,
            "numchild": node.numchild,
        }
    elif tree_type == NS_Node:
        return {
            "lft": node.lft,
            "rgt": node.rgt,
            "tree_id": node.tree_id,
            "depth": node.depth,
        }
    elif tree_type == AL_Node:
        return {
            "parent_id": node.parent_id,
            "depth": _get_node_depth(node),
        }
    return {}


def _get_user_fields(node, fields, tree_type):
    core_field_names = set(TREE_CORE_FIELDS.get(tree_type, []))
    if "parent_id" not in core_field_names and tree_type == AL_Node:
        core_field_names.add("parent_id")
    result = {}
    for f in fields:
        if f in core_field_names:
            continue
        val = getattr(node, f, None)
        if callable(val):
            val = val()
        result[f] = val
    return result


def _node_to_dict(node, tree_type, fields=None):
    core = _get_core_fields(node, tree_type)
    if fields:
        user = _get_user_fields(node, fields, tree_type)
        combined = {**core, **user}
        ordered = {}
        for f in fields:
            if f in combined:
                ordered[f] = combined[f]
        for k, v in combined.items():
            if k not in ordered:
                ordered[k] = v
        return ordered
    return dict(core)


def _flatten_dump_bulk(bulk_data, tree_type, fields=None, pk_field="id"):
    rows = []
    for item in bulk_data:
        data = dict(item.get("data", {}))
        if pk_field in item:
            data[pk_field] = item[pk_field]
        row = dict(data)
        rows.append(row)
        children = item.get("children", [])
        if children:
            rows.extend(_flatten_dump_bulk(children, tree_type, fields, pk_field))
    return rows


def _export_json(model_cls, parent=None, fields=None):
    bulk_data = model_cls.dump_bulk(parent=parent, keep_ids=True)
    if fields is not None:
        pk_field = model_cls._meta.pk.attname
        filtered = []
        for item in bulk_data:
            new_item = _filter_dump_bulk_item(item, fields, pk_field)
            filtered.append(new_item)
        bulk_data = filtered
    return bulk_data


def _filter_dump_bulk_item(item, fields, pk_field):
    data = item.get("data", {})
    filtered_data = {k: v for k, v in data.items() if k in fields}
    new_item = {"data": filtered_data}
    if pk_field in item:
        new_item[pk_field] = item[pk_field]
    if pk_field in fields and pk_field in item:
        new_item[pk_field] = item[pk_field]
    children = item.get("children", [])
    if children:
        new_item["children"] = [_filter_dump_bulk_item(c, fields, pk_field) for c in children]
    return new_item


def _export_csv(model_cls, parent=None, fields=None):
    tree_type = _detect_tree_type(model_cls)
    nodes = model_cls.get_tree(parent)
    if hasattr(nodes, "iterator"):
        nodes = list(nodes.iterator())
    pk_field = model_cls._meta.pk.attname

    if fields is not None:
        header = list(fields)
    else:
        core = list(TREE_CORE_FIELDS.get(tree_type, []))
        extra = []
        if nodes:
            sample = nodes[0]
            all_field_names = [f.name for f in sample._meta.get_fields() if hasattr(f, 'column')]
            for fn in all_field_names:
                if fn not in core and fn != pk_field:
                    extra.append(fn)
        header = [pk_field] + core + extra

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for node in nodes:
        row = {}
        for f in header:
            if f == "depth" and tree_type == AL_Node:
                row[f] = _get_node_depth(node)
            elif f == "parent_id" and tree_type == AL_Node:
                row[f] = node.parent_id
            else:
                val = getattr(node, f, None)
                if callable(val) and not isinstance(val, (str, int, float, bool)):
                    val = val()
                row[f] = val
        writer.writerow(row)
    return output.getvalue()


def _export_text(model_cls, parent=None, fields=None):
    tree_type = _detect_tree_type(model_cls)
    nodes = model_cls.get_tree(parent)
    if hasattr(nodes, "iterator"):
        nodes = list(nodes.iterator())

    if not nodes:
        return ""

    lines = []
    depth_stack = []

    for i, node in enumerate(nodes):
        depth = _get_node_depth(node)
        label = _get_text_label(node, tree_type, fields)

        while len(depth_stack) > 0 and depth_stack[-1] >= depth:
            depth_stack.pop()

        parent_depth = depth_stack[-1] if depth_stack else 0
        is_last_child = _is_last_child(nodes, i, depth)

        indent = ""
        if depth > 1:
            parts = []
            for d in range(1, depth):
                if d in depth_stack or d < depth:
                    has_more = _has_more_siblings_at_depth(nodes, i, d)
                    if d < depth:
                        parts.append("\u2502   " if has_more else "    ")
                    else:
                        parts.append("\u251c\u2500\u2500 " if not is_last_child else "\u2514\u2500\u2500 ")
            indent = "".join(parts)
            if depth > 1:
                connector = "\u251c\u2500\u2500 " if not is_last_child else "\u2514\u2500\u2500 "
                prefix_parts = []
                for d in range(1, depth):
                    has_more = _has_more_siblings_at_depth(nodes, i, d)
                    if d < depth - 1:
                        prefix_parts.append("\u2502   " if has_more else "    ")
                indent = "".join(prefix_parts) + connector

        lines.append(f"{indent}{label}")
        depth_stack.append(depth)

    return "\n".join(lines)


def _has_more_siblings_at_depth(nodes, current_idx, depth):
    current_depth = _get_node_depth(nodes[current_idx])
    for j in range(current_idx + 1, len(nodes)):
        node_depth = _get_node_depth(nodes[j])
        if node_depth < depth:
            return False
        if node_depth == depth:
            return True
    return False


def _is_last_child(nodes, current_idx, depth):
    for j in range(current_idx + 1, len(nodes)):
        node_depth = _get_node_depth(nodes[j])
        if node_depth < depth:
            return True
        if node_depth == depth:
            return False
    return True


def _get_text_label(node, tree_type, fields):
    if fields:
        parts = []
        for f in fields:
            if f in ("path", "depth", "numchild", "lft", "rgt", "tree_id", "parent_id", "sib_order"):
                continue
            val = getattr(node, f, None)
            if callable(val) and not isinstance(val, (str, int, float, bool)):
                val = val()
            if val is not None:
                parts.append(str(val))
        if parts:
            return " ".join(parts)

    pk = node.pk
    desc = getattr(node, "desc", None)
    if desc is not None:
        return f"[{pk}] {desc}"
    str_val = str(node)
    return f"[{pk}] {str_val}"


_EXPORT_FUNCS = {
    ExportFormat.JSON: _export_json,
    ExportFormat.CSV: _export_csv,
    ExportFormat.TEXT: _export_text,
}


def export_tree(source, format="json", parent=None, fields=None):
    if isinstance(format, str):
        try:
            format = ExportFormat(format)
        except ValueError:
            raise ValueError(f"Unsupported format: {format}. Use one of: {', '.join(f.value for f in ExportFormat)}")

    model_cls = _resolve_model_class(source)

    if parent is None and source is not model_cls:
        if hasattr(source, "get_tree"):
            pass

    func = _EXPORT_FUNCS[format]
    return func(model_cls, parent=parent, fields=fields)


def _resolve_model_class(source):
    from django.db.models import QuerySet

    if isinstance(source, type) and issubclass(source, (MP_Node, NS_Node, AL_Node)):
        return source.tree_model()

    if isinstance(source, QuerySet):
        return source.model.tree_model()

    if hasattr(source, "get_tree") and hasattr(source, "tree_model"):
        return source.tree_model()

    if hasattr(source, "__class__") and issubclass(source.__class__, (MP_Node, NS_Node, AL_Node)):
        return source.__class__.tree_model()

    raise TypeError(f"Cannot resolve tree model from source: {source}")
