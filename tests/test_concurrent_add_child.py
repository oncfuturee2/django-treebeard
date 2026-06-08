import pytest
from tests.models import MP_TestNodeSorted
import threading
import time

@pytest.mark.django_db(transaction=True)
def test_concurrent_add_child_sorted():
    # Clear the DB
    MP_TestNodeSorted.objects.all().delete()
    
    # Create root
    root = MP_TestNodeSorted.add_root(val1=1, val2=1)
    
    # Add a first child so node_order_by branch is hit
    child1 = root.add_child(val1=2, val2=2)
    
    # Verify root numchild is 1
    assert root.numchild == 1
    assert MP_TestNodeSorted.objects.get(pk=root.pk).numchild == 1

    # We want to simulate concurrency. 
    # Thread 1 starts add_child, acquires lock, pauses before add_sibling.
    # Thread 2 starts add_child, waits for lock.
    # We can use mock/patch to inject a sleep in add_sibling.
    
    import unittest.mock as mock

    original_add_sibling = MP_TestNodeSorted.add_sibling
    
    def mocked_add_sibling(self, pos=None, **kwargs):
        # Sleep to let Thread 2 acquire stale `self.node` and wait for lock
        time.sleep(0.5)
        return original_add_sibling(self, pos, **kwargs)

    # We need thread 1 to run the mocked version, thread 2 to run the normal version? 
    # Actually, both can run the mocked version, it doesn't matter.
    
    root_thread1 = MP_TestNodeSorted.objects.get(pk=root.pk)
    root_thread2 = MP_TestNodeSorted.objects.get(pk=root.pk)
    
    results = {}
    
    def thread1_func():
        try:
            with mock.patch('treebeard.mp_tree.MP_Node.add_sibling', new=mocked_add_sibling):
                root_thread1.add_child(val1=3, val2=3)
            results['t1'] = root_thread1.numchild
        except Exception as e:
            results['t1_err'] = e

    def thread2_func():
        try:
            time.sleep(0.1) # Ensure thread 1 acquires the lock first
            root_thread2.add_child(val1=4, val2=4)
            results['t2'] = root_thread2.numchild
        except Exception as e:
            results['t2_err'] = e

    t1 = threading.Thread(target=thread1_func)
    t2 = threading.Thread(target=thread2_func)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    db_root = MP_TestNodeSorted.objects.get(pk=root.pk)
    
    print(f"DB numchild: {db_root.numchild}")
    print(f"Thread 1 numchild: {results.get('t1')}")
    print(f"Thread 2 numchild: {results.get('t2')}")

    # They should both reflect the correct count at the end, or at least Thread 2 should.
    # Actually, Thread 2's root_thread2.numchild will be 2 instead of 3.
    if 't1_err' in results:
        print("T1 Error:", results['t1_err'])
    if 't2_err' in results:
        print("T2 Error:", results['t2_err'])
