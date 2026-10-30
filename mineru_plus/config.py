"""Configuration of the external components.

The config file is a JSON object with one entry per role. Each entry names a backend and gives that backend's options:

    {"primary_reader": {"backend": "command", "command": ["mineru", "-p", "{pdf}", "-o", "{out}"]}, ...}

Roles: primary_reader, second_reader, decision_judge, page_judge (the backends of each role are listed in
mineru_plus/backends/__init__.py). Keys starting with "_" are comments and are ignored. A credential is never a value in
this file: an option such as "api_key_env" names the environment variable that holds it.

The file is looked up in this order: the path given to load() (the --config option), the variable MINERU_PLUS_CONFIG,
then mineru_plus.json in the working directory.
"""
import json, os
from pathlib import Path

ROLES = ("primary_reader", "second_reader", "decision_judge", "page_judge")
ENV = "MINERU_PLUS_CONFIG"
DEFAULT_NAME = "mineru_plus.json"
_loaded = None          # (path, document) once a config file has been read


class ConfigError(RuntimeError):
    """A missing or invalid setting. The message names the role and the config file."""


class Spec(dict):
    """The options of one role, with the role and the file they came from (for the error messages)."""

    def __init__(self, role, path, data):
        super().__init__(data)
        self.role, self.path = role, path

    def fail(self, msg):
        return ConfigError(f"role '{self.role}' in {self.path}: {msg}")

    def require(self, key):
        v = self.get(key)
        if v is None or v == "":
            raise self.fail(f"option '{key}' is required")
        return v

    def secret(self, key):
        """The value of the environment variable that option `key` names; None when the option is absent."""
        name = self.get(key)
        if name is None:
            return None
        if not isinstance(name, str) or not name:
            raise self.fail(f"'{key}' must be the name of an environment variable")
        value = os.environ.get(name)
        if not value:
            raise self.fail(f"'{key}' names the environment variable {name}, which is not set")
        return value


def find(path=None):
    if path:
        return Path(path)
    if os.environ.get(ENV):
        return Path(os.environ[ENV])
    here = Path.cwd() / DEFAULT_NAME
    if here.is_file():
        return here
    user = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mineru_plus" / "config.json"
    return user if user.is_file() else here


def load(path=None):
    """Read the config file; returns its path."""
    global _loaded
    p = find(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {p} (pass --config PATH, set {ENV}, create {DEFAULT_NAME} "
                          "in the working directory or ~/.config/mineru_plus/config.json; config.example.json shows "
                          "the format)")
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ConfigError(f"config file {p} is not valid JSON: {e}")
    if not isinstance(doc, dict):
        raise ConfigError(f"config file {p} must hold a JSON object with one entry per role")
    unknown = [k for k in doc if not k.startswith("_") and k not in ROLES]
    if unknown:
        raise ConfigError(f"config file {p} has unknown role(s) {unknown}; the roles are {list(ROLES)}")
    _loaded = (p, doc)
    return p


def role(name):
    """The Spec of one role; ConfigError when the role is not configured."""
    if _loaded is None:
        load()
    p, doc = _loaded
    entry = doc.get(name)
    if entry is None:
        raise ConfigError(f"role '{name}' is not configured in {p}; add an entry with a \"backend\" name "
                          "(config.example.json shows the options)")
    if not isinstance(entry, dict) or not entry.get("backend"):
        raise ConfigError(f"role '{name}' in {p} must be an object with a \"backend\" name")
    return Spec(name, p, entry)


def reset():
    global _loaded
    _loaded = None
