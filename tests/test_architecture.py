"""Repository-level checks for the frozen v1.2 boundaries."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pidsmaker_is_only_a_submodule_boundary():
    assert (ROOT / "PIDSMaker" / ".git").is_file()
    assert not (ROOT / "src" / "apt_detection_agent" / "pidsmaker").exists()
    assert (ROOT / "src" / "apt_detection_agent" / "pidsmaker_adapter").is_dir()


def test_runtime_data_is_external_to_repository():
    assert not (ROOT / "data").exists()


def test_prompt_assets_are_plain_text():
    prompt_assets = [
        path
        for path in (ROOT / "prompts").rglob("*")
        if path.is_file() and not path.name.startswith(".")
    ]
    assert all(path.suffix == ".txt" or path.name == "README.md" for path in prompt_assets)


def test_sft_is_reserved_without_python_implementation():
    assert not list((ROOT / "src" / "apt_detection_agent" / "sft").glob("*.py"))


def test_no_legacy_duplicate_source_domains():
    package = ROOT / "src" / "apt_detection_agent"
    for legacy_name in ("runtime", "tooling", "pidsmaker", "evaluator", "training"):
        assert not (package / legacy_name).exists()
