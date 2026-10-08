"""Helpers for refreshing a token from a configured real environment."""

import base64
import datetime
import json
import logging
import os

import requests
from requests.exceptions import SSLError

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


def fetch_real_env_token_detail():
    """登录真实环境，返回 (token, error_message)。成功时 error 为 None。

    失败原因会细分到具体场景，便于前端直接展示：
        - 配置缺失/错误
        - SSL 证书校验失败（内网自签名证书）
        - 网络请求失败
        - 登录接口 HTTP 非 200
        - 登录被拒绝（returnCode != 0，如密码错误/账号锁定）
        - 响应缺少 accessToken
    """
    try:
        login = _get_login_config()
    except RealEnvTokenConfigError as exc:
        msg = "配置缺失/错误: %s" % exc
        logger.error("Real environment token: %s", msg)
        return None, msg

    try:
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
    except SSLError:
        msg = "登录接口 SSL 证书校验失败（内网自签名证书），请把 REAL_ENV_VERIFY_SSL 设为 false"
        logger.error("Real environment token: %s", msg)
        return None, msg
    except requests.RequestException as exc:
        msg = "登录接口网络请求失败: %s" % type(exc).__name__
        logger.error("Real environment token: %s", msg)
        return None, msg

    if response.status_code != 200:
        msg = "登录接口返回 HTTP %s" % response.status_code
        logger.error("Real environment token: %s", msg)
        return None, msg

    try:
        body = response.json()
    except ValueError:
        msg = "登录接口返回了非 JSON 响应"
        logger.error("Real environment token: %s", msg)
        return None, msg

    if not isinstance(body, dict):
        msg = "登录接口返回了非预期的 JSON 结构"
        logger.error("Real environment token: %s", msg)
        return None, msg

    # 登录失败时（密码错误/账号锁定等）返回 returnCode != 0，且没有 data 字段
    return_code = body.get("returnCode")
    if isinstance(return_code, int) and return_code != 0:
        reason = body.get("returnMsg") or body.get("message") or ""
        msg = ("登录被拒绝(returnCode=%s): %s" % (return_code, reason)).strip()
        logger.error("Real environment token: %s", msg)
        return None, msg

    data = body.get("data")
    token = data.get("accessToken") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token.strip():
        msg = "登录响应中缺少 accessToken（可能账号异常或接口变更）"
        logger.error("Real environment token: %s", msg)
        return None, msg

    return token, None


def fetch_real_env_token():
    """Login to the real environment and return accessToken, or None on failure."""
    token, _ = fetch_real_env_token_detail()
    return token


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
