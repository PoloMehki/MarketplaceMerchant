"""config.py — Task 0.1: env + run configuration loading.

Loads environment variables (via python-dotenv) into a typed, validated
pydantic config object. Loading is STRICT (team decision): every required var
must be present, otherwise :func:`load_config` raises :class:`ConfigError`
naming all missing keys. Run ``python -m negagent.config --print`` to see the
resolved config with secrets masked.

SHARED FILE (Dev A + Dev B). Append your own fields only; coordinate before
changing the shape of existing fields (CLAUDE.md sections 2.6 / 3).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


# AppConfig field name -> environment variable name. All of these are required;
# a missing/blank value makes load_config raise ConfigError.
_REQUIRED_ENV: dict[str, str] = {
    "aws_region": "AWS_REGION",
    "bedrock_model_id": "BEDROCK_MODEL_ID",
    "apify_token": "APIFY_TOKEN",
    "apify_ecommerce_actor_id": "APIFY_ECOMMERCE_ACTOR_ID",
    "apify_fb_actor_id": "APIFY_FB_ACTOR_ID",
    "box_client_id": "BOX_CLIENT_ID",
    "box_client_secret": "BOX_CLIENT_SECRET",
}

# Field names whose values are secrets and must be masked on display.
_SECRET_FIELDS = frozenset({"apify_token", "box_client_secret"})

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class AppConfig(BaseModel):
    """Typed, immutable application configuration. See .env.example for vars."""

    model_config = ConfigDict(frozen=True)

    # --- Bedrock (required) ---
    aws_region: str
    bedrock_model_id: str

    # --- Apify (required) ---
    apify_token: str
    apify_ecommerce_actor_id: str
    apify_fb_actor_id: str
    mock_apify: bool = True

    # --- Box (required creds; archival only) ---
    box_client_id: str
    box_client_secret: str
    box_enterprise_id: Optional[str] = None
    box_root_folder_id: str = "0"
    box_jwt_config_path: Optional[Path] = None
    box_developer_token: Optional[str] = None

    # --- Runtime (optional, defaulted) ---
    mcp_config_path: Path = Field(default=Path("config/mcp.json"))
    sqlite_path: Path = Field(default=Path("negagent.db"))
    hitl_enabled: bool = True
    match_confidence_threshold: float = 0.6
    condition_tolerance: int = 1


def _get_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in _TRUE_VALUES:
        return True
    if val in _FALSE_VALUES:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def load_config(
    env_file: "str | os.PathLike[str]" = ".env", *, load_env: bool = True
) -> AppConfig:
    """Load and validate configuration from the environment.

    If ``load_env`` is true, values are first read from ``env_file`` (when it
    exists) via python-dotenv, without overriding variables already set in the
    process environment. Pass ``load_env=False`` (e.g. in tests) to read only
    the current process environment.

    Raises :class:`ConfigError` listing every missing required variable.
    """
    if load_env:
        load_dotenv(env_file, override=False)

    missing = sorted(
        env_name
        for env_name in _REQUIRED_ENV.values()
        if not os.environ.get(env_name, "").strip()
    )
    if missing:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill them in."
        )

    return AppConfig(
        aws_region=os.environ["AWS_REGION"],
        bedrock_model_id=os.environ["BEDROCK_MODEL_ID"],
        apify_token=os.environ["APIFY_TOKEN"],
        apify_ecommerce_actor_id=os.environ["APIFY_ECOMMERCE_ACTOR_ID"],
        apify_fb_actor_id=os.environ["APIFY_FB_ACTOR_ID"],
        mock_apify=_get_bool("MOCK_APIFY", True),
        box_client_id=os.environ["BOX_CLIENT_ID"],
        box_client_secret=os.environ["BOX_CLIENT_SECRET"],
        box_enterprise_id=os.environ.get("BOX_ENTERPRISE_ID") or None,
        box_root_folder_id=_get_str("BOX_ROOT_FOLDER_ID", "0"),
        box_jwt_config_path=(
            Path(p) if (p := os.environ.get("BOX_JWT_CONFIG_PATH", "").strip()) else None
        ),
        box_developer_token=os.environ.get("BOX_DEVELOPER_TOKEN") or None,
        mcp_config_path=Path(_get_str("MCP_CONFIG_PATH", "config/mcp.json")),
        sqlite_path=Path(_get_str("SQLITE_PATH", "negagent.db")),
        hitl_enabled=_get_bool("HITL_ENABLED", True),
        match_confidence_threshold=_get_float("MATCH_CONFIDENCE_THRESHOLD", 0.6),
        condition_tolerance=_get_int("CONDITION_TOLERANCE", 1),
    )


def _mask_secret(value: str) -> str:
    if not value:
        return "(unset)"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def render_config(cfg: AppConfig, *, mask: bool = True) -> str:
    """Render the config as readable lines, masking secrets unless disabled."""
    lines = ["Resolved negagent config:"]
    for name, value in cfg.model_dump().items():
        if mask and name in _SECRET_FIELDS and isinstance(value, str):
            value = _mask_secret(value)
        lines.append(f"  {name:<28}= {value}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="python -m negagent.config",
        description="Resolve and print the negagent configuration (secrets masked).",
    )
    parser.add_argument(
        "--print", action="store_true", dest="do_print",
        help="Print the resolved configuration.",
    )
    parser.add_argument(
        "--no-mask", action="store_true",
        help="Show secret values unmasked (use with care).",
    )
    args = parser.parse_args(argv)

    if not args.do_print:
        parser.print_help()
        return 0

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    print(render_config(cfg, mask=not args.no_mask))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
