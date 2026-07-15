"""Safe loader for plain-text prompt templates."""

from pathlib import Path


class PromptLoader:
    def __init__(self, prompt_root: Path) -> None:
        self.prompt_root = prompt_root.resolve()

    def load(self, relative_path: str) -> str:
        requested = Path(relative_path)
        if requested.suffix != ".txt" or requested.is_absolute():
            raise ValueError("prompts must be relative .txt files")
        path = (self.prompt_root / requested).resolve()
        if path == self.prompt_root or self.prompt_root not in path.parents:
            raise ValueError("prompt path escapes prompt root")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")
