"""
Loads config.yaml once and exposes it as a plain dict.
Environment variables in .env override values in config.yaml for secrets
and environment-specific paths (TAILSCALE_AUTH_KEY, TAILSCALE_IP,
DB_PATH, LOG_FILE, SERIAL_PORT).
Import `cfg` anywhere in the project to access configuration values.
"""
import os
import yaml
from pathlib import Path

# Load .env if present — do this before reading config so overrides apply
_ENV_PATH = Path(__file__).parent / ".env"
if _ENV_PATH.exists():
    with open(_ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: Path = _CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Override with environment variables where set
    env = os.environ
    if env.get("TAILSCALE_AUTH_KEY"):
        data.setdefault("tailscale", {})["auth_key"] = env["TAILSCALE_AUTH_KEY"]
    if env.get("TAILSCALE_IP"):
        data.setdefault("tailscale", {})["ip"] = env["TAILSCALE_IP"]
    if env.get("DB_PATH"):
        data.setdefault("database", {})["path"] = env["DB_PATH"]
    if env.get("LOG_FILE"):
        data.setdefault("logging", {})["log_file"] = env["LOG_FILE"]
    if env.get("SERIAL_PORT"):
        data.setdefault("sensors", {})["serial_port"] = env["SERIAL_PORT"]

    return data


cfg: dict = load_config()
