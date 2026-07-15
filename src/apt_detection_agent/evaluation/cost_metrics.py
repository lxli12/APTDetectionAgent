"""Runtime and token-cost accounting."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CostMetrics:
    runtime_seconds: float
    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        if min(self.runtime_seconds, self.prompt_tokens, self.completion_tokens) < 0:
            raise ValueError("cost values cannot be negative")

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)
