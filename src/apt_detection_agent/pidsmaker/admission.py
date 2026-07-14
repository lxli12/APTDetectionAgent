"""PIDSMaker admission service separated from exchange schemas.

Requirements: REQ-PIDS-006, REQ-CAUSAL-002..004, REQ-LABEL-001..004.
"""

from apt_detection_agent.schemas import AdmittedUse, DataSplit, PIDSAdmissionRecord, PIDSRef


class PIDSAdmissionRegistry:
    def __init__(self, records: tuple[PIDSAdmissionRecord, ...]) -> None:
        self.records = {item.admission_id: item for item in records}
        if len(self.records) != len(records):
            raise ValueError("duplicate PIDS admission identity")

    def require_exact(
        self,
        *,
        admission_id: str | None,
        pids: PIDSRef,
        scenario_id: str,
        split: DataSplit,
        admitted_use: AdmittedUse,
    ) -> PIDSAdmissionRecord:
        record = self.records.get(str(admission_id))
        if not record or (
            not record.admitted_for_formal_trajectory
            or record.pids != pids
            or record.dataset_or_scenario_id != scenario_id
            or record.split != split
            or admitted_use not in record.admitted_uses
        ):
            raise ValueError("candidate availability exceeds scoped admission")
        return record
