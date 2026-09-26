"""配置读取与校验。"""

from __future__ import annotations

import json

import pytest

from coke.config import PlatformConfig, config_to_mapping, default_config, load_config
from coke.errors import ConfigError


def test_default_config_has_all_limits():
    config = default_config()
    assert config.pusher.stroke_baseline_mm > 0
    assert config.collector.settled(config.collector.pressure_target_pa)
    assert config.heating.confirmed(config.heating.temp_target_c)
    assert config.dust.damper_open_deg <= 90.0


def test_load_config_round_trips_through_mapping(tmp_path):
    payload = config_to_mapping(default_config())
    path = tmp_path / "coke.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_config(str(path))
    assert loaded.pusher == default_config().pusher
    assert loaded.quench.spray_duration_s == default_config().quench.spray_duration_s


def test_load_config_rejects_missing_file():
    with pytest.raises(ConfigError):
        load_config("does-not-exist.json")


def test_config_rejects_inverted_speed_limits():
    payload = config_to_mapping(default_config())
    payload["limits"]["pusher"]["speed_min_mm_s"] = 40.0
    with pytest.raises(ConfigError):
        PlatformConfig.from_mapping(payload)


def test_config_rejects_pressure_target_out_of_band():
    payload = config_to_mapping(default_config())
    payload["limits"]["collector"]["pressure_target_pa"] = 0.0
    with pytest.raises(ConfigError):
        PlatformConfig.from_mapping(payload)
