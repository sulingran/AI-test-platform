"""Provider registry used by the shared AI gateway."""

from typing import Any, Dict


PROVIDERS: Dict[str, Dict[str, Any]] = {
    "deepseek": {
        "name": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "auth": "bearer",
        "model_hint": "deepseek-chat",
    },
    "qwen": {
        "name": "Qwen",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "auth": "api_key",
        "model_hint": "qwen-plus",
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "auth": "bearer",
        "model_hint": "Qwen/Qwen2.5-7B-Instruct",
    },
    "zhipu": {
        "name": "Zhipu",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "auth": "bearer",
        "model_hint": "glm-4-plus",
    },
    "xiaomi": {
        "name": "Xiaomi",
        "default_base_url": "https://api.xiaomimimo.com/v1",
        "auth": "bearer",
        "model_hint": "",
    },
    "xiaomi_coding_plan": {
        "name": "Xiaomi Coding Plan",
        "default_base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "auth": "bearer",
        "model_hint": "",
    },
    "other": {
        "name": "Other",
        "default_base_url": "",
        "auth": "bearer",
        "model_hint": "",
    },
}


def get_provider(provider: str) -> Dict[str, Any]:
    return PROVIDERS.get(provider or "", PROVIDERS["other"])


def provider_display_name(provider: str) -> str:
    return get_provider(provider)["name"]
