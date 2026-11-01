"""Single-process JSONL writer; an audit failure aborts the caller."""

import os
from pathlib import Path

from ai_devops_guard.models import AuditEvent


class AuditError(RuntimeError):
    pass


class AuditWriter:
    """Create a fresh private log; never overwrite or follow an existing file."""

    def __init__(self, path: Path):
        try:
            self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError:
            raise AuditError("cannot create audit log") from None

    def write(self, event: AuditEvent) -> None:
        if self._fd is None:
            raise AuditError("audit log is closed")
        data = (event.model_dump_json() + "\n").encode()
        try:
            while data:
                written = os.write(self._fd, data)
                if written == 0:
                    raise OSError("short write")
                data = data[written:]
            os.fsync(self._fd)
        except OSError:
            raise AuditError("cannot persist audit event") from None

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
