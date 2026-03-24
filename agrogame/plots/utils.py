from __future__ import annotations

from typing import Any, List, Sequence, Tuple


def moving_average(values: Sequence[float], window: int) -> List[float]:
    w = max(1, int(window))
    if w == 1:
        return list(values)
    out: List[float] = []
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= w:
            run -= values[i - w]
        out.append(run / min(i + 1, w))
    return out


def merge_legends(*axes: Any) -> Tuple[list, list]:
    handles: list = []
    labels: list = []
    for ax in axes:
        local_handles, local_labels = ax.get_legend_handles_labels()
        handles.extend(local_handles)
        labels.extend(local_labels)
    # de-duplicate by label while preserving order
    seen: set[str] = set()
    unique_h: list = []
    unique_l: list[str] = []
    for handle, label in zip(handles, labels, strict=False):
        if label not in seen:
            seen.add(label)
            unique_h.append(handle)
            unique_l.append(label)
    return unique_h, unique_l


def clamp_forward_fill(values: Sequence[float], lo: float, hi: float) -> List[float]:
    out: List[float] = []
    last: float | None = None
    for v in values:
        vv = v
        if vv is None or vv < lo or vv > hi:
            vv = last if last is not None else max(lo, min(0.0, hi))
        out.append(vv)
        last = vv
    return out
