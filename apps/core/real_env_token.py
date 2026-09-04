"""Helpers for refreshing a token from a configured real environment."""

import base64
import datetime
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

LOGIN_PATH = "/uap-change-service/oauth/token"
DEFAULT_LOGIN_TYPE = "2"


class RealEnvTokenConfigError(ValueError):
    """Raised when real-environment token configuration is incomplete."""


def _read_bool(name, default=True):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RealEnvTokenConfigError(f"{name} must be a boolean value")


def _get_login_config():
    """Read login settings without exposing secret values."""
    required = {
        "REAL_ENV_BASE_URL": os.getenv("REAL_ENV_BASE_URL", "").strip(),
        "REAL_ENV_USERNAME": os.getenv("REAL_ENV_USERNAME", "").strip(),
        "REAL_ENV_PASSWORD": os.getenv("REAL_ENV_PASSWORD", ""),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RealEnvTokenConfigError(
            "missing required settings: " + ", ".join(missing)
        )

    base_url = required["REAL_ENV_BASE_URL"].rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise RealEnvTokenConfigError(
            "REAL_ENV_BASE_URL must include http:// or https://"
        )

    return {
        "url": base_url + LOGIN_PATH,
        "username": required["REAL_ENV_USERNAME"],
        "password": required["REAL_ENV_PASSWORD"],
        "login_type": os.getenv("REAL_ENV_LOGIN_TYPE", DEFAULT_LOGIN_TYPE).strip()
        or DEFAULT_LOGIN_TYPE,
        "verify": os.getenv("REAL_ENV_CA_BUNDLE", "").strip()
        or _read_bool("REAL_ENV_VERIFY_SSL"),
    }


def decode_jwt_exp(token):
    """Return a JWT expiry timestamp in local time, or None if unavailable."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        if exp:
            return datetime.datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def fetch_real_env_token():
    """Login to the real environment and return accessToken, or None on failure."""
    try:
        login = _get_login_config()
        response = requests.post(
            login["url"],
            data={
                "userName": login["username"],
                "password": login["password"],
                "loginType": login["login_type"],
            },
            timeout=25,
            verify=login["verify"],
        )
        response.raise_for_status()
        token = response.json()["data"]["accessToken"]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("response did not contain a non-empty access token")
        return token
    except RealEnvTokenConfigError as exc:
        logger.error("Real environment token configuration error: %s", exc)
    except requests.RequestException as exc:
        logger.error("Real environment token request failed: %s", type(exc).__name__)
    except (KeyError, TypeError, ValueError) as exc:
        logger.error("Real environment token response invalid: %s", type(exc).__name__)
    except Exception:
        logger.exception("Unexpected real environment token error")
    return None


def write_token_to_environment(env, token):
    """Write token to variables["token"] while preserving its value shape."""
    variables = env.variables or {}
    old = variables.get("token")
    if isinstance(old, dict):
        variables["token"] = {"currentValue": token, "initialValue": token}
    else:
        variables["token"] = token
    env.variables = variables
    env.save()
