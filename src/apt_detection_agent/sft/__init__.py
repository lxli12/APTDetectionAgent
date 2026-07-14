"""Canonical SFT dataset construction boundary.

Current implementation is demonstration-based. Legacy/frozen symbols are
temporarily re-exported for stored artifacts and old entrypoints only.
Requirements: REQ-SFT-001..010, REQ-LABEL-002..004.
"""

from .models import (
    CanonicalDemonstrationTrajectory, CoverageClass, DemonstrationDatasetManifest,
    DemonstrationExecutionMatrixRow, DemonstrationExchange, ExecutionDisposition,
    PublicOfflineRunRecord,
)
from .builder import (
    DemonstrationCorpusManifest, DemonstrationCorpusValidator,
    DemonstrationCoverageReport, build_coverage_report, build_dataset_manifest,
    build_execution_matrix, build_offline_run_record, build_trajectory, corpus_digest,
)
from .exporters import DemonstrationExporter, LossAwareMessage, OpenAICompatibleTrajectory
from .validators import DemonstrationSanitizer
from .datasets import load_trajectory_jsonl
# Compatibility surface for pre-demonstration artifacts. No new code may depend on it.
from .compat.contracts import SFTDataset, SFTDatasetManifest, SFTDatasetValidator, StudentSFTExample
from .compat.sanitizer import SFTSanitizer
from .compat.teacher import HiddenTeacherRecord
from .compat.frozen_contracts import (
    FrozenSFTDataset, FrozenSFTDatasetManifest, FrozenSFTDatasetValidator,
    FrozenStudentSFTExample,
)
from .compat.frozen_sanitizer import FrozenSFTSanitizer
from .compat.frozen_teacher import FrozenHiddenTeacherRecord

__all__ = [name for name in globals() if not name.startswith("_")]
