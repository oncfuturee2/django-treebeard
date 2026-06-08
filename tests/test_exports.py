import csv
import io
import json

import pytest

from treebeard.al_tree import AL_Node
from treebeard.exports import (
    ExportFormat,
    export_csv,
    export_json,
    export_text,
    export_to_csv,
    export_to_json,
    export_to_text,
    export_tree,
    get_flattened_nodes,
    get_node_field_value,
    get_node_label,
    get_parent_pk,
)
from treebeard.mp_tree import MP_Node
from treebeard.ns_tree import NS_Node

from tests import models

BASE_DATA = [
    {"data": {"desc": "1"}},
    {
        "data": {"desc": "2"},
        "children": [
            {"data": {"desc": "21"}},
            {"data": {"desc": "22"}},
            {
                "data": {"desc": "23"},
                "children": [
                    {"data": {"desc": "231"}},
                ],
            },
            {"data": {"desc": "24"}},
        ],
    },
    {"data": {"desc": "3"}},
    {
        "data": {"desc": "4"},
        "children": [
            {"data": {"desc": "41"}},
        ],
    },
]


@pytest.fixture(scope="function", params=models.BASE_MODELS)
def model_with_data(request):
    request.param.load_bulk(BASE_DATA)
    return request.param


@pytest.fixture(scope="function", params=models.BASE_MODELS)
def model_empty(request):
    return request.param


@pytest.fixture(scope="function", params=models.SORTED_MODELS)
def sorted_model(request):
    return request.param


class TestExportEmptyTree:
    @pytest.mark.django_db
    def test_export_json_empty(self, model_empty):
        result = export_tree(model_empty, ExportFormat.JSON)
        assert result == []

    @pytest.mark.django_db
    def test_export_csv_empty(self, model_empty):
        result = export_tree(model_empty, ExportFormat.CSV)
        assert result == ""

    @pytest.mark.django_db
    def test_export_text_empty(self, model_empty):
        result = export_tree(model_empty, ExportFormat.TEXT)
        assert result == ""

    @pytest.mark.django_db
    def test_export_to_json_empty(self, model_empty):
        result = export_to_json(model_empty)
        assert result == "[]"

    @pytest.mark.django_db
    def test_export_to_csv_empty(self, model_empty):
        result = export_to_csv(model_empty)
        assert result == ""

    @pytest.mark.django_db
    def test_export_to_text_empty(self, model_empty):
        result = export_to_text(model_empty)
        assert result == ""


class TestExportJSON:
    @pytest.mark.django_db
    def test_export_json_basic(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.JSON)

        assert isinstance(result, list)
        assert len(result) == 4

        root_descs = [item["data"]["desc"] for item in result]
        assert root_descs == ["1", "2", "3", "4"]

        node2 = result[1]
        children_of_2 = [item["data"]["desc"] for item in node2["children"]]
        assert children_of_2 == ["21", "22", "23", "24"]

        node23 = node2["children"][2]
        children_of_23 = [item["data"]["desc"] for item in node23["children"]]
        assert children_of_23 == ["231"]

    @pytest.mark.django_db
    def test_export_json_with_parent_filter(self, model_with_data):
        parent = model_with_data.objects.get(desc="2")
        result = export_tree(model_with_data, ExportFormat.JSON, parent=parent)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["data"]["desc"] == "2"
        children = [item["data"]["desc"] for item in result[0]["children"]]
        assert children == ["21", "22", "23", "24"]

    @pytest.mark.django_db
    def test_export_json_with_field_filter(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.JSON, fields=["desc"])

        for item in result:
            assert set(item["data"].keys()) == {"desc"}

    @pytest.mark.django_db
    def test_export_json_without_primary_key(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.JSON, include_primary_key=False)

        for item in result:
            assert "id" not in item
            assert "pk" not in item

    @pytest.mark.django_db
    def test_export_to_json_string(self, model_with_data):
        result = export_to_json(model_with_data)

        assert isinstance(result, str)
        parsed = json.loads(result)
        assert len(parsed) == 4
        assert parsed[0]["data"]["desc"] == "1"

    @pytest.mark.django_db
    def test_export_json_single_node(self, model_empty):
        model_empty.add_root(desc="single")
        result = export_tree(model_empty, ExportFormat.JSON)

        assert len(result) == 1
        assert result[0]["data"]["desc"] == "single"
        assert "children" not in result[0]


