from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "remote_smoke_check.py"
SPEC = spec_from_file_location("remote_smoke_check", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_snapshot_validator_reports_every_bootstrap_boundary():
    snapshot = {
        "repository": {
            "commit": "parent",
            "origin_main_commit": "origin",
            "clean": False,
            "pidsmaker_expected_tree_entry": "160000 commit expected PIDSMaker",
            "pidsmaker_commit": "actual",
        },
        "runtime": {
            "pidsmaker": {"ok": False},
            "torch": {"cuda_available": False, "gpu_count": 0},
        },
        "storage": {"required_directories": {"pidsmaker/cache": False}},
    }

    failures = MODULE.validate_snapshot(snapshot)

    assert len(failures) == 6
    assert any("origin/main" in failure for failure in failures)
    assert any("PIDSMaker" in failure for failure in failures)
    assert any("CUDA" in failure for failure in failures)


def test_required_runtime_paths_are_external_data_disk_paths():
    assert MODULE.REQUIRED_DATA_DIRECTORIES
    assert all(not Path(relative).is_absolute() for relative in MODULE.REQUIRED_DATA_DIRECTORIES)
    assert not any(relative.startswith("../") for relative in MODULE.REQUIRED_DATA_DIRECTORIES)
