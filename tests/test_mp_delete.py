"""Pytest tests for MP_NodeQuerySet.delete method."""

import pytest

from tests.models import MP_TestNode


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


def get_tree_state():
    return [
        (n.desc, n.path, n.depth, n.numchild)
        for n in MP_TestNode.objects.order_by("path")
    ]


@pytest.fixture(scope="function")
def populated_tree():
    MP_TestNode.load_bulk(BASE_DATA)
    return MP_TestNode


@pytest.mark.django_db
class TestMPNodeDeleteLeaf:
    def test_delete_leaf_decrements_parent_numchild(self, populated_tree):
        leaf = populated_tree.objects.get(desc="231")
        parent = populated_tree.objects.get(desc="23")
        grandparent = populated_tree.objects.get(desc="2")

        assert parent.numchild == 1
        assert grandparent.numchild == 4

        leaf.delete()

        parent.refresh_from_db()
        grandparent.refresh_from_db()

        assert parent.numchild == 0
        assert grandparent.numchild == 4

        assert not populated_tree.objects.filter(desc="231").exists()
        assert populated_tree.objects.filter(desc="23").exists()

    def test_delete_leaf_keeps_other_nodes_unchanged(self, populated_tree):
        leaf = populated_tree.objects.get(desc="231")
        leaf.delete()

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "21", "22", "23", "24", "3", "4", "41"}
        assert remaining == expected

    def test_delete_leaf_paths_remain_valid(self, populated_tree):
        leaf = populated_tree.objects.get(desc="231")
        old_parent_path = populated_tree.objects.get(desc="23").path
        leaf.delete()

        parent = populated_tree.objects.get(desc="23")
        assert parent.path == old_parent_path
        assert parent.depth == 2
        assert parent.numchild == 0


@pytest.mark.django_db
class TestMPNodeDeleteNonLeaf:
    def test_delete_nonleaf_removes_descendants(self, populated_tree):
        node23 = populated_tree.objects.get(desc="23")
        node23.delete()

        assert not populated_tree.objects.filter(desc="23").exists()
        assert not populated_tree.objects.filter(desc="231").exists()

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "21", "22", "24", "3", "4", "41"}
        assert remaining == expected

    def test_delete_nonleaf_updates_parent_numchild(self, populated_tree):
        node23 = populated_tree.objects.get(desc="23")
        node23.delete()

        parent = populated_tree.objects.get(desc="2")
        assert parent.numchild == 3

    def test_delete_nonleaf_keeps_siblings_intact(self, populated_tree):
        node23 = populated_tree.objects.get(desc="23")
        node23.delete()

        siblings = populated_tree.objects.filter(
            path__startswith=populated_tree.objects.get(desc="2").path,
            depth=2,
        )
        sibling_descs = {n.desc for n in siblings}
        assert sibling_descs == {"21", "22", "24"}


@pytest.mark.django_db
class TestMPNodeDeleteAncestorDescendantOverlap:
    def test_ancestor_descendant_dedup(self, populated_tree):
        populated_tree.objects.filter(desc__in=("2", "23", "231")).delete()

        assert not populated_tree.objects.filter(desc="2").exists()
        assert not populated_tree.objects.filter(desc="21").exists()
        assert not populated_tree.objects.filter(desc="22").exists()
        assert not populated_tree.objects.filter(desc="23").exists()
        assert not populated_tree.objects.filter(desc="231").exists()
        assert not populated_tree.objects.filter(desc="24").exists()

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "3", "4", "41"}
        assert remaining == expected

        assert populated_tree.objects.get(desc="1").numchild == 0
        assert populated_tree.objects.get(desc="3").numchild == 0
        assert populated_tree.objects.get(desc="4").numchild == 1
        assert populated_tree.objects.get(desc="41").numchild == 0

    def test_ancestor_descendant_reversed_order(self, populated_tree):
        populated_tree.objects.filter(desc__in=("231", "2")).delete()

        assert not populated_tree.objects.filter(desc="2").exists()
        assert not populated_tree.objects.filter(path__startswith="002").exists()

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "3", "4", "41"}
        assert remaining == expected

    def test_middle_node_skipped_when_root_in_set(self, populated_tree):
        populated_tree.objects.filter(desc__in=("2", "22")).delete()

        assert not populated_tree.objects.filter(desc="2").exists()
        assert not populated_tree.objects.filter(desc="22").exists()
        assert not populated_tree.objects.filter(desc="21").exists()
        remaining = {n.desc for n in populated_tree.objects.all()}
        assert remaining == {"1", "3", "4", "41"}

    def test_deeply_nested_ancestor_descendant_dedup(self, populated_tree):
        populated_tree.objects.filter(desc__in=("23", "231")).delete()

        assert not populated_tree.objects.filter(desc="23").exists()
        assert not populated_tree.objects.filter(desc="231").exists()

        parent = populated_tree.objects.get(desc="2")
        assert parent.numchild == 3

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "21", "22", "24", "3", "4", "41"}
        assert remaining == expected


