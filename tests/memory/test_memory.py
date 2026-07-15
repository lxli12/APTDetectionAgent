from datetime import datetime, timedelta, timezone

from apt_detection_agent.memory import InMemoryStore, MemoryManager
from apt_detection_agent.schemas import MemoryQuery, MemoryRecord


def test_memory_is_namespaced_ranked_and_reset():
    manager = MemoryManager(InMemoryStore())
    now = datetime.now(timezone.utc)
    manager.remember(MemoryRecord("m1", "case-a", "velox anomaly", ("e1",), now))
    manager.remember(MemoryRecord("m2", "case-a", "orthurs context", ("e2",), now + timedelta(seconds=1)))
    manager.remember(MemoryRecord("m3", "case-b", "velox private", ("e3",), now))
    result = manager.recall(MemoryQuery("case-a", "velox", limit=1))
    assert tuple(item.memory_id for item in result) == ("m1",)
    assert manager.reset("case-a") == 2
    assert manager.recall(MemoryQuery("case-a", "velox")) == ()
