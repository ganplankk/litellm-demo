"""Small helpers for the lab's generated, single-line KEY=value files."""

import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def read_env(path):
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def private_write(path, text):
    """Replace a secret file atomically, with mode 0600 on Linux."""
    fd, temporary = tempfile.mkstemp(prefix=".lab-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def replace_values(text, updates):
    lines = []
    remaining = dict(updates)
    for line in text.splitlines():
        key = line.split("=", 1)[0].strip()
        if not line.lstrip().startswith("#") and key in remaining:
            line = key + "=" + remaining.pop(key)
        lines.append(line)
    lines.extend(key + "=" + value for key, value in remaining.items())
    return "\n".join(lines) + "\n"