@pytest.mark.django_db
class TestMPNodeDeleteSiblings:
    def test_delete_two_siblings(self, populated_tree):
        parent = populated_tree.objects.get(desc="2")
        assert parent.numchild == 4

        populated_tree.objects.filter(desc__in=("21", "22")).delete()

        parent.refresh_from_db()
        assert parent.numchild == 2

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "23", "231", "24", "3", "4", "41"}
        assert remaining == expected

    def test_delete_all_siblings_under_parent(self, populated_tree):
        parent = populated_tree.objects.get(desc="2")
        assert parent.numchild == 4

        populated_tree.objects.filter(desc__in=("21", "22", "23", "24")).delete()

        parent.refresh_from_db()
        assert parent.numchild == 0

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "3", "4", "41"}
        assert remaining == expected

    def test_delete_single_sibling(self, populated_tree):
        parent = populated_tree.objects.get(desc="2")
        assert parent.numchild == 4

        populated_tree.objects.get(desc="22").delete()

        parent.refresh_from_db()
        assert parent.numchild == 3

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "2", "21", "23", "231", "24", "3", "4", "41"}
        assert remaining == expected

    def test_delete_siblings_numchild_never_negative(self, populated_tree):
        parent = populated_tree.objects.get(desc="2")
        parent.numchild = 3
        parent.save()

        populated_tree.objects.filter(desc__in=("21", "22", "23", "24")).delete()

        parent.refresh_from_db()
        assert parent.numchild == 0


@pytest.mark.django_db
class TestMPNodeDeleteCrossRoot:
    def test_delete_nodes_from_different_roots(self, populated_tree):
        populated_tree.objects.filter(desc__in=("1", "41")).delete()

        assert not populated_tree.objects.filter(desc="1").exists()
        assert not populated_tree.objects.filter(desc="41").exists()

        root4 = populated_tree.objects.get(desc="4")
        assert root4.numchild == 0

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"2", "21", "22", "23", "231", "24", "3", "4"}
        assert remaining == expected

    def test_delete_root_and_leaf_from_another_root(self, populated_tree):
        populated_tree.objects.filter(desc__in=("2", "41")).delete()

        assert not populated_tree.objects.filter(desc="2").exists()
        assert not populated_tree.objects.filter(path__startswith="002").exists()
        assert not populated_tree.objects.filter(desc="41").exists()

        root4 = populated_tree.objects.get(desc="4")
        assert root4.numchild == 0

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"1", "3", "4"}
        assert remaining == expected

    def test_delete_all_leaf_nodes_across_roots(self, populated_tree):
        leaf_descs = {"1", "21", "22", "231", "24", "3", "41"}
        populated_tree.objects.filter(desc__in=leaf_descs).delete()

        root2 = populated_tree.objects.get(desc="2")
        assert root2.numchild == 1

        root4 = populated_tree.objects.get(desc="4")
        assert root4.numchild == 0

        remaining = {n.desc for n in populated_tree.objects.all()}
        expected = {"2", "23", "4"}
        assert remaining == expected

    def test_delete_all_root_nodes(self, populated_tree):
        populated_tree.objects.filter(depth=1).delete()

        assert populated_tree.objects.count() == 0