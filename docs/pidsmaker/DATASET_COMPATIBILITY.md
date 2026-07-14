# PIDSMaker dataset compatibility inventory

Requirements: REQ-PIDS-001..002, REQ-CAUSAL-001..004, REQ-EVAL-004.

The dynamic dataset source is `DATASET_DEFAULT_CONFIG` in
`PIDSMaker/pidsmaker/config/config.py:3-500`; CLI validation uses those keys at
`PIDSMaker/pidsmaker/config/pipeline.py:375-379`. Static presence means syntactic
pipeline registration, not verified model/checkpoint compatibility.

| Dataset | OS | Upstream size estimate | AutoDL dump observed 2026-07-14 |
|---|---|---:|---|
| CADETS_E3 | FreeBSD | 10 GB | yes |
| THEIA_E3 | Linux | 12 GB | yes |
| CLEARSCOPE_E3 | Android | 4.8 GB | yes |
| FIVEDIRECTIONS_E3 | Windows | 22 GB | yes |
| TRACE_E3 | Linux | 100 GB | no |
| CADETS_E5 | FreeBSD | 276 GB | no |
| THEIA_E5 | Linux | 36 GB | yes |
| CLEARSCOPE_E5 | Android | 49 GB | yes |
| FIVEDIRECTIONS_E5 | Windows | 280 GB | no |
| TRACE_E5 | Linux | 710 GB | no |
| optc_h201 | Windows | 9 GB | yes |
| optc_h501 | Windows | 6.7 GB | yes |
| optc_h051 | Windows | 7.7 GB | yes |
| ATLASV2_EDR | Windows | 1 GB | no |
| CARBANAKV2_EDR | Windows + Linux | 6.6 GB | no |

OS and upstream size evidence is `PIDSMaker/README.md:51-69`. The README and
`PIDSMaker/docs/docs/datasets.md:9-23` disagree on the FIVEDIRECTIONS OS label
(Windows versus Linux); registry inventory records this as an upstream documentation
conflict rather than choosing silently.

All PIDS × dataset pairs begin `unverified`. Availability becomes `available` only
after database mapping, causal configuration, checkpoint, and isolated smoke checks.
PIDSMaker ground-truth relative paths are not campaign IDs; the project campaign
manifest remains the evaluation source of truth.
