"""File-backed prompt registry.

Prompt versions are source-controlled files. The registry deliberately does
not import models or write to the database, so it is safe to use against an
existing installation with production data. Existing v1 prompts continue to
come from the project's legacy ``docs/tester*.md`` files; later versions can
be added as ``docs/prompts/<type>/vN.md``.
"""

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional

from django.conf import settings


_VERSION_PATTERN = re.compile(r"^v(?P<version>\d+)\.md$", re.IGNORECASE)

PROMPT_SEEDS: Dict[str, Dict[str, str]] = {
    "writer": {
        "name": "Test case writer",
        "legacy_source": "docs/tester.md",
    },
    "reviewer": {
        "name": "Test case reviewer",
        "legacy_source": "docs/tester_pro.md",
    },
}


def content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _base_dir() -> Path:
    return Path(settings.BASE_DIR)


def _version_dir(prompt_type: str) -> Path:
    return _base_dir() / "docs" / "prompts" / prompt_type


def _legacy_path(prompt_type: str) -> Path:
    seed = PROMPT_SEEDS.get(prompt_type)
    if not seed:
        raise KeyError(f"Unknown prompt type: {prompt_type}")
    return _base_dir() / seed["legacy_source"]


def available_versions(prompt_type: str) -> List[int]:
    """Return source-controlled versions in ascending order."""
    if prompt_type not in PROMPT_SEEDS:
        raise KeyError(f"Unknown prompt type: {prompt_type}")
    versions = set()
    directory = _version_dir(prompt_type)
    if directory.is_dir():
        for path in directory.iterdir():
            match = _VERSION_PATTERN.match(path.name)
            if match and path.is_file():
                versions.add(int(match.group("version")))
    if 1 not in versions and _legacy_path(prompt_type).is_file():
        versions.add(1)
    return sorted(versions)


def _path_for_version(prompt_type: str, version: int) -> Path:
    explicit = _version_dir(prompt_type) / f"v{int(version)}.md"
    if explicit.is_file():
        return explicit
    if int(version) == 1:
        legacy = _legacy_path(prompt_type)
        if legacy.is_file():
            return legacy
    raise FileNotFoundError(f"Prompt {prompt_type} v{version} does not exist")


def content_for(prompt_type: str, version: Optional[int] = None) -> str:
    """Read a prompt version without touching the database."""
    versions = available_versions(prompt_type)
    if not versions:
        raise FileNotFoundError(f"No prompt seed found for {prompt_type}")
    selected = versions[-1] if version is None else int(version)
    return _path_for_version(prompt_type, selected).read_text(encoding="utf-8")


def get_prompt(prompt_type: str, version: Optional[int] = None) -> Dict[str, object]:
    """Return prompt metadata and content for API/CLI consumers."""
    versions = available_versions(prompt_type)
    if not versions:
        raise FileNotFoundError(f"No prompt seed found for {prompt_type}")
    selected = versions[-1] if version is None else int(version)
    path = _path_for_version(prompt_type, selected)
    content = path.read_text(encoding="utf-8")
    return {
        "prompt_type": prompt_type,
        "name": PROMPT_SEEDS[prompt_type]["name"],
        "version": selected,
        "source": path.relative_to(_base_dir()).as_posix(),
        "sha256": content_hash(content),
        "content": content,
    }


def get_prompt_content(prompt_type: str, default: str = "", version: Optional[int] = None, **fmt) -> str:
    """Return registered content, optionally formatting named placeholders."""
    try:
        content = content_for(prompt_type, version=version)
    except (FileNotFoundError, KeyError):
        content = default
    if fmt:
        try:
            content = content.format(**fmt)
        except (KeyError, IndexError, ValueError):
            # Prompts often contain JSON braces; formatting is best-effort.
            pass
    return content


def validate_registry() -> Dict[str, Dict[str, object]]:
    """Validate all seeds and return deterministic metadata for CI."""
    results = {}
    for prompt_type in PROMPT_SEEDS:
        try:
            metadata = get_prompt(prompt_type)
            results[prompt_type] = {
                "ok": bool(metadata["content"].strip()),
                "version": metadata["version"],
                "source": metadata["source"],
                "sha256": metadata["sha256"],
            }
        except (FileNotFoundError, KeyError, OSError) as exc:
            results[prompt_type] = {"ok": False, "error": str(exc)}
    return results
