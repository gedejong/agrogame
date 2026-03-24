from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt

from agrogame.soil.canopy.interception import InterceptionState


def plot_interception_isolation(
    profile: str,
    days: int,
    rain: float,
    out: Path,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    # Use interception state directly for isolation
    istate = InterceptionState()
    lai = 3.0
    intercepted = []
    throughfall = []
    for _ in range(days):
        took, tf = istate.intercept(lai, rain)
        # Evaporate a small fraction from canopy each day (e.g., 1 mm)
        _ = istate.evaporate(1.0)
        intercepted.append(took)
        throughfall.append(tf)

    x = list(range(1, days + 1))
    plt.figure(figsize=(8, 5))
    plt.bar(x, intercepted, label="Intercepted (mm)", color="#1f77b4", alpha=0.7)
    plt.bar(
        x,
        throughfall,
        bottom=intercepted,
        label="Throughfall (mm)",
        color="#aec7e8",
        alpha=0.7,
    )
    plt.xlabel("Day")
    plt.ylabel("mm")
    plt.title("Interception isolation")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print("Saved", out)