class TestExportCSV:
    @pytest.mark.django_db
    def test_export_csv_basic(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.CSV)

        assert isinstance(result, str)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 10

        descs = [row["desc"] for row in rows]
        assert descs == ["1", "2", "21", "22", "23", "231", "24", "3", "4", "41"]

    @pytest.mark.django_db
    def test_export_csv_has_core_fields(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.CSV)

        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) > 0

        fieldnames = reader.fieldnames
        assert "pk" in fieldnames
        assert "depth" in fieldnames
        assert "numchild" in fieldnames

    @pytest.mark.django_db
    def test_export_csv_mp_has_path_field(self):
        from tests.models import MP_TestNode

        MP_TestNode.load_bulk(BASE_DATA)
        result = export_tree(MP_TestNode, ExportFormat.CSV)

        reader = csv.DictReader(io.StringIO(result))
        assert "path" in reader.fieldnames

    @pytest.mark.django_db
    def test_export_csv_ns_has_ns_fields(self):
        from tests.models import NS_TestNode

        NS_TestNode.load_bulk(BASE_DATA)
        result = export_tree(NS_TestNode, ExportFormat.CSV)

        reader = csv.DictReader(io.StringIO(result))
        assert "lft" in reader.fieldnames
        assert "rgt" in reader.fieldnames
        assert "tree_id" in reader.fieldnames

    @pytest.mark.django_db
    def test_export_csv_al_has_parent_id(self):
        from tests.models import AL_TestNode

        AL_TestNode.load_bulk(BASE_DATA)
        result = export_tree(AL_TestNode, ExportFormat.CSV)

        reader = csv.DictReader(io.StringIO(result))
        assert "parent_id" in reader.fieldnames

    @pytest.mark.django_db
    def test_export_csv_with_field_filter(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.CSV, fields=["desc"])

        reader = csv.DictReader(io.StringIO(result))
        fieldnames = reader.fieldnames
        assert "desc" in fieldnames
        rows = [row["desc"] for row in reader]
        assert rows == ["1", "2", "21", "22", "23", "231", "24", "3", "4", "41"]

    @pytest.mark.django_db
    def test_export_csv_parent_filter(self, model_with_data):
        parent = model_with_data.objects.get(desc="2")
        result = export_tree(model_with_data, ExportFormat.CSV, parent=parent)

        reader = csv.DictReader(io.StringIO(result))
        descs = [row["desc"] for row in reader]
        assert descs == ["2", "21", "22", "23", "231", "24"]

    @pytest.mark.django_db
    def test_export_to_csv_function(self, model_with_data):
        result = export_to_csv(model_with_data)

        assert isinstance(result, str)
        lines = result.strip().split("\n")
        assert len(lines) == 11  # header + 10 rows


class TestExportText:
    @pytest.mark.django_db
    def test_export_text_basic(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.TEXT)

        assert isinstance(result, str)
        lines = result.split("\n")
        assert len(lines) == 10

        assert "├── 1" in lines[0]
        assert "├── 2" in lines[1]
        assert "└── 4" in lines[-1]

    @pytest.mark.django_db
    def test_export_text_single_node(self, model_empty):
        model_empty.add_root(desc="single")
        result = export_tree(model_empty, ExportFormat.TEXT)

        assert "single" in result
        assert "└──" not in result
        assert "├──" not in result

    @pytest.mark.django_db
    def test_export_text_parent_filter(self, model_with_data):
        parent = model_with_data.objects.get(desc="2")
        result = export_tree(model_with_data, ExportFormat.TEXT, parent=parent)

        lines = result.split("\n")
        assert "2" in lines[0]
        assert "├──" in lines[1] or "└──" in lines[1]

    @pytest.mark.django_db
    def test_export_text_has_tree_connectors(self, model_with_data):
        result = export_tree(model_with_data, ExportFormat.TEXT)

        for tree_prefix in ["├──", "└──"]:
            assert tree_prefix in result

    @pytest.mark.django_db
    def test_export_to_text_function(self, model_with_data):
        result = export_to_text(model_with_data)

        assert isinstance(result, str)
        assert len(result) > 0


class TestExportTreeUnified:
    @pytest.mark.django_db
    def test_export_tree_with_queryset(self, model_with_data):
        qs = model_with_data.objects.all()
        result = export_tree(qs, ExportFormat.CSV)

        assert isinstance(result, str)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 10

    @pytest.mark.django_db
    def test_export_tree_invalid_format(self, model_with_data):
        with pytest.raises(ValueError, match="Unsupported export format"):
            export_tree(model_with_data, "invalid")


