from pathlib import Path

from .exceptions import StorageNotFound
from .ports import Storage


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if path == self._root or self._root not in path.parents:
            raise ValueError(f"key escapes storage root: {key!r}")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageNotFound(key)
        return path.read_bytes()

    def list(self, prefix: str) -> list[str]:
        base = self._resolve(prefix)
        if not base.is_dir():
            return []
        return [
            str(p.relative_to(self._root)) for p in sorted(base.rglob("*")) if p.is_file()
        ]

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def local_path(self, key: str) -> str:
        return str(self._resolve(key))
