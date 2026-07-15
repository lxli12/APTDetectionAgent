# APTDetectionAgent

APTDetectionAgent is an LLM-based orchestration layer for long-horizon APT
detection. It uses the pinned `PIDSMaker/` git submodule only through a typed
adapter and does not modify, duplicate, or manage PIDSMaker internals.

The frozen repository architecture is documented in
[`docs/architecture/PROJECT_ARCHITECTURE_DESIGN_v1.1.md`](docs/architecture/PROJECT_ARCHITECTURE_DESIGN_v1.1.md).

## Development

```bash
python -m pip install -e '.[dev]'
pytest
```

Generated datasets, checkpoints, and run outputs are local-only. Prompt templates
are plain `.txt` files under `prompts/`.
