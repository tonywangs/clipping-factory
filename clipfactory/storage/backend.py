from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import project_root


class ArtifactStorage(ABC):
    @abstractmethod
    def path(self, key: str) -> Path: ...

    @abstractmethod
    def put_file(self, source: Path, key: str) -> Path: ...

    @abstractmethod
    def move_prefix(self, from_key: str, to_key: str) -> None: ...


class LocalStorage(ArtifactStorage):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or project_root()

    def path(self, key: str) -> Path:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_file(self, source: Path, key: str) -> Path:
        target = self.path(key)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        return target

    def move_prefix(self, from_key: str, to_key: str) -> None:
        source, target = self.root / from_key, self.root / to_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))


class GCSStorage(ArtifactStorage):
    """GCS artifact implementation; local temporary paths remain caller-owned."""
    def __init__(self, bucket_name: str, root: Path | None = None) -> None:
        from google.cloud import storage
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.local = LocalStorage(root)

    def path(self, key: str) -> Path:
        return self.local.path(key)

    def put_file(self, source: Path, key: str) -> Path:
        self.bucket.blob(key).upload_from_filename(source)
        return source

    def move_prefix(self, from_key: str, to_key: str) -> None:
        for blob in self.client.list_blobs(self.bucket, prefix=from_key.rstrip("/") + "/"):
            target = self.bucket.blob(blob.name.replace(from_key.rstrip("/"), to_key.rstrip("/"), 1))
            self.bucket.copy_blob(blob, self.bucket, target.name)
            blob.delete()


def build_storage(backend: str, bucket: str | None = None) -> ArtifactStorage:
    if backend == "gcs":
        if not bucket:
            raise ValueError("GCS_BUCKET is required when STORAGE_BACKEND=gcs")
        return GCSStorage(bucket)
    return LocalStorage()
