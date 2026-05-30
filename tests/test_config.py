"""Task 0.1: test_config_loads_from_env, test_config_missing_required_raises.

All tests read only the monkeypatched process environment (load_env=False) so
they never touch a real .env file or the network.
"""
import pytest

from negagent.config import AppConfig, ConfigError, load_config

# A complete set of the strict-required environment variables.
_REQUIRED = {
    "AWS_REGION": "us-west-2",
    "BEDROCK_MODEL_ID": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "APIFY_TOKEN": "apify_api_secret_token",
    "APIFY_ECOMMERCE_ACTOR_ID": "apify/ecommerce-actor",
    "APIFY_FB_ACTOR_ID": "apify/fb-marketplace-actor",
    "BOX_CLIENT_ID": "box-client-id",
    "BOX_CLIENT_SECRET": "box-client-secret-value",
}

# Optional vars that may leak in from the real environment; clear them so
# default-value assertions are deterministic.
_OPTIONAL = [
    "MOCK_APIFY", "HITL_ENABLED", "MATCH_CONFIDENCE_THRESHOLD",
    "CONDITION_TOLERANCE", "SQLITE_PATH", "MCP_CONFIG_PATH",
    "BOX_ENTERPRISE_ID", "BOX_ROOT_FOLDER_ID",
]


def _apply_env(monkeypatch, values: dict, *, clear_optional: bool = True):
    """Set exactly `values` for the required/optional keys, deleting the rest."""
    for key in list(_REQUIRED) + (_OPTIONAL if clear_optional else []):
        monkeypatch.delenv(key, raising=False)
    for key, val in values.items():
        monkeypatch.setenv(key, val)


def test_config_loads_from_env(monkeypatch):
    _apply_env(monkeypatch, {
        **_REQUIRED,
        "MOCK_APIFY": "false",
        "HITL_ENABLED": "false",
        "MATCH_CONFIDENCE_THRESHOLD": "0.8",
        "CONDITION_TOLERANCE": "2",
        "SQLITE_PATH": "tmp/test.db",
    })

    cfg = load_config(load_env=False)

    assert isinstance(cfg, AppConfig)
    assert cfg.aws_region == "us-west-2"
    assert cfg.bedrock_model_id == _REQUIRED["BEDROCK_MODEL_ID"]
    assert cfg.apify_token == "apify_api_secret_token"
    assert cfg.apify_ecommerce_actor_id == "apify/ecommerce-actor"
    assert cfg.box_client_secret == "box-client-secret-value"
    # Parsed (non-string) values.
    assert cfg.mock_apify is False
    assert cfg.hitl_enabled is False
    assert cfg.match_confidence_threshold == 0.8
    assert cfg.condition_tolerance == 2
    assert str(cfg.sqlite_path).replace("\\", "/") == "tmp/test.db"


def test_config_defaults_applied_when_optional_absent(monkeypatch):
    _apply_env(monkeypatch, dict(_REQUIRED))

    cfg = load_config(load_env=False)

    assert cfg.mock_apify is True
    assert cfg.hitl_enabled is True
    assert cfg.match_confidence_threshold == 0.6
    assert cfg.condition_tolerance == 1
    assert cfg.box_enterprise_id is None
    assert cfg.box_root_folder_id == "0"
    assert str(cfg.mcp_config_path).replace("\\", "/") == "config/mcp.json"
    assert str(cfg.sqlite_path) == "negagent.db"


@pytest.mark.parametrize(
    "missing_key", ["AWS_REGION", "BEDROCK_MODEL_ID", "APIFY_TOKEN", "BOX_CLIENT_SECRET"]
)
def test_config_missing_required_raises(monkeypatch, missing_key):
    values = {k: v for k, v in _REQUIRED.items() if k != missing_key}
    _apply_env(monkeypatch, values)

    with pytest.raises(ConfigError) as excinfo:
        load_config(load_env=False)

    # The error must name the missing variable so the operator can fix it.
    assert missing_key in str(excinfo.value)


def test_config_blank_required_treated_as_missing(monkeypatch):
    _apply_env(monkeypatch, {**_REQUIRED, "APIFY_TOKEN": "   "})

    with pytest.raises(ConfigError) as excinfo:
        load_config(load_env=False)

    assert "APIFY_TOKEN" in str(excinfo.value)


def test_config_invalid_number_raises(monkeypatch):
    _apply_env(monkeypatch, {**_REQUIRED, "MATCH_CONFIDENCE_THRESHOLD": "not-a-number"})

    with pytest.raises(ConfigError):
        load_config(load_env=False)
