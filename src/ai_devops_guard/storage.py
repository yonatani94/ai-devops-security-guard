"""Bounded regular-file reads and private, exclusive writes in trusted directories."""

import os
import stat
from pathlib import Path


def read_regular(path: Path, limit: int = 1_048_576) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("expected regular file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file exceeds limit")
    return data


def write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
