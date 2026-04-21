"""Small shared utilities for JSON-on-disk state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, obj: Any) -> None:
    """Serialize obj to path via a `.tmp` sibling and atomic rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
