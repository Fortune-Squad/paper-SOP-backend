from __future__ import annotations

import sys


def substitute_command_tokens(command: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in command:
        if token == "@PYTHON@":
            normalized.append(sys.executable)
        else:
            normalized.append(token)
    return normalized
