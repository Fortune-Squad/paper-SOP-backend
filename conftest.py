"""Root conftest — mock heavy third-party deps before any test collection."""
import sys
from unittest.mock import MagicMock

_MOCK_MODULES = [
    "google", "google.generativeai", "google.ai", "google.ai.generativelanguage",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "chromadb", "chromadb.config", "chromadb.api",
    "tiktoken", "openai",
]
for _mod in _MOCK_MODULES:
    sys.modules[_mod] = MagicMock()
