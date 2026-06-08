import csv
import io
import json

import pytest
from django.db import transaction

from tests.models import (
    AL_TestNode,
    AL_TestNodeSorted,
    MP_TestNode,
    MP_TestNodeSorted,
    NS_TestNode,
    NS_TestNodeSorted,
)
from treebeard.export import ExportFormat, export_tree

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

SORTED_DATA = [
    {"data": {"desc": "root1", "val1": 2, "val2": 1}},
    {
        "data": {"desc": "root2", "val1": 1, "val2": 2},
        "children": [
            {"data": {"desc": "child1", "val1": 1, "val2": 1}},
            {"data": {"desc": "child2", "val1": 2, "val2": 2}},
        ],
    },
]

BASE_MODELS = [MP_TestNode, NS_TestNode, AL_TestNode]
SORTED_MODELS = [MP_TestNodeSorted, NS_TestNodeSorted, AL_TestNodeSorted]


@pytest.fixture(params=BASE_MODELS, ids=lambda m: m.__name__)
def tree_model(request):
    return request.param


@pytest.fixture(params=BASE_MODELS, ids=lambda m: m.__name__)
def tree_model_with_data(request):
    model = request.param
    model.load_bulk(BASE_DATA)
    return model


@pytest.fixture(params=SORTED_MODELS, ids=lambda m: m.__name__)
def sorted_model(request):
    return request.param


@pytest.fixture(params=SORTED_MODELS, ids=lambda m: m.__name__)
def sorted_model_with_data(request):
    model = request.param
    model.load_bulk(SORTED_DATA)
    return model


@pytest.mark.django_db
class TestExportJSON:
    def test_empty_tree(self, tree_model):
        result = export_tree(tree_model, format="json")
        assert result == []

    def test_single_node(self, tree_model):
        tree_model.add_root(desc="root")
        result = export_tree(tree_model, format="json")
        assert len(result) == 1
        assert "data" in result[0]
        assert result[0]["data"]["desc"] == "root"

    def test_multi_level_tree(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="json")
        assert len(result) == 4
        root_descs = [item["data"]["desc"] for item in result]
        assert "1" in root_descs
        assert "2" in root_descs
        assert "3" in root_descs
        assert "4" in root_descs
        node2 = next(item for item in result if item["data"]["desc"] == "2")
        assert "children" in node2
        assert len(node2["children"]) == 4
        node23 = next(c for c in node2["children"] if c["data"]["desc"] == "23")
        assert "children" in node23
        assert len(node23["children"]) == 1
        assert node23["children"][0]["data"]["desc"] == "231"

    def test_json_with_parent_filter(self, tree_model_with_data):
        root_nodes = list(tree_model_with_data.get_root_nodes())
        node2 = next(n for n in root_nodes if n.desc == "2")
        result = export_tree(tree_model_with_data, format="json", parent=node2)
        assert len(result) == 1
        assert result[0]["data"]["desc"] == "2"
        assert "children" in result[0]
        assert len(result[0]["children"]) == 4

    def test_json_with_fields_filter(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="json", fields=["desc"])
        assert len(result) == 4
        for item in result:
            assert "desc" in item["data"]
            assert len(item["data"]) == 1

    def test_json_preserves_ids(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="json")
        pk_field = tree_model_with_data._meta.pk.attname
        for item in result:
            assert pk_field in item

    def test_json_sorted_tree(self, sorted_model_with_data):
        result = export_tree(sorted_model_with_data, format="json")
        assert len(result) == 2
        root_descs = [item["data"]["desc"] for item in result]
        assert root_descs == ["root2", "root1"]


