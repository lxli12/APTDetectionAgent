# PIDSMaker model inventory

Requirements: REQ-PIDS-001..005, REQ-ARTIFACT-002, REQ-CAUSAL-004.
Baseline: commit `32602734bc9f896be5fc0f03f0a185c967cd6624`.

The executable registry is discovered from top-level YAML files in
`PIDSMaker/config/`; `default.yml` and `tests.yml` are framework/test templates, not
PIDS entries. Discovery also cross-checks `PIDSMaker/README.md`,
`PIDSMaker/tests/test_framework.py`, config inheritance, and the pipeline source.

| source_config_id | Registry identity | Detection unit | Causality classification | Threshold semantics | Current checkpoint status |
|---|---|---|---|---|---|
| `flash` | `(flash, default)` | node | causal candidate | `flash` | unavailable |
| `kairos` | `(kairos, default)` | node | compatibility baseline | `max_val_loss` | unavailable |
| `magic` | `(magic, default)` | node | causal candidate | `magic` | unavailable |
| `nodlink` | `(nodlink, default)` | node | causal candidate | `nodlink` | unavailable |
| `orthrus` | `(orthrus, default)` | node | compatibility baseline | `max_val_loss` | unavailable |
| `orthrus_fixed` | `(orthrus, fixed)` | edge | causal candidate | `max_val_loss` | unavailable |
| `orthrus_non_snooped` | `(orthrus, non_snooped)` | node | causal candidate | `max_val_loss` | unavailable |
| `rcaid` | `(rcaid, default)` | node | compatibility baseline | `max_val_loss` | unavailable |
| `threatrace` | `(threatrace, default)` | node | causal candidate | `threatrace` | unavailable |
| `velox` | `(velox, default)` | node | causal candidate | frozen validation calibration | available for bounded `CADETS_E3` validation only |

Evidence:

- Canonical systems: `PIDSMaker/README.md:34-49`.
- Test list includes the non-snooped config: `PIDSMaker/tests/test_framework.py:270-280`.
- Fixed and non-snooped inheritance is declared in
  `PIDSMaker/config/orthrus_fixed.yml:1` and
  `PIDSMaker/config/orthrus_non_snooped.yml:4`.
- Original ORTHRUS uses all-split embedding fit and test-score clustering:
  `PIDSMaker/config/orthrus.yml:21,100-102`.
- R-CAID fits Doc2Vec on `all`: `PIDSMaker/config/rcaid.yml:22`.
- KAIROS fits hierarchical hashing on `all`:
  `PIDSMaker/config/kairos.yml:18`.
- Non-snooped ORTHRUS changes fit to train and disables clustering:
  `PIDSMaker/config/orthrus_non_snooped.yml:7,17`.

“Causal candidate” means the static config does not expose the audited snooping
patterns; it is not an ApprovedConfig until window alignment, fitted-state freeze,
checkpoint, dataset, and smoke validation pass. All ten entries remain in
`allowed_pids`; unavailable entries are never silently removed.

The VELOX promotion is backed by
`/root/autodl-tmp/apt-agent/experiments/runs/phase8-velox-cadets-smoke-20260714-002`
and the frozen bundle
`/root/autodl-tmp/apt-agent/pre-sft-bundles/velox-cadets-validation-3fa5ec0-002`.
Its checkpoint hash is
`9fd5b64fd65f71faea65b037294dca537c75ab902a4ad92f04bb84315c0f54a2`;
new-window frozen inference evidence is in
`phase10-frozen-new-window-20260714-001`. This does not approve VELOX for held-out,
deployment, or any other dataset. No status for the other nine entries changes.
