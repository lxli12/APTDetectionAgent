from apt_detection_agent.evaluation import compute_detection_metrics


def test_detection_metrics():
    metrics = compute_detection_metrics({"a", "b"}, {"b", "c"})
    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.precision == 0.5
    assert metrics.coverage == 0.5