class TestExportSortedTree:
    @pytest.mark.django_db
    def test_export_text_sorted_tree(self, sorted_model):
        import random

        root = sorted_model.add_root(desc="root", val1=0, val2=0)
        values = list(range(10, 50, 10))
        random.shuffle(values)
        for v in values:
            root.add_child(desc=f"child-{v}", val1=v, val2=1)

        result = export_tree(sorted_model, ExportFormat.TEXT)

        lines = result.split("\n")
        child_descs = [line.strip().lstrip("├└── ") for line in lines[1:]]
        assert child_descs == sorted(child_descs, key=lambda x: int(x.split("-")[1]))

    @pytest.mark.django_db
    def test_export_csv_sorted_tree(self, sorted_model):
        root = sorted_model.add_root(desc="root", val1=0, val2=0)
        for v in [10, 30, 20]:
            root.add_child(desc=f"child-{v}", val1=v, val2=1)

        result = export_tree(sorted_model, ExportFormat.CSV)
        reader = csv.DictReader(io.StringIO(result))
        child_rows = [row for row in reader if row["desc"] != "root"]
        child_descs = [row["desc"] for row in child_rows]
        assert child_descs == ["child-10", "child-20", "child-30"]

    @pytest.mark.django_db
    def test_export_json_sorted_tree(self, sorted_model):
        root = sorted_model.add_root(desc="root", val1=0, val2=0)
        for v in [10, 30, 20]:
            root.add_child(desc=f"child-{v}", val1=v, val2=1)

        result = export_tree(sorted_model, ExportFormat.JSON)
        child_descs = [item["data"]["desc"] for item in result[0]["children"]]
        assert child_descs == ["child-10", "child-20", "child-30"]


class TestExportDeepTree:
    @pytest.mark.django_db
    def test_export_json_deep_tree(self, model_empty):
        root = model_empty.add_root(desc="A")
        b = root.add_child(desc="B")
        c = b.add_child(desc="C")
        c.add_child(desc="D")

        result = export_tree(model_empty, ExportFormat.JSON)

        assert len(result) == 1
        assert result[0]["data"]["desc"] == "A"
        assert len(result[0]["children"]) == 1
        assert result[0]["children"][0]["data"]["desc"] == "B"
        assert len(result[0]["children"][0]["children"]) == 1
        assert result[0]["children"][0]["children"][0]["data"]["desc"] == "C"
        assert len(result[0]["children"][0]["children"][0]["children"]) == 1
        assert result[0]["children"][0]["children"][0]["children"][0]["data"]["desc"] == "D"

    @pytest.mark.django_db
    def test_export_csv_deep_tree(self, model_empty):
        root = model_empty.add_root(desc="A")
        b = root.add_child(desc="B")
        c = b.add_child(desc="C")
        c.add_child(desc="D")

        result = export_tree(model_empty, ExportFormat.CSV)
        reader = csv.DictReader(io.StringIO(result))
        descs = [row["desc"] for row in reader]
        assert descs == ["A", "B", "C", "D"]

    @pytest.mark.django_db
    def test_export_text_deep_tree(self, model_empty):
        root = model_empty.add_root(desc="A")
        b = root.add_child(desc="B")
        c = b.add_child(desc="C")
        c.add_child(desc="D")

        result = export_tree(model_empty, ExportFormat.TEXT)
        lines = result.split("\n")
        assert "A" in lines[0]
        assert any("B" in line for line in lines)
        assert any("C" in line for line in lines)
        assert any("D" in line for line in lines)


class TestExportMultiRootTree:
    @pytest.mark.django_db
    def test_export_json_multi_root(self, model_empty):
        model_empty.add_root(desc="R1")
        model_empty.add_root(desc="R2")
        model_empty.add_root(desc="R3")

        result = export_tree(model_empty, ExportFormat.JSON)
        assert len(result) == 3
        descs = [item["data"]["desc"] for item in result]
        assert descs == ["R1", "R2", "R3"]

    @pytest.mark.django_db
    def test_export_text_multi_root(self, model_empty):
        model_empty.add_root(desc="R1")
        model_empty.add_root(desc="R2")
        model_empty.add_root(desc="R3")

        result = export_tree(model_empty, ExportFormat.TEXT)
        lines = result.split("\n")
        assert len(lines) == 3
        assert "R1" in lines[0]
        assert "R2" in lines[1]
        assert "R3" in lines[2]

    @pytest.mark.django_db
    def test_export_csv_multi_root(self, model_empty):
        model_empty.add_root(desc="R1")
        model_empty.add_root(desc="R2")
        model_empty.add_root(desc="R3")

        result = export_tree(model_empty, ExportFormat.CSV)
        reader = csv.DictReader(io.StringIO(result))
        descs = [row["desc"] for row in reader]
        assert descs == ["R1", "R2", "R3"]
        depths = [int(row["depth"]) for row in csv.DictReader(io.StringIO(result))]
        assert depths == [1, 1, 1]


