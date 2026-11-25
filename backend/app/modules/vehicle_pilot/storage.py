import hashlib
import os
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.core.config import get_settings

_MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAGIC = {
    "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
    "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda value: len(value) >= 12 and value[:4] == b"RIFF" and value[8:12] == b"WEBP",
}


class EvidenceStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or get_settings().pilot_evidence_root).expanduser().resolve()

    def object_key(self, facility_id: int, visit_id: UUID, evidence_id: UUID, content_type: str) -> str:
        ext = _MIME_EXT.get(content_type)
        if ext is None:
            raise HTTPException(415, "Chỉ nhận ảnh JPEG, PNG hoặc WebP.")
        return f"{facility_id}/{visit_id}/{evidence_id}{ext}"

    def validate(self, body: bytes, content_type: str) -> str:
        settings = get_settings()
        if content_type not in _MIME_EXT or not _MAGIC[content_type](body):
            raise HTTPException(415, "Loại ảnh không hợp lệ hoặc không khớp nội dung.")
        if not body or len(body) > settings.pilot_evidence_max_file_bytes:
            raise HTTPException(413, "Ảnh rỗng hoặc vượt giới hạn kích thước.")
        return hashlib.sha256(body).hexdigest()

    def path(self, key: str) -> Path:
        # Keys are produced from UUIDs and a MIME-derived suffix, never client filenames.
        candidate = (self.root / key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Evidence key escapes configured root")
        return candidate

    def write(self, key: str, body: bytes, sha256: str) -> Path:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.parent.chmod(0o700)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
                raise HTTPException(409, "Tệp bằng chứng tồn tại nhưng khác nội dung; cần đối soát.")
            return target
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            target.chmod(0o600)
            return target
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        path = self.path(key)
        return path.read_bytes()

    def delete(self, key: str) -> bool:
        path = self.path(key)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def free_bytes(self) -> int:
        probe = self.root
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return shutil.disk_usage(probe).free
