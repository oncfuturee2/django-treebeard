import csv
import json
from io import StringIO

import pytest

from tests import models
from treebeard.exports import export_tree

BASE_DATA = [
    {"data": {"desc": "1"}},
    {
        "data": {"desc": "2"},
        "children": [
            {"data": {"desc": "21"}},
            {"data": {"desc": "22"}},
            {"data": {"desc": "23"}, "children": [{"data": {"desc": "231"}}]},
            {"data": {"desc": "24"}},
        ],
    },
    {"data": {"desc": "3"}},
    {"data": {"desc": "4"}, "children": [{"data": {"desc": "41"}}]},
]

SORTED_CHILDREN = [
    {"val1": 3, "val2": 3, "desc": "zxy"},
    {"val1": 1, "val2": 4, "desc": "bcd"},
    {"val1": 2, "val2": 5, "desc": "zxy"},
    {"val1": 3, "val2": 3, "desc": "abc"},
    {"val1": 4, "val2": 1, "desc": "fgh"},
    {"val1": 3, "val2": 3, "desc": "abc"},
    {"val1": 2, "val2": 2, "desc": "qwe"},
    {"val1": 3, "val2": 2, "desc": "vcx"},
]

EXPECTED_TEXT_TREE = "\n".join(
    [
        "1",
        "2",
        "├── 21",
        "├── 22",
        "├── 23",
        "│   └── 231",
        "└── 24",
        "3",
        "4",
        "└── 41",
    ]
)

EXPECTED_SORTED_DESCS = ["aaa", "bcd", "qwe", "zxy", "vcx", "zxy", "abc", "abc", "fgh"]


@pytest.fixture(params=[models.AL_TestNode, models.MP_TestNode, models.NS_TestNode])
def export_model(request):
    return request.param


@pytest.fixture(params=models.SORTED_MODELS)
def sorted_export_model(request):
    return request.param


def _csv_rows(content):
    return list(csv.DictReader(StringIO(content)))


@pytest.mark.django_db
class TestTreeExports:
    def test_export_empty_tree_returns_empty_structures(self, export_model):
        json_data = json.loads(export_tree(export_model.objects.all(), "json"))
        csv_rows = _csv_rows(export_tree(export_model.objects.all(), "csv"))
        text_data = export_tree(export_model.objects.all(), "text")

        assert json_data == []
        assert csv_rows == []
        assert text_data == ""

    def test_export_single_node_all_formats(self, export_model):
        root = export_model.add_root(desc="root")

        json_data = json.loads(export_tree(root, "json"))
        csv_rows = _csv_rows(export_tree(root, "csv"))
        text_data = export_tree(root, "text")

        assert len(json_data) == 1
        assert json_data[0]["depth"] == 1
        assert json_data[0]["numchild"] == 0
        assert json_data[0]["data"] == {"desc": "root"}
        assert json_data[0]["path"]
        assert csv_rows == [
            {
                "id": str(root.pk),
                "parent_id": "",
                "path": json_data[0]["path"],
                "depth": "1",
                "numchild": "0",
                "desc": "root",
            }
        ]
        assert text_data == "root"

    def test_export_multilevel_tree_all_formats(self, export_model):
        export_model.load_bulk(BASE_DATA)

        json_data = json.loads(export_tree(export_model.objects.all(), "json"))
        csv_rows = _csv_rows(export_tree(export_model.objects.all(), "csv"))
        text_data = export_tree(export_model.objects.all(), "text")

        assert [node["data"]["desc"] for node in json_data] == ["1", "2", "3", "4"]
        assert [child["data"]["desc"] for child in json_data[1]["children"]] == ["21", "22", "23", "24"]
        assert json_data[1]["children"][2]["children"][0]["data"]["desc"] == "231"
        assert [row["desc"] for row in csv_rows] == ["1", "2", "21", "22", "23", "231", "24", "3", "4", "41"]
        assert [row["depth"] for row in csv_rows] == ["1", "1", "2", "2", "2", "3", "2", "1", "1", "2"]
        assert [row["numchild"] for row in csv_rows] == ["0", "4", "0", "0", "1", "0", "0", "0", "1", "0"]
        assert all(row["path"] for row in csv_rows)
        assert text_data == EXPECTED_TEXT_TREE

    def test_export_branch_with_parent_and_field_filter(self, export_model):
        export_model.load_bulk(BASE_DATA)
        parent = export_model.objects.get(desc="2")

        json_data = json.loads(export_tree(export_model.objects.all(), "json", parent=parent, fields=["desc"]))
        text_data = export_tree(export_model.objects.all(), "text", parent=parent, fields=["desc"])

        assert [node["data"]["desc"] for node in json_data] == ["2"]
        assert [child["data"]["desc"] for child in json_data[0]["children"]] == ["21", "22", "23", "24"]
        assert set(json_data[0]["data"].keys()) == {"desc"}
        assert text_data == "\n".join(["2", "├── 21", "├── 22", "├── 23", "│   └── 231", "└── 24"])

    def test_export_preserves_sorted_order(self, sorted_export_model):
        root = sorted_export_model.add_root(val1=0, val2=0, desc="aaa")
        for child in SORTED_CHILDREN:
            root.add_child(**child)

        csv_rows = _csv_rows(export_tree(root, "csv", fields=["desc", "val1", "val2"]))
        text_data = export_tree(root, "text", fields=["desc"])

        assert [row["desc"] for row in csv_rows] == EXPECTED_SORTED_DESCS
        assert [row["depth"] for row in csv_rows] == ["1", "2", "2", "2", "2", "2", "2", "2", "2"]
        assert text_data == "\n".join(
            [
                "aaa",
                "├── bcd",
                "├── qwe",
                "├── zxy",
                "├── vcx",
                "├── zxy",
                "├── abc",
                "├── abc",
                "└── fgh",
            ]
        )
