from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatedFile:

    extension: str

    file_size: int