class TestHelperFunctions:
    @pytest.mark.django_db
    def test_get_flattened_nodes(self, model_with_data):
        nodes = get_flattened_nodes(model_with_data, None)
        assert len(nodes) == 10
        descs = [node.desc for node in nodes]
        assert descs == ["1", "2", "21", "22", "23", "231", "24", "3", "4", "41"]

    @pytest.mark.django_db
    def test_get_flattened_nodes_with_parent(self, model_with_data):
        parent = model_with_data.objects.get(desc="2")
        nodes = get_flattened_nodes(model_with_data, parent)
        descs = [node.desc for node in nodes]
        assert descs == ["2", "21", "22", "23", "231", "24"]

    @pytest.mark.django_db
    def test_get_node_field_value(self, model_with_data):
        node = model_with_data.objects.get(desc="1")
        assert get_node_field_value(node, "pk") == node.pk
        assert get_node_field_value(node, "depth") == 1
        assert get_node_field_value(node, "desc") == "1"

    @pytest.mark.django_db
    def test_get_node_label_default(self, model_with_data):
        node = model_with_data.objects.get(desc="1")
        label = get_node_label(node, None)
        assert label == "1"

    @pytest.mark.django_db
    def test_get_node_label_with_fields(self, model_with_data):
        node = model_with_data.objects.get(desc="1")
        label = get_node_label(node, ["desc"])
        assert label == "1"

    @pytest.mark.django_db
    def test_get_parent_pk_mp(self):
        from tests.models import MP_TestNode

        MP_TestNode.load_bulk(BASE_DATA)
        root = MP_TestNode.objects.get(desc="1")
        assert get_parent_pk(root) is None

        parent = MP_TestNode.objects.get(desc="2")
        child = MP_TestNode.objects.get(desc="21")
        assert get_parent_pk(child) == parent.pk

    @pytest.mark.django_db
    def test_get_parent_pk_ns(self):
        from tests.models import NS_TestNode

        NS_TestNode.load_bulk(BASE_DATA)
        root = NS_TestNode.objects.get(desc="1")
        assert get_parent_pk(root) is None

        child = NS_TestNode.objects.get(desc="21")
        assert get_parent_pk(child) is not None

    @pytest.mark.django_db
    def test_get_parent_pk_al(self):
        from tests.models import AL_TestNode

        AL_TestNode.load_bulk(BASE_DATA)
        root = AL_TestNode.objects.get(desc="1")
        assert get_parent_pk(root) is None

        child = AL_TestNode.objects.get(desc="21")
        assert get_parent_pk(child) is not None


class TestExportFormatClass:
    def test_export_format_constants(self):
        assert ExportFormat.JSON == "json"
        assert ExportFormat.CSV == "csv"
        assert ExportFormat.TEXT == "text"


class TestExportJSONViaQueryset:
    @pytest.mark.django_db
    def test_export_json_from_queryset_mp(self):
        from tests.models import MP_TestNode

        MP_TestNode.load_bulk(BASE_DATA)
        qs = MP_TestNode.objects.all()
        result = export_tree(qs, ExportFormat.JSON)
        assert len(result) == 4
        assert result[0]["data"]["desc"] == "1"

    @pytest.mark.django_db
    def test_export_json_from_queryset_ns(self):
        from tests.models import NS_TestNode

        NS_TestNode.load_bulk(BASE_DATA)
        qs = NS_TestNode.objects.all()
        result = export_tree(qs, ExportFormat.JSON)
        assert len(result) == 4
        assert result[0]["data"]["desc"] == "1"

    @pytest.mark.django_db
    def test_export_json_from_queryset_al(self):
        from tests.models import AL_TestNode

        AL_TestNode.load_bulk(BASE_DATA)
        qs = AL_TestNode.objects.all()
        result = export_tree(qs, ExportFormat.JSON)
        assert len(result) == 4
        assert result[0]["data"]["desc"] == "1"