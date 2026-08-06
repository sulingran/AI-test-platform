from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


REDACTED_VALUE = "[REDACTED]"
LOGIN_USERNAME_PLACEHOLDER = "login_username"
LOGIN_PASSWORD_PLACEHOLDER = "login_password"
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "authorization",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
)


def normalize_openai_base_url(value):
    """Convert a chat-completions endpoint into the base URL expected by OpenAI clients."""
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        return ""

    parts = urlsplit(normalized)
    path = parts.path.rstrip("/")
    endpoint_suffix = "/chat/completions"
    if path.endswith(endpoint_suffix):
        path = path[:-len(endpoint_suffix)].rstrip("/")

    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"

    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def validate_http_url(value, field_name="URL"):
    """Validate browser targets while still allowing intranet IP addresses."""
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) > 2048:
        raise ValueError(f"{field_name} is too long")

    try:
        URLValidator(schemes=["http", "https"])(normalized)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be a valid HTTP or HTTPS URL") from exc
    return normalized


def build_runtime_task_description(
    task_description,
    *,
    target_url="",
    login_url="",
    login_username="",
    login_password="",
):
    """Add one-time browser context without changing the persisted task text."""
    original_task = str(task_description or "").strip()
    context_lines = []

    if target_url:
        context_lines.append(f"Target system URL: {target_url}")

    if login_username and login_password:
        effective_login_url = login_url or target_url
        context_lines.extend([
            "Authentication must be completed before the original task:",
            f"1. Open the login page: {effective_login_url}",
            f"2. Enter exactly this username: <secret>{LOGIN_USERNAME_PLACEHOLDER}</secret>",
            f"3. Enter exactly this password: <secret>{LOGIN_PASSWORD_PLACEHOLDER}</secret>",
            "4. Submit the form and verify that login succeeded before continuing.",
            "Never print, repeat, or expose the supplied credentials in observations or results.",
        ])

    if not context_lines:
        return original_task

    return "\n".join([
        "Runtime browser context:",
        *context_lines,
        "",
        "Original test task:",
        original_task,
    ])


def get_allowed_domains(*urls):
    """Return unique hostnames used to constrain browser navigation with secrets."""
    domains = []
    for value in urls:
        hostname = urlsplit(str(value or "").strip()).hostname
        if hostname and hostname not in domains:
            domains.append(hostname)
    return domains


def redact_sensitive_data(value, sensitive_values=()):
    """Recursively redact credentials before logs or execution results are stored."""
    secrets = tuple(
        str(item) for item in sensitive_values
        if item is not None and str(item)
    )

    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, REDACTED_VALUE)
        return redacted

    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in SENSITIVE_KEY_PARTS):
                redacted[key] = REDACTED_VALUE
            else:
                redacted[key] = redact_sensitive_data(item, secrets)
        return redacted

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item, secrets) for item in value)

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_sensitive_data(item, secrets) for item in value]

    return value
