__version__ = "0.1.0"

# Optional: expose dashboard entrypoint when extras are installed
try:  # pragma: no cover - optional dependency surface
    from .dashboard.app import main as dashboard_main  # type: ignore
except Exception:  # pragma: no cover
    dashboard_main = None  # type: ignore
