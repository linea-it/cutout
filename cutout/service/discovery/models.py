from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileDescriptor:
    tile_id: str
    archive_path: str
    file_path: Path | None
    band: str | None
