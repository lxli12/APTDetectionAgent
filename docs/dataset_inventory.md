# Dataset inventory and experiment-selection gate

Requirements: REQ-PIDS-001..002, REQ-CAUSAL-001..004, REQ-EVAL-004..005,
REQ-DB-001..003, REQ-REPRO-001.

Baseline date: 2026-07-14. Static registration comes from
`PIDSMaker/pidsmaker/config/config.py`; upstream OS and nominal-size evidence comes
from `PIDSMaker/README.md` and `PIDSMaker/docs/docs/datasets.md`. AutoDL facts were
measured read-only. A dump file is backup/input evidence, not proof of a restored,
queryable database. No row below is an approved train/validation/held-out split.

| Dataset | OS / schema family | Registered PIDS | Upstream date range | AutoDL dump | Queryable PostgreSQL DB | Checkpoint | Ground truth / campaign status | Runtime and availability status |
|---|---|---|---|---|---|---|---|---|
| `CADETS_E3` | FreeBSD / DARPA TC E3 CDM | all 10 registered; VELOX bounded validation verified | 2018-04-02..14 | `cadets_e3.dump`, ~1.36 GiB | `cadets_e3`, ~9.8 GiB | VELOX validation checkpoint frozen; others absent | private validation campaign manifest exercised; full campaign inventory pending | VELOX 15-minute causal/new-window smoke passed; no held-out approval |
| `THEIA_E3` | Linux / DARPA TC E3 CDM | all 10, unverified | 2018-04-02..14 | `theia_e3.dump`, ~1.05 GiB | `theia_e3`, ~12 GiB | none found | upstream CSV references only; campaign manifest pending | data present; runtime unprofiled |
| `CLEARSCOPE_E3` | Android / DARPA TC E3 CDM | all 10, unverified | 2018-04-02..14 | `clearscope_e3.dump`, ~588 MiB | `clearscope_e3`, ~4.6 GiB | none found | upstream CSV references only; documented exclusions require review | data present; runtime unprofiled |
| `FIVEDIRECTIONS_E3` | upstream docs conflict: Windows vs Linux / DARPA TC E3 | all 10, unverified | 2018-04-02..14 | `fivedirections_e3.dump`, ~3.0 GiB | absent | none found | upstream CSV references only; campaign manifest pending | unavailable until DB is provisioned by an approved operation |
| `TRACE_E3` | Linux / DARPA TC E3 CDM | all 10, unverified | 2018-04-02..14 | absent | absent | none found | upstream CSV references only | unavailable: data and DB absent |
| `CADETS_E5` | FreeBSD / DARPA TC E5 CDM | all 10, unverified | 2019-05-08..18 | absent | absent | none found | upstream CSV references only | unavailable: data and DB absent |
| `THEIA_E5` | Linux / DARPA TC E5 CDM | all 10, unverified | 2019-05-08..18 | `theia_e5.dump`, ~5.8 GiB | absent | none found | upstream CSV references only | dump present, DB absent |
| `CLEARSCOPE_E5` | Android / DARPA TC E5 CDM | all 10, unverified | 2019-05-08..18 | `clearscope_e5.dump`, ~6.2 GiB | `clearscope_e5`, ~49 GiB | none found | upstream CSV references and exclusions require campaign review | data present; high-size candidate, runtime unprofiled |
| `FIVEDIRECTIONS_E5` | upstream docs conflict: Windows vs Linux / DARPA TC E5 | all 10, unverified | 2019-05-08..18 | absent | absent | none found | upstream CSV references only | unavailable: data and DB absent |
| `TRACE_E5` | Linux / DARPA TC E5 CDM | all 10, unverified | 2019-05-08..18 | absent | absent | none found | upstream CSV references only | unavailable: data and DB absent |
| `optc_h201` | Windows / OpTC | all 10, unverified | 2019-09-15..26 | `optc_h201.dump`, ~1.9 GiB | `optc_h201`, ~8.7 GiB, but upstream config requests `optc_201` | none found | upstream CSV references only; campaign manifest pending | unavailable until dataset-to-database mapping is approved/fixed |
| `optc_h501` | Windows / OpTC | all 10, unverified | 2019-09-15..26 | `optc_h501.dump`, ~1.5 GiB | absent | none found | upstream CSV references only | dump present, DB absent; upstream requests `optc_501` |
| `optc_h051` | Windows / OpTC | all 10, unverified | 2019-09-15..26 | `optc_h051.dump`, ~1.7 GiB | absent | none found | upstream CSV references only | dump present, DB absent; upstream requests `optc_051` |
| `ATLASV2_EDR` | Windows / EDR schema | all 10, unverified | 2022-07-15..21 | absent | absent | none found | upstream config metadata only | unavailable: data and DB absent |
| `CARBANAKV2_EDR` | Windows + Linux / EDR schema | all 10, unverified | 2024-04-18..2024-05-13 | absent | absent | none found | upstream config metadata only | unavailable: data and DB absent |

The “all 10” value means only that the pinned CLI/config mechanism accepts the
dataset for each discovered source config; it is not a compatibility claim. The ten
entries and variants are listed in `docs/pidsmaker/MODEL_INVENTORY.md`, while actual
availability remains gated by a causal ApprovedConfig, a checkpoint, a database
mapping, and an independent smoke profile.

## Split and OOD decision gate

1. First define strict chronological train/validation/held-out ranges inside one
   dataset using project-owned `[start,end)` windows. Upstream date lists in
   `PIDSMaker/pidsmaker/config/config.py` are evidence, not automatically approved
   splits.
2. Build versioned campaign manifests outside the Agent-visible filesystem. A
   `ground_truth_relative_path` entry is never a campaign ID.
3. Smoke every candidate PIDS independently and record checkpoint format, peak RAM,
   peak VRAM, latency, output unit, threshold semantics, and failure status.
4. Only after those checks select leave-one-dataset or leave-one-OS/schema-out OOD
   experiments. No concrete OOD target is frozen by this inventory.

## Current AutoDL evidence and remaining work

- Historical inventory found no usable PIDS checkpoint. The project subsequently
  produced a causal VELOX validation checkpoint and froze it under
  `/root/autodl-tmp/apt-agent/pre-sft-bundles/velox-cadets-validation-3fa5ec0-002`.
  It is a new project artifact, not an upstream pretrained checkpoint.
- The measured dataset-to-database mapping is versioned in
  `configs/database/autodl.yaml`. Role provisioning and live verification use
  `scripts/postgres/provision_roles.sh` and `verify_role_policy.sh`; acceptance
  status is recorded in the Phase 8 report rather than inferred from this inventory.
- VELOX now has one bounded latency/VRAM smoke. Every other PIDS/dataset pair still
  requires an independent profile; host-visible resources may not replace the
  project quota in `configs/resource_profiles/autodl.yaml`.
