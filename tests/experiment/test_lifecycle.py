from apt_detection_agent.experiment import ExperimentRunner


def test_experiment_owns_agent_run_lifecycle(tmp_path):
    run_dir = ExperimentRunner(tmp_path).run("run-1", {"model": "fake"}, lambda _: {"ok": True})
    assert (run_dir / "config.yaml").is_file()
    assert '"completed"' in (run_dir / "status.json").read_text()
    assert (run_dir / "metrics" / "result.json").is_file()
