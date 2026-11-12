# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multi-API Key Pool & Auto-Failover Rotator for LLM Providers.

Allows pooling multiple API keys (e.g. across Google AI Studio projects / accounts)
to multiply free-tier request limits (500 req/day per key) and provide instantaneous,
zero-downtime failover whenever a 429 / RESOURCE_EXHAUSTED rate limit is encountered.
"""

import logging
import os
import re
import threading
import time
from typing import Any

from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


def mask_key(key: str | None) -> str:
    """Mask an API key for safe logging (e.g. AQ.Ab8...wqsA)."""
    if not key:
        return "<none>"
    s = str(key).strip()
    if len(s) <= 10:
        return f"{s[:3]}...{s[-2:]}"
    return f"{s[:7]}...{s[-5:]}"


class GoogleKeyPool:
    """Thread-safe key pool for Google Gemini API keys."""

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: list[str] = []
        self._current_index: int = 0
        self._cooldowns: dict[str, float] = {}  # key -> cooldown_until_timestamp
        self.reload_keys()

    def reload_keys(self) -> list[str]:
        """Scans environment variables and settings to collect and deduplicate valid keys."""
        with self._lock:
            collected: list[str] = []

            def _add_key(k: Any):
                if not k:
                    return
                # Extract raw string if SecretStr
                if hasattr(k, "get_secret_value"):
                    k = k.get_secret_value()
                s = str(k).strip()
                # Split comma or semicolon separated keys
                parts = re.split(r"[,;\s]+", s)
                for part in parts:
                    clean = part.strip()
                    if clean and not self._is_placeholder(clean) and clean not in collected:
                        collected.append(clean)

            # Check explicit environment variables
            _add_key(os.environ.get("GEMINI_API_KEYS"))
            _add_key(os.environ.get("GEMINI_API_KEY"))
            _add_key(os.environ.get("GOOGLE_API_KEY"))

            # Check numbered environment variables: GEMINI_API_KEY_1..9, GOOGLE_API_KEY_1..9
            for i in range(1, 10):
                _add_key(os.environ.get(f"GEMINI_API_KEY_{i}"))
                _add_key(os.environ.get(f"GOOGLE_API_KEY_{i}"))

            # Also check artemis settings if loaded
            try:
                from artemis.config.settings import settings
                _add_key(getattr(settings, "GEMINI_API_KEY", None))
                _add_key(getattr(settings, "GOOGLE_API_KEY", None))
                _add_key(getattr(settings, "GEMINI_API_KEY_2", None))
                _add_key(getattr(settings, "GEMINI_API_KEYS", None))
            except Exception:
                pass

            self._keys = collected
            if self._current_index >= len(self._keys):
                self._current_index = 0

            masked_list = [mask_key(k) for k in self._keys]
            if len(self._keys) > 1:
                logger.info(f"🔑 [KeyPool] Initialized with {len(self._keys)} active Google API keys: {masked_list}")
            return self._keys

    @staticmethod
    def _is_placeholder(val: str) -> bool:
        low = val.lower()
        return (
            low in {"api_key", "your_api_key", "your_gemini_api_key_here", "none", "null", "undefined"}
            or (low.startswith("your_") and low.endswith("_here"))
            or (low.startswith("<") and low.endswith(">"))
            or len(val) < 8
        )

    def get_keys(self) -> list[str]:
        with self._lock:
            return list(self._keys)

    def has_multiple_keys(self) -> bool:
        with self._lock:
            return len(self._keys) > 1

    def get_active_key(self) -> str | None:
        """Returns the current healthy key. If current is cooling down, advances to next."""
        with self._lock:
            if not self._keys:
                return None

            now = time.time()
            # Clean expired cooldowns
            self._cooldowns = {k: ts for k, ts in self._cooldowns.items() if ts > now}

            # Find first non-cooling-down key starting from current_index
            num_keys = len(self._keys)
            for offset in range(num_keys):
                idx = (self._current_index + offset) % num_keys
                k = self._keys[idx]
                if k not in self._cooldowns:
                    self._current_index = idx
                    return k

            # All keys are in cooldown; return the one that expires soonest
            best_key = min(self._keys, key=lambda k: self._cooldowns.get(k, 0))
            return best_key

    def rotate_key(self, failed_key: str | None = None, cooldown_seconds: float = 900.0) -> tuple[str | None, bool]:
        """Marks the failed key as in cooldown and rotates to the next available healthy key.

        Returns (new_key, did_switch).
        """
        with self._lock:
            if not self._keys:
                return None, False

            now = time.time()
            if failed_key and failed_key in self._keys:
                self._cooldowns[failed_key] = now + cooldown_seconds
                logger.warning(
                    f"⚠️ [KeyPool] Marked key {mask_key(failed_key)} as cooling down for {int(cooldown_seconds)}s."
                )

            # Look for next healthy key
            num_keys = len(self._keys)
            for offset in range(1, num_keys + 1):
                idx = (self._current_index + offset) % num_keys
                candidate = self._keys[idx]
                if candidate not in self._cooldowns or self._cooldowns[candidate] <= now:
                    self._current_index = idx
                    new_key = self._keys[idx]
                    logger.info(
                        f"🔄 [KeyPool] Rotated active key to {mask_key(new_key)} (Key {idx + 1} of {num_keys})."
                    )
                    return new_key, (new_key != failed_key)

            # If all are in cooldown, pick the one expiring soonest
            best_key = min(self._keys, key=lambda k: self._cooldowns.get(k, 0))
            self._current_index = self._keys.index(best_key)
            return best_key, (best_key != failed_key)

    def hot_swap_model_client(self, model: Any, new_key: str) -> bool:
        """Injects new_key into a LangChain ChatGoogleGenerativeAI or RunnableBinding instance."""
        if not new_key:
            return False
        try:
            from google.genai import Client

            target = model
            # Unwrap RunnableBinding or wrappers
            while hasattr(target, "bound"):
                target = target.bound
            if hasattr(target, "base_model"):
                target = target.base_model
                while hasattr(target, "bound"):
                    target = target.bound

            if hasattr(target, "client") and hasattr(target, "google_api_key"):
                target.google_api_key = new_key
                target.client = Client(api_key=new_key)
                # Also keep environment in sync for any child processes / probes
                os.environ["GEMINI_API_KEY"] = new_key
                os.environ["GOOGLE_API_KEY"] = new_key
                logger.info(f"✨ [KeyPool] Successfully hot-swapped ChatGoogleGenerativeAI client to key {mask_key(new_key)}!")
                return True
        except Exception as e:
            logger.error(f"❌ [KeyPool] Failed to hot-swap model client: {e}")
        return False


# Global singleton instance
google_key_pool = GoogleKeyPool()
