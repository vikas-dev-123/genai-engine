"""Per-user FAISS index + JSON metadata on disk, safe for concurrent writers.

Every read-modify-write runs under a file lock in the index directory, so
concurrent requests (and multiple worker processes) cannot interleave and
leave ``index.faiss`` and ``meta.json`` out of sync. Files are written to a
temporary path and atomically renamed so a crash never leaves a torn file.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import faiss
import numpy as np
from filelock import FileLock

LOCK_TIMEOUT_SECONDS = 30
INDEX_FILE = "index.faiss"
META_FILE = "meta.json"


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize rows so inner product equals cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vectors / norms


class FaissStore:
    """A flat inner-product index plus one metadata dict per vector."""

    def __init__(self, directory: str) -> None:
        self.directory = directory
        self.index_path = os.path.join(directory, INDEX_FILE)
        self.meta_path = os.path.join(directory, META_FILE)

    def _lock(self) -> FileLock:
        os.makedirs(self.directory, exist_ok=True)
        return FileLock(os.path.join(self.directory, ".lock"), timeout=LOCK_TIMEOUT_SECONDS)

    def _load(self) -> tuple[faiss.Index | None, list[dict[str, Any]]]:
        index = faiss.read_index(self.index_path) if os.path.exists(self.index_path) else None
        metas: list[dict[str, Any]] = []
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                metas = loaded if isinstance(loaded, list) else []
            except (OSError, json.JSONDecodeError):
                metas = []
        # Older metadata files stored vectors positionally without an explicit id.
        for position, meta in enumerate(metas):
            meta.setdefault("faiss_index", position)
        return index, metas

    def _save(self, index: faiss.Index, metas: list[dict[str, Any]]) -> None:
        tmp_index = self.index_path + ".tmp"
        tmp_meta = self.meta_path + ".tmp"
        faiss.write_index(index, tmp_index)
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(metas, f, indent=2)
        os.replace(tmp_index, self.index_path)
        os.replace(tmp_meta, self.meta_path)

    def add(self, vectors: np.ndarray, metas: list[dict[str, Any]]) -> None:
        """Append normalized vectors with their metadata."""
        if vectors.shape[0] == 0:
            return
        if vectors.shape[0] != len(metas):
            raise ValueError("Each vector needs exactly one metadata entry.")
        with self._lock():
            index, existing = self._load()
            if index is None:
                index = faiss.IndexFlatIP(vectors.shape[1])
            elif index.d != vectors.shape[1]:
                raise RuntimeError(
                    f"Embedding dimension mismatch: index has {index.d}, got {vectors.shape[1]}. "
                    "Delete the index directory to re-embed with the new model.",
                )
            start = index.ntotal
            index.add(vectors)
            for offset, meta in enumerate(metas):
                meta["faiss_index"] = start + offset
            self._save(index, existing + metas)

    def search(
        self,
        query: np.ndarray,
        limit: int,
        min_score: float,
    ) -> list[tuple[float, dict[str, Any], np.ndarray]]:
        """Return (score, metadata, stored vector) for hits at or above ``min_score``."""
        with self._lock():
            index, metas = self._load()
            if index is None or index.ntotal == 0 or not metas:
                return []
            by_id = {int(m["faiss_index"]): m for m in metas}
            scores, ids = index.search(query, min(limit, index.ntotal))
            hits: list[tuple[float, dict[str, Any], np.ndarray]] = []
            for score, idx in zip(scores[0], ids[0]):
                meta = by_id.get(int(idx))
                if idx < 0 or meta is None or float(score) < min_score:
                    continue
                hits.append((float(score), meta, index.reconstruct(int(idx))))
            return hits

    def remove_where(self, predicate: Callable[[dict[str, Any]], bool]) -> int:
        """Drop every vector whose metadata matches ``predicate``; return how many."""
        with self._lock():
            index, metas = self._load()
            if index is None:
                return 0
            keep = [
                m for m in metas if not predicate(m) and 0 <= int(m["faiss_index"]) < index.ntotal
            ]
            removed = len(metas) - len(keep)
            if removed == 0:
                return 0
            rebuilt = faiss.IndexFlatIP(index.d)
            vectors = [index.reconstruct(int(m["faiss_index"])) for m in keep]
            if vectors:
                rebuilt.add(np.vstack(vectors).astype("float32"))
            for position, meta in enumerate(keep):
                meta["faiss_index"] = position
            self._save(rebuilt, keep)
            return removed
