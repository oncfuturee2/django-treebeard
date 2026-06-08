"""
专门测试 MP_NodeQuerySet.delete 方法的测试用例
覆盖各种删除场景，包括祖先-后代去重和 numchild 更新
"""

import pytest
from django.db import models

from tests import models as test_models
from treebeard.mp_tree import MP_Node


@pytest.mark.django_db
class TestMPQuerySetDelete:
    """测试 MP_NodeQuerySet.delete 方法的各种场景"""

    @pytest.fixture
    def mp_model(self):
        """加载测试数据的 fixture"""
        test_models.MP_TestNode.load_bulk([
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
        ])
        return test_models.MP_TestNode

    def _verify_tree_state(self, model, expected_nodes):
        """验证树的状态是否符合预期"""
        got = [(o.desc, o.get_depth(), o.get_children_count()) for o in model.get_tree()]
        assert got == expected_nodes

    def _verify_no_problems(self, model):
        """验证树没有结构问题"""
        problems = model.find_problems()
        assert not any(problems), f"树有问题: {problems}"

    def test_delete_single_leaf_node(self, mp_model):
        """测试删除单个叶子节点"""
        node = mp_model.objects.get(desc="231")
        mp_model.objects.filter(pk=node.pk).delete()

        expected = [
            ("1", 1, 0),
            ("2", 1, 4),
            ("21", 2, 0),
            ("22", 2, 0),
            ("23", 2, 0),
            ("24", 2, 0),
            ("3", 1, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

        # 验证父节点的 numchild
        parent_node = mp_model.objects.get(desc="23")
        assert parent_node.numchild == 0

    def test_delete_non_leaf_node_with_subtree(self, mp_model):
        """测试删除包含多个子树的非叶子节点"""
        node = mp_model.objects.get(desc="2")
        mp_model.objects.filter(pk=node.pk).delete()

        expected = [
            ("1", 1, 0),
            ("3", 1, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

    def test_delete_ancestor_descendant_duplicates(self, mp_model):
        """测试同时删除存在祖先-后代关系的多个节点（验证去重逻辑）"""
        # 获取需要删除的节点：祖先 "2" 和其后代 "23"、"231"
        node2 = mp_model.objects.get(desc="2")
        node23 = mp_model.objects.get(desc="23")
        node231 = mp_model.objects.get(desc="231")

        # 删除这些节点
        mp_model.objects.filter(pk__in=[node2.pk, node23.pk, node231.pk]).delete()

        expected = [
            ("1", 1, 0),
            ("3", 1, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

    def test_delete_multiple_siblings(self, mp_model):
        """测试删除同一父节点下的多个兄弟节点（验证 numchild 递减的准确性）"""
        # 获取节点 21、22、24（都是节点 2 的子节点）
        node21 = mp_model.objects.get(desc="21")
        node22 = mp_model.objects.get(desc="22")
        node24 = mp_model.objects.get(desc="24")

        # 删除这三个兄弟节点
        mp_model.objects.filter(pk__in=[node21.pk, node22.pk, node24.pk]).delete()

        expected = [
            ("1", 1, 0),
            ("2", 1, 1),
            ("23", 2, 1),
            ("231", 3, 0),
            ("3", 1, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

        # 验证父节点的 numchild 是否正确递减
        parent_node = mp_model.objects.get(desc="2")
        assert parent_node.numchild == 1

    def test_delete_across_multiple_roots(self, mp_model):
        """测试删除跨多个根节点的节点集合"""
        # 获取根节点 1、3 和 41（4 的子节点）
        node1 = mp_model.objects.get(desc="1")
        node3 = mp_model.objects.get(desc="3")
        node41 = mp_model.objects.get(desc="41")

        # 删除这些节点
        mp_model.objects.filter(pk__in=[node1.pk, node3.pk, node41.pk]).delete()

        expected = [
            ("2", 1, 4),
            ("21", 2, 0),
            ("22", 2, 0),
            ("23", 2, 1),
            ("231", 3, 0),
            ("24", 2, 0),
            ("4", 1, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

        # 验证根节点 4 的 numchild 是否正确更新
        node4 = mp_model.objects.get(desc="4")
        assert node4.numchild == 0

    def test_delete_mixed_leaves_and_branches(self, mp_model):
        """测试同时删除叶子节点和分支节点"""
        # 获取节点 1（叶子）、23（分支）、3（叶子）
        node1 = mp_model.objects.get(desc="1")
        node23 = mp_model.objects.get(desc="23")
        node3 = mp_model.objects.get(desc="3")

        # 删除这些节点
        mp_model.objects.filter(pk__in=[node1.pk, node23.pk, node3.pk]).delete()

        expected = [
            ("2", 1, 3),
            ("21", 2, 0),
            ("22", 2, 0),
            ("24", 2, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ]
        self._verify_tree_state(mp_model, expected)
        self._verify_no_problems(mp_model)

        # 验证父节点的 numchild
        node2 = mp_model.objects.get(desc="2")
        assert node2.numchild == 3

    def test_delete_with_empty_queryset(self, mp_model):
        """测试删除空查询集（无操作）"""
        result = mp_model.objects.filter(desc="nonexistent").delete()
        assert result[0] == 0, "不应该删除任何内容"
        self._verify_no_problems(mp_model)
        self._verify_tree_state(mp_model, [
            ("1", 1, 0),
            ("2", 1, 4),
            ("21", 2, 0),
            ("22", 2, 0),
            ("23", 2, 1),
            ("231", 3, 0),
            ("24", 2, 0),
            ("3", 1, 0),
            ("4", 1, 1),
            ("41", 2, 0),
        ])

    def test_delete_all_nodes(self, mp_model):
        """测试删除所有节点"""
        mp_model.objects.all().delete()
        assert mp_model.objects.count() == 0, "所有节点应该被删除"
        self._verify_no_problems(mp_model)
