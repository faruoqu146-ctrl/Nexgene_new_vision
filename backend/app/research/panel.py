"""Panel construction (boot-safe stub — replace with full surface module)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


@dataclass
class Panel:
    rows: list = field(default_factory=list)
    kinds: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def build_panel(observations: Iterable, *, tz: str = "UTC", end=None, window_days: int = 90, biomarkers=None) -> Panel:
    rows = list(observations) if observations is not None else []
    kinds = sorted({getattr(r, "kind", None) or (r.get("kind") if isinstance(r, dict) else None) for r in rows})
    kinds = [k for k in kinds if k]
    return Panel(rows=rows, kinds=kinds, meta={"tz": tz, "window_days": window_days, "n": len(rows)})


def panel_from_arrays(*args, **kwargs) -> Panel:
    return Panel()


def panel_quality(panel: Panel) -> dict:
    return {"n": len(panel.rows), "kinds": list(panel.kinds)}
