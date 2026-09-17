"""
Reading /etc/renzy-bridge.toml.

A bridge that starts with a half-understood config is worse than one that refuses to start: the
restaurant thinks it has paper and finds out at the pass. Every way of getting it wrong has to be
an error at boot with a sentence saying what to change.
"""

from __future__ import annotations

import tomllib
from dataclasses import fields
from pathlib import Path

import pytest
from conftest import make_config

from renzy_bridge.config import (
    DEFAULT_PRINTER_PORT,
    Config,
    ConfigError,
    Printer,
    from_dict,
    load,
)

MINIMAL = {
    "api": {"url": "https://api.renzy.app", "device_token": "tok"},
    "printers": {"kitchen": "192.168.1.50"},
}


def test_a_printer_without_a_port_gets_the_escpos_default() -> None:
    config = from_dict(MINIMAL)
    assert config.printers["kitchen"] == Printer("kitchen", "192.168.1.50", DEFAULT_PRINTER_PORT)
    assert DEFAULT_PRINTER_PORT == 9100


def test_a_printer_may_be_a_table_with_an_explicit_port() -> None:
    config = from_dict({**MINIMAL, "printers": {"kitchen": {"host": "10.0.0.9", "port": 9101}}})
    assert config.printers["kitchen"] == Printer("kitchen", "10.0.0.9", 9101)


def test_a_trailing_slash_on_the_api_url_is_dropped() -> None:
    """Otherwise every request path would be doubled up and every fetch would 404."""
    assert (
        from_dict({**MINIMAL, "api": {**MINIMAL["api"], "url": "https://x/"}}).api_url
        == "https://x"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"printers": {"kitchen": "h"}}, r"\[api\] url is required"),
        ({"api": {"url": "https://x"}, "printers": {"kitchen": "h"}}, "device token is required"),
        ({"api": {"url": "https://x", "device_token": "t"}}, "At least one printer"),
        (
            {"api": {"url": "https://x", "device_token": "t"}, "printers": {"bar": "h"}},
            "Configure a 'kitchen' and/or a 'front' printer",
        ),
        (
            {**MINIMAL, "printers": {"bar": {"port": 9100}}},
            "printer 'bar' has no host",
        ),
        ({**MINIMAL, "printers": {"bar": 9100}}, "must be a string 'host:port' or a table"),
        (
            {**MINIMAL, "stations": {"GRILL": "grill"}},
            "points at printers that are not configured",
        ),
    ],
)
def test_a_config_that_cannot_work_is_refused_with_a_reason(raw: dict, expected: str) -> None:
    with pytest.raises(ConfigError, match=expected):
        from_dict(raw)


def test_the_device_token_may_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """systemd keeps the secret in an EnvironmentFile so the config can be world-readable."""
    monkeypatch.setenv("RENZY_DEVICE_TOKEN", "from-env")
    config = from_dict({"api": {"url": "https://x"}, "printers": {"kitchen": "h"}})
    assert config.device_token == "from-env"


def test_the_environment_wins_over_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENZY_DEVICE_TOKEN", "from-env")
    assert from_dict(MINIMAL).device_token == "from-env"


def test_the_redacted_form_never_carries_the_token(tmp_path: Path) -> None:
    """`redacted()` is what goes in the first line of the journal on every start."""
    config = make_config(tmp_path)
    assert "tok-secret" not in repr(config.redacted())
    assert "device_token" not in config.redacted()


def test_a_station_with_no_mapping_goes_to_the_kitchen(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        printers={"kitchen": "h", "bar": "h2"},
        stations={"BAR": "bar"},
    )
    assert config.printer_for_station("BAR") == "bar"
    assert config.printer_for_station("GRILL") == "kitchen"
    assert config.printer_for_station(None) == "kitchen"


def test_a_missing_config_file_names_the_path_it_looked_at() -> None:
    with pytest.raises(ConfigError, match="No config file at"):
        load(Path("/nonexistent/renzy-bridge.toml"))


def test_invalid_toml_is_reported_as_invalid_toml(tmp_path: Path) -> None:
    path = tmp_path / "renzy-bridge.toml"
    path.write_text("this is not = = toml", encoding="utf-8")
    with pytest.raises(ConfigError, match="is not valid TOML"):
        load(path)


def test_the_shipped_example_file_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """bridge/renzy-bridge.example.toml is what an installer copies to /etc. It must work."""
    example = Path(__file__).resolve().parents[1] / "renzy-bridge.example.toml"
    monkeypatch.delenv("RENZY_DEVICE_TOKEN", raising=False)
    config = load(example)

    assert config.api_url == "https://api.renzy.app"
    assert set(config.printers) == {"kitchen", "front"}
    assert config.state_path == Path("/var/lib/renzy-bridge/state.sqlite3")
    # No [stations] section: one unsplit ticket to the kitchen, which is how RENZY starts.
    assert config.station_printers == {}


def test_the_example_documents_exactly_the_bridge_settings_that_exist() -> None:
    """
    A knob in the example that nothing reads is a lie to whoever installs the Pi; a knob in the
    code with no example is one nobody will find. Both directions are asserted, so adding a
    setting without documenting it fails here.
    """
    example = Path(__file__).resolve().parents[1] / "renzy-bridge.example.toml"
    documented = set(tomllib.loads(example.read_text(encoding="utf-8")).get("bridge", {}))
    # Everything on Config that is not [api], [printers] or [stations] comes from [bridge].
    implemented = {
        f.name
        for f in fields(Config)
        if f.name not in {"api_url", "device_token", "printers", "station_printers"}
    }
    assert documented == implemented
