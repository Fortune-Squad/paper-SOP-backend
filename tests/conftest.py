"""conftest.py — mock heavy third-party deps so tests don't need real API keys."""
import sys
from unittest.mock import MagicMock

_MOCK_MODULES = [
    "google", "google.generativeai", "google.ai", "google.ai.generativelanguage",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "chromadb", "chromadb.config", "chromadb.api",
    "tiktoken", "openai",
    "anthropic",
]
for _mod in _MOCK_MODULES:
    sys.modules[_mod] = MagicMock()

# Standalone test scripts that use sys.exit() and module-level execution
# — not compatible with pytest collection.
# v4.0/ tests are manual integration tests requiring a real project on disk.
collect_ignore = ["test_v12_devspec.py"]
collect_ignore_glob = ["v4.0/*"]
