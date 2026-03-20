__version__ = "0.1.0"

__all__: list[str] = ["dashboard_main"]


# Optional: expose dashboard entrypoint via lazy wrapper to avoid import errors
def dashboard_main(argv: list[str] | None = None) -> None:  # pragma: no cover
    """Run the Streamlit dashboard (requires extras)."""
    from .dashboard.app import main as _main  # local import to keep optional

    _main(argv)
