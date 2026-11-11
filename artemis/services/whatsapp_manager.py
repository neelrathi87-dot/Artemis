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

"""WhatsApp Locked Chats Manager and Intent Enrichment Engine for Artemis.

Automatically identifies locked WhatsApp contacts, manages the locked contacts registry,
and enriches user task prompts so the agent seamlessly accesses hidden locked chats
using the user's configured secret code without requiring repetitive verbose user prompts.
"""

import json
import os
from pathlib import Path
import re
from typing import Any

from artemis.config import WORKSPACE_ROOT
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG_PATH = Path(WORKSPACE_ROOT) / "config" / "whatsapp_locked_chats.json"


class WhatsAppLockedChatManager:
    """Manages WhatsApp locked chats registry and dynamic prompt enrichment."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._password: str = os.environ.get("WHATSAPP_LOCKED_CHAT_PASSWORD", "")
        self._locked_contacts: set[str] = set()
        self._last_mtime: float = 0.0
        self._load()

    def _load(self) -> None:
        """Load locked chat settings from JSON storage and environment."""
        env_pwd = os.environ.get("WHATSAPP_LOCKED_CHAT_PASSWORD")
        if env_pwd:
            self._password = env_pwd.strip()

        if self.config_path.exists():
            try:
                mtime = self.config_path.stat().st_mtime
                self._last_mtime = mtime
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if "password" in data and not env_pwd:
                        self._password = str(data["password"]).strip()
                    contacts = data.get("locked_contacts", [])
                    if isinstance(contacts, list):
                        self._locked_contacts = {str(c).strip().lower() for c in contacts if str(c).strip()}
                    logger.info(
                        f"Loaded WhatsApp locked chats config: {len(self._locked_contacts)} locked contact(s)."
                    )
            except Exception as e:
                logger.warning(f"Failed to load WhatsApp locked chats config: {e}")
        else:
            self._save()

    def _check_reload(self) -> None:
        """Reload configuration if the file has changed on disk."""
        if self.config_path.exists():
            try:
                mtime = self.config_path.stat().st_mtime
                if mtime > self._last_mtime:
                    self._load()
            except Exception:
                pass

    def _save(self) -> None:
        """Persist settings to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "password": self._password,
                "locked_contacts": sorted(list(self._locked_contacts)),
            }
            self.config_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save WhatsApp locked chats config: {e}")

    @property
    def password(self) -> str:
        self._check_reload()
        return self._password

    @password.setter
    def password(self, val: str) -> None:
        if val:
            self._password = val.strip()
            self._save()

    def get_locked_contacts(self) -> list[str]:
        self._check_reload()
        return sorted(list(self._locked_contacts))

    def is_locked_contact(self, name: str) -> bool:
        if not name:
            return False
        self._check_reload()
        clean = name.strip().lower()
        return clean in self._locked_contacts

    def add_locked_contact(self, name: str) -> bool:
        if not name:
            return False
        self._check_reload()
        clean = name.strip().lower()
        if clean not in self._locked_contacts:
            self._locked_contacts.add(clean)
            self._save()
            logger.info(f"Added '{name}' to WhatsApp locked contacts registry.")
            return True
        return False

    def remove_locked_contact(self, name: str) -> bool:
        if not name:
            return False
        self._check_reload()
        clean = name.strip().lower()
        if clean in self._locked_contacts:
            self._locked_contacts.remove(clean)
            self._save()
            logger.info(f"Removed '{name}' from WhatsApp locked contacts registry.")
            return True
        return False

    def enrich_goal(self, raw_goal: str) -> str:
        """Detect and enrich user tasks involving WhatsApp locked chats."""
        if not raw_goal or not raw_goal.strip():
            return raw_goal

        self._check_reload()
        goal = raw_goal.strip()
        pwd = self._password

        # 1. Pattern: Direct user instructions to register a contact as locked
        # E.g.: "Alice is a locked chat", "add Alice to locked chats", "mark Alice as locked"
        reg_match = re.search(
            r"\b(?:add|mark|set|register)\s+([a-zA-Z0-9_\-\s]+?)\s+(?:as|to|in)\s+(?:whatsapp\s+)?locked\s+chats?\b",
            goal,
            re.IGNORECASE,
        )
        if not reg_match:
            reg_match = re.search(
                r"\b([a-zA-Z0-9_\-]+)\s+is\s+(?:a\s+)?locked\s+chat\b",
                goal,
                re.IGNORECASE,
            )

        if reg_match:
            contact = reg_match.group(1).strip()
            # Filter out generic words
            if contact.lower() not in {"this", "the", "a", "chat", "chats", "whatsapp"}:
                self.add_locked_contact(contact)

        # 2. Pattern: Direct user instructions to remove from locked chats
        # E.g.: "remove Alice from locked chats", "Alice is not a locked chat"
        unreg_match = re.search(
            r"\b(?:remove|delete)\s+([a-zA-Z0-9_\-\s]+?)\s+from\s+(?:whatsapp\s+)?locked\s+chats?\b",
            goal,
            re.IGNORECASE,
        )
        if unreg_match:
            contact = unreg_match.group(1).strip()
            if contact.lower() not in {"this", "the", "a", "chat", "chats", "whatsapp"}:
                self.remove_locked_contact(contact)

        # 3. Pattern: Request to LOCK a chat on device
        # E.g.: "lock chat with Alice", "lock Alice chat", "lock the chat of Alice"
        lock_cmd_match = re.search(
            r"\block\s+(?:the\s+)?chat\s+(?:with|for|of)\s+([a-zA-Z0-9_\-]+)\b",
            goal,
            re.IGNORECASE,
        )
        if not lock_cmd_match:
            lock_cmd_match = re.search(
                r"\block\s+([a-zA-Z0-9_\-]+)(?:'s)?\s+chat\b",
                goal,
                re.IGNORECASE,
            )

        if lock_cmd_match:
            target_contact = lock_cmd_match.group(1).strip()
            if target_contact.lower() not in {"device", "phone", "screen", "this", "the"}:
                self.add_locked_contact(target_contact)
                return (
                    f"In WhatsApp, lock the chat with {target_contact}.\n\n"
                    f"[WhatsApp Lock Chat Execution Guide]:\n"
                    f"1. Open WhatsApp (package com.whatsapp).\n"
                    f"2. Locate and open the chat with '{target_contact}'.\n"
                    f"3. Tap '{target_contact}' (contact name/header) at the top to open Chat Info.\n"
                    f"4. Scroll down to find 'Chat lock' and tap it.\n"
                    f"5. Toggle ON 'Lock this chat with fingerprint / passcode' or 'Secret code'.\n"
                    f"6. When prompted for PIN / password / secret code, enter '{pwd}'.\n"
                    f"7. Confirm that the chat is now locked and return to home screen or WhatsApp."
                )

        # 4. Pattern: Request to UNLOCK a chat on device
        # E.g.: "unlock chat with Alice", "unlock Alice chat", "unlock the chat of Alice"
        unlock_cmd_match = re.search(
            r"\bunlock\s+(?:the\s+)?chat\s+(?:with|for|of)\s+([a-zA-Z0-9_\-]+)\b",
            goal,
            re.IGNORECASE,
        )
        if not unlock_cmd_match:
            unlock_cmd_match = re.search(
                r"\bunlock\s+([a-zA-Z0-9_\-]+)(?:'s)?\s+chat\b",
                goal,
                re.IGNORECASE,
            )

        if unlock_cmd_match:
            target_contact = unlock_cmd_match.group(1).strip()
            if target_contact.lower() not in {"device", "phone", "screen", "this", "the"}:
                self.remove_locked_contact(target_contact)
                return (
                    f"In WhatsApp, unlock the locked chat with {target_contact}.\n\n"
                    f"[WhatsApp Unlock Chat Execution Guide]:\n"
                    f"1. Open WhatsApp (package com.whatsapp).\n"
                    f"2. In Chats tab, tap the search bar/icon at the top and type the secret code '{pwd}' to reveal 'Locked chats'.\n"
                    f"3. Tap 'Locked chats' in search results (or enter passcode '{pwd}' if prompted).\n"
                    f"4. Tap '{target_contact}' to open the chat.\n"
                    f"5. Tap '{target_contact}' (contact name/header) at the top to open Chat Info.\n"
                    f"6. Scroll down to 'Chat lock' and tap it.\n"
                    f"7. Toggle OFF 'Lock this chat with fingerprint / passcode'.\n"
                    f"8. Confirm the chat is unlocked and moved back to regular chats."
                )

        # 5. Check if the goal mentions ANY known locked contact
        # E.g.: "message Alice hello", "text Alice hey are you coming", "send Alice a message"
        for contact in self._locked_contacts:
            # Word boundary check for the contact name
            if re.search(rf"\b{re.escape(contact)}\b", goal, re.IGNORECASE):
                # Check if it already contains the secret code guide
                if f"secret code '{pwd}'" in goal or f"code '{pwd}'" in goal:
                    return goal

                # Extract message if present
                logger.info(
                    f"Detected known WhatsApp locked contact '{contact}' in goal: '{goal}'. "
                    f"Enriching task with secret code '{pwd}' access guide."
                )

                return (
                    f"{goal}\n\n"
                    f"[WhatsApp Locked Chat Execution Guide for '{contact}']:\n"
                    f"NOTE: '{contact}' is in WhatsApp Locked Chats!\n"
                    f"1. Open WhatsApp (package com.whatsapp).\n"
                    f"2. In Chats tab, tap the search bar / search icon at the top.\n"
                    f"3. Type the secret code '{pwd}' into the search bar to reveal the 'Locked chats' folder.\n"
                    f"4. Tap 'Locked chats' in the search results (enter '{pwd}' if prompted for passcode/fingerprint).\n"
                    f"5. In the Locked chats list, tap '{contact}' to open the conversation.\n"
                    f"6. Proceed with the user's requested action (typing message, reading chat, etc.)."
                )

        return goal


# Singleton instance
whatsapp_locked_chat_manager = WhatsAppLockedChatManager()
