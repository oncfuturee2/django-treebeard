from contextlib import contextmanager

import pytest

from tests.models import MP_TestNode
from treebeard.mp_tree import nodes_deleted as mp_nodes_deleted


MP_DELETE_DATA = [
    {
        "data": {"desc": "root-a"},
        "children": [
            {
                "data": {"desc": "a-branch"},
                "children": [
                    {
                        "data": {"desc": "a-left"},
                        "children": [
                            {"data": {"desc": "a-left-leaf"}},
                        ],
                    },
                    {
                        "data": {"desc": "a-right"},
                        "children": [
                            {"data": {"desc": "a-right-leaf"}},
                        ],
                    },
                ],
            },
            {"data": {"desc": "a-sibling-1"}},
            {"data": {"desc": "a-sibling-2"}},
        ],
    },
    {
        "data": {"desc": "root-b"},
        "children": [
            {"data": {"desc": "b-left"}},
            {
                "data": {"desc": "b-mid"},
                "children": [
                    {"data": {"desc": "b-mid-leaf"}},
                ],
            },
            {"data": {"desc": "b-right"}},
        ],
    },
    {"data": {"desc": "root-c"}},
]


@contextmanager
def capture_mp_delete_signals():
    calls = []

    def handler(sender, **kwargs):
        calls.append((kwargs["pks_to_remove"], kwargs["paths_to_remove"], kwargs["using"]))

    mp_nodes_deleted.connect(handler)
    try:
        yield calls
    finally:
        mp_nodes_deleted.disconnect(handler)


@pytest.fixture
def mp_delete_tree():
    MP_TestNode.load_bulk(MP_DELETE_DATA)
    return MP_TestNode


def tree_state(model):
    return list(model.objects.order_by("path").values_list("desc", "path", "depth", "numchild"))


@pytest.mark.django_db
class TestMPNodeQuerySetDelete:
    def test_delete_single_leaf(self, mp_delete_tree):
        model = mp_delete_tree

        result = model.objects.filter(desc="b-mid-leaf").delete()

        assert result == (1, {model._meta.label: 1})
        assert tree_state(model) == [
            ("root-a", "001", 1, 3),
            ("a-branch", "001001", 2, 2),
            ("a-left", "001001001", 3, 1),
            ("a-left-leaf", "001001001001", 4, 0),
            ("a-right", "001001002", 3, 1),
            ("a-right-leaf", "001001002001", 4, 0),
            ("a-sibling-1", "001002", 2, 0),
            ("a-sibling-2", "001003", 2, 0),
            ("root-b", "002", 1, 3),
            ("b-left", "002001", 2, 0),
            ("b-mid", "002002", 2, 0),
            ("b-right", "002003", 2, 0),
            ("root-c", "003", 1, 0),
        ]

    def test_delete_non_leaf_with_multiple_subtrees(self, mp_delete_tree):
        model = mp_delete_tree

        result = model.objects.filter(desc="a-branch").delete()

        assert result == (5, {model._meta.label: 5})
        assert tree_state(model) == [
            ("root-a", "001", 1, 2),
            ("a-sibling-1", "001002", 2, 0),
            ("a-sibling-2", "001003", 2, 0),
            ("root-b", "002", 1, 3),
            ("b-left", "002001", 2, 0),
            ("b-mid", "002002", 2, 1),
            ("b-mid-leaf", "002002001", 3, 0),
            ("b-right", "002003", 2, 0),
            ("root-c", "003", 1, 0),
        ]

    def test_delete_overlapping_ancestor_descendant_nodes_deduplicates_paths(self, mp_delete_tree):
        model = mp_delete_tree
        sibling = model.objects.get(desc="a-sibling-1")

        with capture_mp_delete_signals() as signals:
            result = model.objects.filter(desc__in=("a-branch", "a-left", "a-left-leaf", "a-sibling-1")).delete()

        assert result == (6, {model._meta.label: 6})
        assert signals == [([sibling.pk], ["001001"], "default")]
        assert tree_state(model) == [
            ("root-a", "001", 1, 1),
            ("a-sibling-2", "001003", 2, 0),
            ("root-b", "002", 1, 3),
            ("b-left", "002001", 2, 0),
            ("b-mid", "002002", 2, 1),
            ("b-mid-leaf", "002002001", 3, 0),
            ("b-right", "002003", 2, 0),
            ("root-c", "003", 1, 0),
        ]

    def test_delete_multiple_siblings_updates_numchild_precisely(self, mp_delete_tree):
        model = mp_delete_tree

        result = model.objects.filter(desc__in=("b-left", "b-right")).delete()

        assert result == (2, {model._meta.label: 2})
        assert tree_state(model) == [
            ("root-a", "001", 1, 3),
            ("a-branch", "001001", 2, 2),
            ("a-left", "001001001", 3, 1),
            ("a-left-leaf", "001001001001", 4, 0),
            ("a-right", "001001002", 3, 1),
            ("a-right-leaf", "001001002001", 4, 0),
            ("a-sibling-1", "001002", 2, 0),
            ("a-sibling-2", "001003", 2, 0),
            ("root-b", "002", 1, 1),
            ("b-mid", "002002", 2, 1),
            ("b-mid-leaf", "002002001", 3, 0),
            ("root-c", "003", 1, 0),
        ]

    def test_delete_nodes_across_multiple_roots(self, mp_delete_tree):
        model = mp_delete_tree

        result = model.objects.filter(desc__in=("a-sibling-1", "b-mid", "root-c")).delete()

        assert result == (4, {model._meta.label: 4})
        assert tree_state(model) == [
            ("root-a", "001", 1, 2),
            ("a-branch", "001001", 2, 2),
            ("a-left", "001001001", 3, 1),
            ("a-left-leaf", "001001001001", 4, 0),
            ("a-right", "001001002", 3, 1),
            ("a-right-leaf", "001001002001", 4, 0),
            ("a-sibling-2", "001003", 2, 0),
            ("root-b", "002", 1, 2),
            ("b-left", "002001", 2, 0),
            ("b-right", "002003", 2, 0),
        ]
