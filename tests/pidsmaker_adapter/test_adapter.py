import pytest

from apt_detection_agent.pidsmaker_adapter import (
    AdmissionPolicy, PIDSMakerAdapter, default_registry,
)
from apt_detection_agent.pidsmaker_adapter.admission import Admission


def test_adapter_requires_exact_admission():
    calls = []

    def runner(detector, config, dataset, parameters):
        calls.append((detector, config, dataset, parameters))
        return {"status": "succeeded", "alerts": [{"entity": "n1"}], "scores": [0.9]}

    adapter = PIDSMakerAdapter(
        default_registry(),
        AdmissionPolicy((Admission("VELOX", "velox", "darpa"),)),
        runner,
    )
    with pytest.raises(PermissionError):
        adapter.run("VELOX", "velox", "other", {})
    result = adapter.run("VELOX", "velox", "darpa", {"window": "w1"})
    assert result.detector == "VELOX"
    assert len(result.alerts) == 1
    assert calls == [("VELOX", "velox", "darpa", {"window": "w1"})]
