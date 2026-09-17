"""
Bridge configuration, read from /etc/renzy-bridge.toml.

The device token is a secret and lives in the config file (mode 0600, owned by the bridge user) or
in RENZY_DEVICE_TOKEN. It is never logged, and `Config.redacted()` is what goes in a log line.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("/etc/renzy-bridge.toml")

# Every ESC/POS network printer worth buying listens here.
DEFAULT_PRINTER_PORT = 9100

# The two logical printers the restaurant actually has. "kitchen" is the fallback for any station
# without its own printer; "front" is the till printer that produces receipts.
KITCHEN = "kitchen"
FRONT = "front"


class ConfigError(RuntimeError):
    """The config file is missing, unreadable, or does not describe a usable bridge."""


@dataclass(frozen=True)
class Printer:
    name: str
    host: str
    port: int = DEFAULT_PRINTER_PORT

    def __str__(self) -> str:
        return f"{self.name} ({self.host}:{self.port})"


@dataclass(frozen=True)
class Config:
    api_url: str
    device_token: str
    printers: dict[str, Printer]
    state_path: Path
    # Which prep station goes to which printer. Anything unlisted goes to `kitchen`.
    station_printers: dict[str, str] = field(default_factory=dict)
    reconnect_min_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    printer_timeout_seconds: float = 5.0
    healthcheck_seconds: float = 60.0
    retry_seconds: float = 15.0

    def printer_for_station(self, station: str | None) -> str:
        """The printer name for a prep station, falling back to the kitchen printer."""
        if station is None:
            return KITCHEN
        return self.station_printers.get(station, KITCHEN)

    def printer(self, name: str) -> Printer | None:
        return self.printers.get(name)

    def redacted(self) -> dict[str, Any]:
        return {
            "api_url": self.api_url,
            "printers": {name: str(p) for name, p in self.printers.items()},
            "station_printers": dict(self.station_printers),
            "state_path": str(self.state_path),
        }


def _printers_from(raw: dict[str, Any]) -> dict[str, Printer]:
    printers: dict[str, Printer] = {}
    for name, value in (raw or {}).items():
        if isinstance(value, str):
            host, _, port = value.partition(":")
            printers[name] = Printer(name, host, int(port) if port else DEFAULT_PRINTER_PORT)
        elif isinstance(value, dict):
            host = value.get("host")
            if not host:
                raise ConfigError(f"printer '{name}' has no host")
            printers[name] = Printer(
                name, str(host), int(value.get("port", DEFAULT_PRINTER_PORT))
            )
        else:
            raise ConfigError(f"printer '{name}' must be a string 'host:port' or a table")
    return printers


def load(path: Path | str | None = None) -> Config:
    config_path = Path(path or os.environ.get("RENZY_BRIDGE_CONFIG") or DEFAULT_CONFIG_PATH)
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise ConfigError(f"No config file at {config_path}") from err
    except tomllib.TOMLDecodeError as err:
        raise ConfigError(f"{config_path} is not valid TOML: {err}") from err
    return from_dict(raw, config_path=config_path)


def from_dict(raw: dict[str, Any], *, config_path: Path | None = None) -> Config:
    api = raw.get("api") or {}
    api_url = str(api.get("url") or "").rstrip("/")
    if not api_url:
        raise ConfigError("[api] url is required")

    token = os.environ.get("RENZY_DEVICE_TOKEN") or api.get("device_token")
    if not token:
        raise ConfigError(
            "A device token is required: set [api] device_token, or RENZY_DEVICE_TOKEN. "
            "Enrol the Pi as a device with allowed_roles = ['PRINTER'] to get one."
        )

    printers = _printers_from(raw.get("printers") or {})
    if not printers:
        raise ConfigError("At least one printer must be configured under [printers]")
    if KITCHEN not in printers and FRONT not in printers:
        raise ConfigError(f"Configure a '{KITCHEN}' and/or a '{FRONT}' printer under [printers]")

    stations = {str(k): str(v) for k, v in (raw.get("stations") or {}).items()}
    unknown = sorted({v for v in stations.values()} - set(printers))
    if unknown:
        raise ConfigError(f"[stations] points at printers that are not configured: {unknown}")

    bridge = raw.get("bridge") or {}
    state_path = Path(bridge.get("state_path") or "/var/lib/renzy-bridge/state.sqlite3")

    del config_path
    return Config(
        api_url=api_url,
        device_token=str(token),
        printers=printers,
        state_path=state_path,
        station_printers=stations,
        reconnect_min_seconds=float(bridge.get("reconnect_min_seconds", 1.0)),
        reconnect_max_seconds=float(bridge.get("reconnect_max_seconds", 30.0)),
        printer_timeout_seconds=float(bridge.get("printer_timeout_seconds", 5.0)),
        healthcheck_seconds=float(bridge.get("healthcheck_seconds", 60.0)),
        retry_seconds=float(bridge.get("retry_seconds", 15.0)),
    )
