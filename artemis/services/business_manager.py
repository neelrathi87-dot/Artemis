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

"""Business Customer Assistant Engine for Artemis.

Provides dynamic brand persona, multilingual language mirroring (English, Hindi, Hinglish),
in-memory business knowledge base (FAQs, pricing, policies), and risk-based severity
escalation (autonomous low-severity responses vs. human owner escalation for high-severity topics).
"""

import json
import os
from pathlib import Path
import re
from typing import Any

from artemis.config import WORKSPACE_ROOT
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG_PATH = Path(WORKSPACE_ROOT) / "config" / "business_config.json"
DEFAULT_EXAMPLE_PATH = Path(WORKSPACE_ROOT) / "config" / "business_config.json.example"


class BusinessAssistantManager:
    """Manages business profile, brand tone, FAQs, and severity escalation rules."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.example_path = DEFAULT_EXAMPLE_PATH
        self._last_mtime: float = 0.0
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load business configuration from JSON storage with fallback to example template."""
        target_file = self.config_path if self.config_path.exists() else self.example_path
        if target_file.exists():
            try:
                self._last_mtime = target_file.stat().st_mtime
                data = json.loads(target_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._config = data
                    logger.info(
                        f"Loaded Business Assistant configuration for '{self._config.get('business_name', 'Business')}'. "
                        f"Enabled: {self._config.get('enabled', True)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load business configuration from {target_file}: {e}")
        else:
            self._config = {
                "enabled": True,
                "business_name": "My Business",
                "brand_tone": "Warm, professional, polite, helpful, and concise",
                "supported_languages": ["English", "Hindi", "Hinglish"],
                "language_behavior": "auto_mirror",
                "knowledge_base": {},
                "escalation_policy": {},
            }

    def _check_reload(self) -> None:
        """Reload configuration if the file has changed on disk."""
        target_file = self.config_path if self.config_path.exists() else self.example_path
        if target_file.exists():
            try:
                mtime = target_file.stat().st_mtime
                if mtime > self._last_mtime:
                    self._load()
            except Exception:
                pass

    def get_config(self) -> dict[str, Any]:
        """Return the current active business configuration."""
        self._check_reload()
        return dict(self._config)

    def update_config(self, new_data: dict[str, Any]) -> dict[str, Any]:
        """Update and persist business configuration to disk."""
        self._config.update(new_data)
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(self._config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._last_mtime = self.config_path.stat().st_mtime
            logger.info("Saved updated business configuration to disk.")
        except Exception as e:
            logger.error(f"Failed to save business configuration: {e}")
        return dict(self._config)

    def is_enabled(self) -> bool:
        self._check_reload()
        return bool(self._config.get("enabled", True))

    def is_customer_chat_intent(self, goal: str) -> bool:
        """Detect whether a task goal involves customer/business communication."""
        if not goal:
            return False
        keywords = [
            r"\bcustomer\b",
            r"\bclient\b",
            r"\bbusiness\b",
            r"\bbuyer\b",
            r"\binquiry\b",
            r"\binquiries\b",
            r"\borders?\b",
            r"\bsupport\b",
            r"\bproduct\s+price\b",
            r"\bchat\s+with\s+(?:the\s+)?customer\b",
            r"\breply\s+to\s+(?:the\s+)?customer\b",
            r"\bhandle\s+customer\b",
        ]
        pattern = "|".join(keywords)
        return bool(re.search(pattern, goal, re.IGNORECASE))

    def build_business_guide_prompt(self) -> str:
        """Construct a structured prompt guiding Artemis on brand voice, FAQs, and escalation."""
        self._check_reload()
        cfg = self._config
        b_name = cfg.get("business_name", "My Business")
        b_tone = cfg.get("brand_tone", "Warm, professional, polite, helpful, and concise")
        kb = cfg.get("knowledge_base", {})
        esc = cfg.get("escalation_policy", {})
        high_severity = esc.get("severity_levels", {}).get("high_escalate_to_owner", [])
        holding_msg = esc.get(
            "holding_message_for_customer",
            "Thank you for reaching out! Let me quickly check this with the owner and get back to you shortly.",
        )

        kb_formatted = []
        for k, v in kb.items():
            title = k.replace("_", " ").title()
            if isinstance(v, list):
                items = "\n".join(f"  - {json.dumps(item, ensure_ascii=False)}" for item in v)
                kb_formatted.append(f"• {title}:\n{items}")
            elif isinstance(v, dict):
                items = "\n".join(f"  - {sub_k}: {sub_v}" for sub_k, sub_v in v.items())
                kb_formatted.append(f"• {title}:\n{items}")
            else:
                kb_formatted.append(f"• {title}: {v}")
        kb_text = "\n".join(kb_formatted) if kb_formatted else "No specific knowledge base entries provided."

        high_sev_items = "\n".join(f"  - {item.replace('_', ' ').title()}" for item in high_severity) if high_severity else "  - Discounts/bargaining, refunds, complaints, or unknown questions."

        return (
            f"\n\n{'=' * 60}\n"
            f"[BUSINESS CUSTOMER ASSISTANT INSTRUCTIONS for '{b_name}']:\n"
            f"You are representing '{b_name}'. Follow these strict communication principles:\n\n"
            f"1. BRAND TONE & STYLE:\n"
            f"   - Tone: {b_tone}\n"
            f"   - Keep text messages short (1-2 sentences), conversational, and friendly.\n"
            f"   - Avoid robotic, overly formal corporate jargon (e.g. do not say 'Greetings esteemed client').\n\n"
            f"2. LANGUAGE MIRRORING:\n"
            f"   - Automatically detect the customer's language and reply in the EXACT same language.\n"
            f"   - If the customer texts in English: reply in English.\n"
            f"   - If the customer texts in Hindi/Hinglish (e.g. 'price kitna hai?'): reply in natural Hinglish (e.g. 'Hello! Iska price...').\n\n"
            f"3. BUSINESS KNOWLEDGE BASE (Verified Facts):\n"
            f"{kb_text}\n\n"
            f"4. SEVERITY & ESCALATION RULES:\n"
            f"   - 🟢 LOW SEVERITY (Answer Autonomously): Answer verified information directly from the Knowledge Base above (hours, standard price, address, delivery policy).\n"
            f"   - 🔴 HIGH SEVERITY (MUST ESCALATE TO OWNER):\n"
            f"{high_sev_items}\n"
            f"   - If an inquiry involves a High Severity topic or information you do NOT know with 100% certainty:\n"
            f"     DO NOT guess or invent pricing or policy! Send this polite holding message:\n"
            f"     \"{holding_msg}\"\n"
            f"     Then report task status with notification to the owner.\n"
            f"{'=' * 60}\n"
        )

    def enrich_task_goal(self, goal: str) -> str:
        """Enrich a task goal if it involves customer communication."""
        if not self.is_enabled() or not goal:
            return goal
        if self.is_customer_chat_intent(goal):
            guide = self.build_business_guide_prompt()
            logger.info(f"Enriched task goal with Business Assistant guidelines for '{self._config.get('business_name')}'.")
            return f"{goal.strip()}{guide}"
        return goal


# Singleton instance
business_assistant_manager = BusinessAssistantManager()
