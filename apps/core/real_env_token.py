"""真实环境登录取 token 的共享工具（供 refresh_token 命令与接口 API 复用）。

把原先散落在 refresh_token 管理命令里的登录逻辑抽出，供命令行与 HTTP 接口共用，
避免同一段“登录真实环境→拿 token→写回环境变量”逻辑在两处重复实现。
"""
import base64
import datetime
import json

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# 真实环境登录（与 docs/setup 下探测脚本保持一致）
REAL_ENV_BASE = "https://192.168.159.114:9993"
LOGIN_PATH = "/uap-change-service/oauth/token"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "UZfpjBdeLX/5wCRnYYntxw=="  # 已加密的密码串
LOGIN_TYPE = "2"

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def decode_jwt_exp(token):
    """从 JWT payload 解析过期时间（本地时区），失败返回 None。"""
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
    """登录真实环境，成功返回 accessToken，失败返回 None。"""
    try:
        r = requests.post(
            REAL_ENV_BASE + LOGIN_PATH,
            data={
                "userName": DEFAULT_USERNAME,
                "password": DEFAULT_PASSWORD,
                "loginType": LOGIN_TYPE,
            },
            timeout=25,
            verify=False,
        )
        r.raise_for_status()
        return r.json()["data"]["accessToken"]
    except Exception:
        return None


def write_token_to_environment(env, token):
    """把 token 写回环境的 variables["token"]，保留原有取值结构。

    原值是 dict（{currentValue, initialValue}）则写回 dict；否则写纯字符串。
    缺失时也会创建。
    """
    variables = env.variables or {}
    old = variables.get("token")
    if isinstance(old, dict):
        variables["token"] = {"currentValue": token, "initialValue": token}
    else:
        variables["token"] = token
    env.variables = variables
    env.save()