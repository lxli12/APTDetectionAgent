from datetime import timedelta

from apt_detection_agent.memory import InMemoryStore, MemoryManager
from apt_detection_agent.schemas import MemoryQuery
from tests.test_contracts import NOW, memory_record


def test_memory_is_namespaced_ranked_and_reset():
    manager = MemoryManager(InMemoryStore())
    manager.remember(memory_record("m1", "case-a", NOW))
    manager.remember(memory_record("m2", "case-a", NOW + timedelta(seconds=1)))
    manager.remember(memory_record("m3", "case-b", NOW))
    query = MemoryQuery("case-a", "FreeBSD", "CDM18", "ORTHRUS", ("persistent_tail",), (), 1)
    result = manager.recall(query)
    assert tuple(item.memory_id for item in result) == ("m2",)
    assert manager.reset("case-a") == 2
    assert manager.recall(query) == ()
