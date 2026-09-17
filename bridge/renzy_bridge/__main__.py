"""
Entry point: `python -m renzy_bridge` (what the systemd unit runs).

Logging goes to stdout because systemd captures it into the journal; there is no log file to rotate
on an SD card that would rather not be written to.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import printer as printer_io
from .config import Config, ConfigError, load
from .daemon import build


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


def _init_sentry() -> None:
    """Plain Sentry SDK, no Django integration — see infra/bridge/sentry.example.py."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger("renzy.bridge").warning("SENTRY_DSN set but sentry-sdk is not installed")
        return
    sentry_sdk.init(
        dsn=dsn,
        release=os.environ.get("GIT_SHA"),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("component", "print_bridge")


def _selftest(config: Config) -> int:
    """`--selftest` — prove the config parses and say which printers answer. Prints no paper."""
    print(f"config OK: {config.redacted()}")
    failures = 0
    for name, target in sorted(config.printers.items()):
        ok = printer_io.probe(target)
        print(f"  {name:<10} {target} {'reachable' if ok else 'UNREACHABLE'}")
        failures += 0 if ok else 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renzy-bridge", description="RENZY ESC/POS print bridge")
    parser.add_argument("-c", "--config", type=Path, default=None, help="path to renzy-bridge.toml")
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="check the config and probe every printer, then exit",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.log_level)
    _init_sentry()

    try:
        config = load(args.config)
    except ConfigError as err:
        logging.getLogger("renzy.bridge").error("%s", err)
        return 2

    if args.selftest:
        return _selftest(config)

    bridge = build(config)
    bridge.install_signal_handlers()
    try:
        bridge.run()
    finally:
        bridge.api.close()
        bridge.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