@pytest.mark.django_db
class TestExportCSV:
    def test_empty_tree(self, tree_model):
        result = export_tree(tree_model, format="csv")
        lines = result.strip().split("\n")
        assert len(lines) == 1
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 0

    def test_single_node(self, tree_model):
        tree_model.add_root(desc="root")
        result = export_tree(tree_model, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["desc"] == "root"

    def test_multi_level_tree(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 10
        descs = [row["desc"] for row in rows]
        assert descs == ["1", "2", "21", "22", "23", "231", "24", "3", "4", "41"]

    def test_csv_core_fields_mp(self):
        MP_TestNode.load_bulk(BASE_DATA)
        result = export_tree(MP_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert "path" in reader.fieldnames
        assert "depth" in reader.fieldnames
        assert "numchild" in reader.fieldnames
        assert rows[0]["depth"] == "1"

    def test_csv_core_fields_ns(self):
        NS_TestNode.load_bulk(BASE_DATA)
        result = export_tree(NS_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert "lft" in reader.fieldnames
        assert "rgt" in reader.fieldnames
        assert "tree_id" in reader.fieldnames
        assert "depth" in reader.fieldnames
        assert rows[0]["depth"] == "1"

    def test_csv_core_fields_al(self):
        AL_TestNode.load_bulk(BASE_DATA)
        result = export_tree(AL_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert "parent_id" in reader.fieldnames
        assert "depth" in reader.fieldnames
        assert rows[0]["depth"] == "1"
        assert rows[0]["parent_id"] == "" or rows[0]["parent_id"] == "None"

    def test_csv_with_fields_filter(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="csv", fields=["desc", "depth"])
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert set(reader.fieldnames) == {"desc", "depth"}
        assert len(rows) == 10
        assert rows[0]["desc"] == "1"

    def test_csv_with_parent_filter(self, tree_model_with_data):
        root_nodes = list(tree_model_with_data.get_root_nodes())
        node2 = next(n for n in root_nodes if n.desc == "2")
        result = export_tree(tree_model_with_data, format="csv", parent=node2)
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 6
        descs = [row["desc"] for row in rows]
        assert "2" in descs
        assert "21" in descs

    def test_csv_sorted_tree(self, sorted_model_with_data):
        result = export_tree(sorted_model_with_data, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 4


@pytest.mark.django_db
class TestExportText:
    def test_empty_tree(self, tree_model):
        result = export_tree(tree_model, format="text")
        assert result == ""

    def test_single_node(self, tree_model):
        tree_model.add_root(desc="root")
        result = export_tree(tree_model, format="text")
        assert "root" in result
        lines = result.split("\n")
        assert len(lines) == 1

    def test_multi_level_tree(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="text")
        lines = result.split("\n")
        assert len(lines) == 10
        assert "1" in lines[0]
        assert "2" in lines[1]
        assert "\u251c\u2500\u2500" in result or "\u2514\u2500\u2500" in result

    def test_text_tree_connectors(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="text")
        assert "\u2514\u2500\u2500" in result
        assert "\u251c\u2500\u2500" in result

    def test_text_with_parent_filter(self, tree_model_with_data):
        root_nodes = list(tree_model_with_data.get_root_nodes())
        node2 = next(n for n in root_nodes if n.desc == "2")
        result = export_tree(tree_model_with_data, format="text", parent=node2)
        lines = result.split("\n")
        assert len(lines) == 6
        assert "2" in lines[0]

    def test_text_with_fields_filter(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="text", fields=["desc"])
        assert "1" in result
        lines = result.split("\n")
        assert len(lines) == 10

    def test_text_sorted_tree(self, sorted_model_with_data):
        result = export_tree(sorted_model_with_data, format="text")
        lines = result.split("\n")
        assert len(lines) == 4


class TestExportTreeInterface:
    def test_invalid_format(self, tree_model):
        with pytest.raises(ValueError, match="Unsupported format"):
            export_tree(tree_model, format="xml")

    def test_unsupported_source_type(self):
        with pytest.raises(TypeError):
            export_tree("not_a_model", format="json")

    @pytest.mark.django_db
    def test_export_from_queryset(self, tree_model_with_data):
        qs = tree_model_with_data.objects.all()
        result = export_tree(qs, format="json")
        assert len(result) == 4

    @pytest.mark.django_db
    def test_export_from_node_instance(self, tree_model_with_data):
        root = tree_model_with_data.get_first_root_node()
        result = export_tree(root, format="json")
        assert len(result) >= 1

    @pytest.mark.django_db
    def test_format_enum(self, tree_model):
        tree_model.add_root(desc="root")
        result = export_tree(tree_model, format=ExportFormat.JSON)
        assert len(result) == 1

    @pytest.mark.django_db
    def test_export_returns_correct_type_json(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="json")
        assert isinstance(result, list)

    @pytest.mark.django_db
    def test_export_returns_correct_type_csv(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="csv")
        assert isinstance(result, str)

    @pytest.mark.django_db
    def test_export_returns_correct_type_text(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="text")
        assert isinstance(result, str)


@pytest.mark.django_db
class TestExportTreeSpecificModels:
    def test_mp_node_json(self):
        MP_TestNode.load_bulk(BASE_DATA)
        result = export_tree(MP_TestNode, format="json")
        assert len(result) == 4
        node2 = next(item for item in result if item["data"]["desc"] == "2")
        assert len(node2["children"]) == 4

    def test_ns_node_json(self):
        NS_TestNode.load_bulk(BASE_DATA)
        result = export_tree(NS_TestNode, format="json")
        assert len(result) == 4
        node2 = next(item for item in result if item["data"]["desc"] == "2")
        assert len(node2["children"]) == 4

    def test_al_node_json(self):
        AL_TestNode.load_bulk(BASE_DATA)
        result = export_tree(AL_TestNode, format="json")
        assert len(result) == 4
        node2 = next(item for item in result if item["data"]["desc"] == "2")
        assert len(node2["children"]) == 4

    def test_mp_node_csv_core_fields(self):
        MP_TestNode.load_bulk(BASE_DATA)
        result = export_tree(MP_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        fieldnames = set(reader.fieldnames)
        assert "path" in fieldnames
        assert "depth" in fieldnames
        assert "numchild" in fieldnames

    def test_ns_node_csv_core_fields(self):
        NS_TestNode.load_bulk(BASE_DATA)
        result = export_tree(NS_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        fieldnames = set(reader.fieldnames)
        assert "lft" in fieldnames
        assert "rgt" in fieldnames
        assert "tree_id" in fieldnames
        assert "depth" in fieldnames

    def test_al_node_csv_core_fields(self):
        AL_TestNode.load_bulk(BASE_DATA)
        result = export_tree(AL_TestNode, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        fieldnames = set(reader.fieldnames)
        assert "parent_id" in fieldnames
        assert "depth" in fieldnames

    def test_mp_node_text(self):
        MP_TestNode.load_bulk(BASE_DATA)
        result = export_tree(MP_TestNode, format="text")
        assert "1" in result
        assert "\u2514\u2500\u2500" in result

    def test_ns_node_text(self):
        NS_TestNode.load_bulk(BASE_DATA)
        result = export_tree(NS_TestNode, format="text")
        assert "1" in result
        assert "\u2514\u2500\u2500" in result

    def test_al_node_text(self):
        AL_TestNode.load_bulk(BASE_DATA)
        result = export_tree(AL_TestNode, format="text")
        assert "1" in result
        assert "\u2514\u2500\u2500" in result


@pytest.mark.django_db
class TestExportSortedTree:
    def test_sorted_json(self):
        MP_TestNodeSorted.load_bulk(SORTED_DATA)
        result = export_tree(MP_TestNodeSorted, format="json")
        assert len(result) == 2
        root_descs = [item["data"]["desc"] for item in result]
        assert root_descs == ["root2", "root1"]

    def test_sorted_csv(self):
        NS_TestNodeSorted.load_bulk(SORTED_DATA)
        result = export_tree(NS_TestNodeSorted, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert len(rows) == 4

    def test_sorted_text(self):
        AL_TestNodeSorted.load_bulk(SORTED_DATA)
        result = export_tree(AL_TestNodeSorted, format="text")
        lines = result.split("\n")
        assert len(lines) == 4


@pytest.mark.django_db
class TestExportTreeDepth:
    def test_text_tree_depth_representation(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="text")
        lines = result.split("\n")
        root_line = lines[0]
        assert not root_line.startswith(" ")
        assert not root_line.startswith("\u2502")
        child_line = None
        for line in lines[1:]:
            if "\u251c\u2500\u2500" in line or "\u2514\u2500\u2500" in line:
                child_line = line
                break
        if child_line:
            assert child_line.startswith("\u251c\u2500\u2500") or child_line.startswith("\u2514\u2500\u2500")

    def test_csv_depth_values(self, tree_model_with_data):
        result = export_tree(tree_model_with_data, format="csv")
        reader = csv.DictReader(io.StringIO(result))
        rows = list(reader)
        assert rows[0]["depth"] == "1"
        depth_2_rows = [r for r in rows if r["depth"] == "2"]
        assert len(depth_2_rows) == 5
