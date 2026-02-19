from __future__ import annotations

import json
from pathlib import Path
from typing import List, Protocol


class StateStore(Protocol):
    def is_processed_trade(self, trade_id: str) -> bool: ...

    def remember_processed_trade(self, trade_id: str, *, max_size: int, trim_to: int) -> None: ...

    def close(self) -> None: ...


class InMemoryStateStore:
    def __init__(self):
        self._processed_set = set()
        self._processed_order: List[str] = []

    def is_processed_trade(self, trade_id: str) -> bool:
        return bool(trade_id) and trade_id in self._processed_set

    def remember_processed_trade(self, trade_id: str, *, max_size: int, trim_to: int) -> None:
        if not trade_id or trade_id in self._processed_set:
            return
        self._processed_set.add(trade_id)
        self._processed_order.append(trade_id)

        trim_to = max(1, int(trim_to))
        max_size = max(trim_to, int(max_size))
        if len(self._processed_order) <= max_size:
            return
        while len(self._processed_order) > trim_to:
            old_id = self._processed_order.pop(0)
            self._processed_set.discard(old_id)

    def close(self) -> None:
        return


class JsonFileStateStore(InMemoryStateStore):
    def __init__(self, path: Path):
        super().__init__()
        self.path = Path(path)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text())
            ids = raw.get("processed_trade_ids") or []
            if isinstance(ids, list):
                for item in ids:
                    trade_id = str(item).strip()
                    if trade_id and trade_id not in self._processed_set:
                        self._processed_set.add(trade_id)
                        self._processed_order.append(trade_id)
        except Exception:
            # Ignore corrupt state and rebuild from runtime.
            self._processed_set.clear()
            self._processed_order.clear()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"processed_trade_ids": self._processed_order}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload))
        tmp_path.replace(self.path)

    def remember_processed_trade(self, trade_id: str, *, max_size: int, trim_to: int) -> None:
        before = len(self._processed_order)
        super().remember_processed_trade(trade_id, max_size=max_size, trim_to=trim_to)
        if len(self._processed_order) != before:
            self._save()

    def close(self) -> None:
        self._save()
