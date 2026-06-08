import pytest
from tests.models import MP_TestNode

@pytest.fixture
def mp_tree():
    """
    Build a tree structure for testing delete operations:
    root1 (depth 1, numchild 2)
      - child1 (depth 2, numchild 2)
        - leaf1 (depth 3, numchild 0)
        - leaf2 (depth 3, numchild 0)
      - child2 (depth 2, numchild 1)
        - leaf3 (depth 3, numchild 0)
    root2 (depth 1, numchild 1)
      - child3 (depth 2, numchild 1)
        - leaf4 (depth 3, numchild 0)
    root3 (depth 1, numchild 0)
    """
    MP_TestNode.objects.all().delete()
    
    root1 = MP_TestNode.add_root(desc="root1")
    child1 = root1.add_child(desc="child1")
    leaf1 = child1.add_child(desc="leaf1")
    leaf2 = child1.add_child(desc="leaf2")
    
    child2 = root1.add_child(desc="child2")
    leaf3 = child2.add_child(desc="leaf3")
    
    root2 = MP_TestNode.add_root(desc="root2")
    child3 = root2.add_child(desc="child3")
    leaf4 = child3.add_child(desc="leaf4")

    root3 = MP_TestNode.add_root(desc="root3")
    
    # Reload from db to ensure properties like numchild are updated correctly
    return {
        "root1": MP_TestNode.objects.get(pk=root1.pk),
        "child1": MP_TestNode.objects.get(pk=child1.pk),
        "leaf1": MP_TestNode.objects.get(pk=leaf1.pk),
        "leaf2": MP_TestNode.objects.get(pk=leaf2.pk),
        "child2": MP_TestNode.objects.get(pk=child2.pk),
        "leaf3": MP_TestNode.objects.get(pk=leaf3.pk),
        "root2": MP_TestNode.objects.get(pk=root2.pk),
        "child3": MP_TestNode.objects.get(pk=child3.pk),
        "leaf4": MP_TestNode.objects.get(pk=leaf4.pk),
        "root3": MP_TestNode.objects.get(pk=root3.pk),
    }

@pytest.mark.django_db
class TestMPNodeQuerySetDelete:

    def test_delete_single_leaf(self, mp_tree):
        # 1. 删除单个叶子节点
        leaf1 = mp_tree["leaf1"]
        
        MP_TestNode.objects.filter(pk=leaf1.pk).delete()
        
        # 验证 leaf1 被删除
        assert not MP_TestNode.objects.filter(pk=leaf1.pk).exists()
        
        # 验证 child1 的 numchild 从 2 减少到 1
        child1 = MP_TestNode.objects.get(pk=mp_tree["child1"].pk)
        assert child1.numchild == 1
        assert child1.depth == 2
        
        # 验证 child1 仍包含 leaf2
        assert MP_TestNode.objects.filter(pk=mp_tree["leaf2"].pk).exists()

    def test_delete_non_leaf_with_subtrees(self, mp_tree):
        # 2. 删除包含多个子树的非叶子节点
        child1 = mp_tree["child1"]
        
        MP_TestNode.objects.filter(pk=child1.pk).delete()
        
        # 验证 child1 及其后代被删除
        assert not MP_TestNode.objects.filter(pk=child1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf1"].pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf2"].pk).exists()
        
        # 验证 root1 的 numchild 从 2 减少到 1
        root1 = MP_TestNode.objects.get(pk=mp_tree["root1"].pk)
        assert root1.numchild == 1
        assert root1.depth == 1
        
        # 验证其他分支不受影响
        assert MP_TestNode.objects.filter(pk=mp_tree["child2"].pk).exists()

    def test_delete_ancestor_descendant_overlap(self, mp_tree):
        # 3. 同时删除存在祖先-后代关系的多个节点（验证去重逻辑）
        root1 = mp_tree["root1"]
        child1 = mp_tree["child1"]
        leaf1 = mp_tree["leaf1"]
        
        # 构造包含祖先后代的 QuerySet
        qs = MP_TestNode.objects.filter(pk__in=[root1.pk, child1.pk, leaf1.pk])
        qs.delete()
        
        # 验证 root1 及其所有后代均被删除
        assert not MP_TestNode.objects.filter(pk=root1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=child1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=leaf1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf2"].pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["child2"].pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf3"].pk).exists()
        
        # 验证 root2 等其他根节点不受影响
        root2 = MP_TestNode.objects.get(pk=mp_tree["root2"].pk)
        assert root2.depth == 1
        assert root2.numchild == 1
        
        # 由于删除的是根节点，不涉及父节点的 numchild 更新（根节点没有父节点）
        # 验证剩余的根节点数量
        assert MP_TestNode.get_root_nodes().count() == 2

    def test_delete_multiple_siblings(self, mp_tree):
        # 4. 删除同一父节点下的多个兄弟节点（验证 numchild 递减的准确性）
        leaf1 = mp_tree["leaf1"]
        leaf2 = mp_tree["leaf2"]
        
        # child1 本来有 2 个子节点
        qs = MP_TestNode.objects.filter(pk__in=[leaf1.pk, leaf2.pk])
        qs.delete()
        
        # 验证 leaf1, leaf2 被删除
        assert not MP_TestNode.objects.filter(pk=leaf1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=leaf2.pk).exists()
        
        # 验证 child1 的 numchild 正确递减到 0
        child1 = MP_TestNode.objects.get(pk=mp_tree["child1"].pk)
        assert child1.numchild == 0
        assert child1.depth == 2

    def test_delete_across_multiple_roots(self, mp_tree):
        # 5. 删除跨多个根节点的节点集合
        child1 = mp_tree["child1"]
        leaf4 = mp_tree["leaf4"]
        root3 = mp_tree["root3"]
        
        qs = MP_TestNode.objects.filter(pk__in=[child1.pk, leaf4.pk, root3.pk])
        qs.delete()
        
        # 验证跨树节点删除
        assert not MP_TestNode.objects.filter(pk=child1.pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf1"].pk).exists()
        assert not MP_TestNode.objects.filter(pk=mp_tree["leaf2"].pk).exists()
        assert not MP_TestNode.objects.filter(pk=leaf4.pk).exists()
        assert not MP_TestNode.objects.filter(pk=root3.pk).exists()
        
        # 验证各父节点的 numchild 更新
        root1 = MP_TestNode.objects.get(pk=mp_tree["root1"].pk)
        assert root1.numchild == 1  # 失去 child1，只剩 child2
        
        child3 = MP_TestNode.objects.get(pk=mp_tree["child3"].pk)
        assert child3.numchild == 0  # 失去 leaf4
        
        root2 = MP_TestNode.objects.get(pk=mp_tree["root2"].pk)
        assert root2.numchild == 1  # child3 仍然存在

