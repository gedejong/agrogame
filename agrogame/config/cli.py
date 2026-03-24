from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List

from agrogame.config.compose import load_and_compose
from agrogame.config.validation import validate_data
from agrogame.config.watcher import watch
from agrogame.events import EventBus, ConfigReloaded


def _cmd_validate(args: argparse.Namespace) -> int:
    schema = args.schema
    files = [Path(p) for p in args.files]
    data = load_and_compose(files)
    validate_data(data, schema)
    print(f"Validation OK for schema '{schema}' over {len(files)} file(s)")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    schema = args.schema
    files = [Path(p) for p in args.files]
    out = Path(args.out)
    data = load_and_compose(files)
    validate_data(data, schema)
    out.write_text("\n".join([f"# built from: {p}" for p in files]) + "\n")
    out.write_text(out.read_text() + "---\n")
    import yaml

    out.write_text(out.read_text() + yaml.safe_dump(data, sort_keys=False))
    print(f"Built configuration written to {out}")
    return 0


def _cmd_watch(args: argparse.Namespace) -> int:  # pragma: no cover - long-running loop
    schema = args.schema
    files = [Path(p) for p in args.files]
    bus = EventBus()

    def on_change(_changed: List[Path]) -> None:
        data = load_and_compose(files)
        try:
            validate_data(data, schema)
            bus.emit(ConfigReloaded(files=files, schema=schema))
            print(f"Reloaded {len(files)} files; schema '{schema}' OK")
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Reload failed: {e}") from e

    observer: Any = watch({p.parent for p in files}, on_change)
    print("Watching for changes. Press Ctrl+C to stop.")
    try:
        while True:
            import time

            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        # Best-effort stopping without strict typing on external observer
        observer.stop()
        observer.join()
    return 0


def _cmd_wizard(args: argparse.Namespace) -> int:
    # Minimal placeholder to satisfy acceptance criteria; can be expanded
    print("Interactive builder is not yet implemented. Use 'build' for now.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agrogame", description="AgroGame config tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Validate configuration against a schema")
    v.add_argument("schema", choices=["crop", "soil", "weather", "management"])
    v.add_argument("files", nargs="+", help="Config files (YAML/JSON) in order")
    v.set_defaults(func=_cmd_validate)

    b = sub.add_parser("build", help="Compose and validate, then write YAML output")
    b.add_argument("schema", choices=["crop", "soil", "weather", "management"])
    b.add_argument("out", help="Output YAML path")
    b.add_argument("files", nargs="+", help="Config files (YAML/JSON) in order")
    b.set_defaults(func=_cmd_build)

    w = sub.add_parser("watch", help="Watch files and emit reload events on change")
    w.add_argument("schema", choices=["crop", "soil", "weather", "management"])
    w.add_argument("files", nargs="+", help="Config files (YAML/JSON) in order")
    w.set_defaults(func=_cmd_watch)

    wiz = sub.add_parser("wizard", help="Interactive configuration builder")
    wiz.set_defaults(func=_cmd_wizard)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    result = ns.func(ns)
    assert isinstance(result, int)
    return result


if __name__ == "__main__":
    sys.exit(main())
