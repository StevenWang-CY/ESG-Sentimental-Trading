"""
Configuration loading with .env support and ``${ENV_VAR}`` expansion.

Historically ``config/config.yaml`` advertised ``client_id: "${REDDIT_CLIENT_ID}"``
placeholders, but the loader was a bare ``yaml.safe_load`` -- so the placeholder
was never expanded and ``.env`` was never read (``load_dotenv`` lived only in an
archived script). The credential gate then accepted the literal truthy string
``"${REDDIT_CLIENT_ID}"`` as a valid credential.

This module fixes that:

* :func:`load_environment` loads ``.env`` once (if python-dotenv is installed).
* :func:`load_config` loads YAML and recursively expands ``${VAR}`` placeholders
  from the environment (unset placeholders expand to ``""`` so credential gates
  fail closed instead of sending a literal placeholder to an API).
* :func:`resolve_credential` resolves a config value the same way the fetchers
  do (treat a ``${...}`` placeholder or empty value as unset and fall back to
  ``os.environ``), returning ``None`` when truly unset.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import yaml

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:  # python-dotenv is a hard dependency, but degrade gracefully
    _DOTENV_AVAILABLE = False

_PLACEHOLDER_RE = re.compile(r"^\$\{([^}^{]+)\}$")
_INLINE_RE = re.compile(r"\$\{([^}^{]+)\}")

_ENV_LOADED = False


def load_environment(dotenv_path: Optional[str] = None) -> None:
    """Load variables from a ``.env`` file into ``os.environ`` exactly once.

    Safe to call repeatedly and safe if python-dotenv is not installed.
    """
    global _ENV_LOADED
    if _ENV_LOADED or not _DOTENV_AVAILABLE:
        _ENV_LOADED = True
        return
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        load_dotenv()  # searches CWD and parents for .env
    _ENV_LOADED = True


def _expand_value(value: Any) -> Any:
    """Recursively expand ``${VAR}`` placeholders in strings/dicts/lists.

    Unset variables expand to an empty string so downstream truthiness checks
    treat them as "not configured" rather than passing the literal placeholder.
    """
    if isinstance(value, str):
        return _INLINE_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_value(v) for v in value]
    return value


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load YAML config, after loading ``.env`` and expanding ``${ENV}`` refs."""
    load_environment()
    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
    return _expand_value(config)


def is_unset(value: Optional[str]) -> bool:
    """True if a credential value is missing, empty, or an unexpanded placeholder."""
    if value is None:
        return True
    value = str(value).strip()
    if not value:
        return True
    return bool(_PLACEHOLDER_RE.match(value))


def resolve_credential(value: Optional[str], env_var: Optional[str] = None) -> Optional[str]:
    """Resolve a credential value, falling back to the environment.

    If ``value`` is empty or a ``${VAR}`` placeholder, read ``env_var`` (or the
    variable named inside the placeholder) from the environment. Returns the
    resolved credential, or ``None`` if it remains unset.
    """
    load_environment()
    if value is not None:
        text = str(value).strip()
        match = _PLACEHOLDER_RE.match(text)
        if match:
            env_var = env_var or match.group(1)
        elif text:
            return text  # already a concrete value
    if env_var:
        resolved = os.environ.get(env_var)
        if resolved and resolved.strip():
            return resolved.strip()
    return None
