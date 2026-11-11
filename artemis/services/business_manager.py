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

"""Chat Persona & Business Assistant Engine for Artemis.

Provides dynamic brand and casual personas, multilingual language mirroring (English, Hindi, Hinglish),
in-memory business knowledge base (FAQs, pricing, policies), and risk-based severity escalation
for customer interactions, alongside authentic, warm, human-like casual chatting for personal interactions.
"""

import json
import os
from pathlib import Path
import re
from typing import Any

from artemis.config import WORKSPACE_ROOT
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_BUSINESS_CONFIG = Path(WORKSPACE_ROOT) / "config" / "business_config.json"
DEFAULT_BUSINESS_EXAMPLE = Path(WORKSPACE_ROOT) / "config" / "business_config.json.example"

DEFAULT_CASUAL_CONFIG = Path(WORKSPACE_ROOT) / "config" / "casual_config.json"
DEFAULT_CASUAL_EXAMPLE = Path(WORKSPACE_ROOT) / "config" / "casual_config.json.example"


class PersonaManager:
    """Manages Business and Casual personas, FAQs, language mirroring, and escalation rules."""

    def __init__(
        self,
        business_config_path: Path | None = None,
        casual_config_path: Path | None = None,
    ):
        self.business_config_path = business_config_path or DEFAULT_BUSINESS_CONFIG
        self.business_example_path = DEFAULT_BUSINESS_EXAMPLE
        self._last_b_mtime: float = 0.0
        self._business_config: dict[str, Any] = {}

        self.casual_config_path = casual_config_path or DEFAULT_CASUAL_CONFIG
        self.casual_example_path = DEFAULT_CASUAL_EXAMPLE
        self._last_c_mtime: float = 0.0
        self._casual_config: dict[str, Any] = {}

        self._load_business()
        self._load_casual()

    def _load_business(self) -> None:
        """Load business configuration from JSON storage with fallback to example template."""
        target = self.business_config_path if self.business_config_path.exists() else self.business_example_path
        if target.exists():
            try:
                self._last_b_mtime = target.stat().st_mtime
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._business_config = data
                    logger.info(
                        f"Loaded Business Assistant configuration for '{self._business_config.get('business_name', 'Business')}'. "
                        f"Enabled: {self._business_config.get('enabled', True)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load business configuration from {target}: {e}")
        else:
            self._business_config = {
                "enabled": True,
                "business_name": "My Business",
                "brand_tone": "Warm, professional, polite, helpful, and concise",
                "supported_languages": ["English", "Hindi", "Hinglish"],
                "language_behavior": "auto_mirror",
                "knowledge_base": {},
                "escalation_policy": {},
            }

    def _load_casual(self) -> None:
        """Load casual chat configuration from JSON storage with fallback to example template."""
        target = self.casual_config_path if self.casual_config_path.exists() else self.casual_example_path
        if target.exists():
            try:
                self._last_c_mtime = target.stat().st_mtime
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._casual_config = data
                    logger.info(
                        f"Loaded Casual Chat Persona configuration for '{self._casual_config.get('user_name', 'User')}'. "
                        f"Enabled: {self._casual_config.get('enabled', True)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load casual configuration from {target}: {e}")
        else:
            self._casual_config = {
                "enabled": True,
                "user_name": "User",
                "casual_tone": "Warm, natural, informal, friendly, authentic",
                "language_mirroring": {"enabled": True, "languages": ["English", "Hindi", "Hinglish"]},
                "style_rules": [],
                "safety_boundaries": [],
            }

    def _check_reload(self) -> None:
        """Reload configurations if files have changed on disk."""
        target_b = self.business_config_path if self.business_config_path.exists() else self.business_example_path
        if target_b.exists():
            try:
                if target_b.stat().st_mtime > self._last_b_mtime:
                    self._load_business()
            except Exception:
                pass

        target_c = self.casual_config_path if self.casual_config_path.exists() else self.casual_example_path
        if target_c.exists():
            try:
                if target_c.stat().st_mtime > self._last_c_mtime:
                    self._load_casual()
            except Exception:
                pass

    # Business Config API
    def get_config(self) -> dict[str, Any]:
        """Return the active business configuration (backwards compatibility)."""
        self._check_reload()
        return dict(self._business_config)

    def get_business_config(self) -> dict[str, Any]:
        return self.get_config()

    def update_config(self, new_data: dict[str, Any]) -> dict[str, Any]:
        """Update and persist business configuration to disk."""
        self._business_config.update(new_data)
        try:
            self.business_config_path.parent.mkdir(parents=True, exist_ok=True)
            self.business_config_path.write_text(
                json.dumps(self._business_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._last_b_mtime = self.business_config_path.stat().st_mtime
            logger.info("Saved updated business configuration to disk.")
        except Exception as e:
            logger.error(f"Failed to save business configuration: {e}")
        return dict(self._business_config)

    # Casual Config API
    def get_casual_config(self) -> dict[str, Any]:
        self._check_reload()
        return dict(self._casual_config)

    def update_casual_config(self, new_data: dict[str, Any]) -> dict[str, Any]:
        self._casual_config.update(new_data)
        try:
            self.casual_config_path.parent.mkdir(parents=True, exist_ok=True)
            self.casual_config_path.write_text(
                json.dumps(self._casual_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._last_c_mtime = self.casual_config_path.stat().st_mtime
            logger.info("Saved updated casual configuration to disk.")
        except Exception as e:
            logger.error(f"Failed to save casual configuration: {e}")
        return dict(self._casual_config)

    def is_business_enabled(self) -> bool:
        self._check_reload()
        return bool(self._business_config.get("enabled", True))

    def is_casual_enabled(self) -> bool:
        self._check_reload()
        return bool(self._casual_config.get("enabled", True))

    def is_enabled(self) -> bool:
        return self.is_business_enabled() or self.is_casual_enabled()

    def is_explicit_business_mode(self, goal: str) -> bool:
        """Detect explicit business mode tags or directives."""
        if not goal:
            return False
        pattern = r"\[MODE:\s*BUSINESS\]|\[BUSINESS\s+MODE\]|\bbusiness\s+model\b|\bbusiness\s+mode\b|\bbrand\s+persona\b"
        return bool(re.search(pattern, goal, re.IGNORECASE))

    def is_explicit_casual_mode(self, goal: str) -> bool:
        """Detect explicit casual mode tags or directives."""
        if not goal:
            return False
        pattern = r"\[MODE:\s*CASUAL\]|\[CASUAL\s+MODE\]|\bcasual\s+model\b|\bcasual\s+mode\b|\bcasual\s+persona\b|\bcasual\s+chat\b|\bchat\s+casually\b"
        return bool(re.search(pattern, goal, re.IGNORECASE))

    def is_customer_chat_intent(self, goal: str) -> bool:
        """Detect whether a task goal involves customer/business communication."""
        if not goal:
            return False
        if self.is_explicit_business_mode(goal):
            return True
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
            r"\bpricing\b",
            r"\brefund\b",
            r"\bchat\s+with\s+(?:the\s+)?customer\b",
            r"\breply\s+to\s+(?:the\s+)?customer\b",
            r"\bhandle\s+customer\b",
        ]
        pattern = "|".join(keywords)
        return bool(re.search(pattern, goal, re.IGNORECASE))

    def is_casual_chat_intent(self, goal: str) -> bool:
        """Detect whether a task goal involves personal/casual chatting."""
        if not goal:
            return False
        if self.is_explicit_casual_mode(goal):
            return True
        # If explicit business was requested, do not treat as casual
        if self.is_explicit_business_mode(goal):
            return False

        keywords = [
            r"\bsis\b",
            r"\bsister\b",
            r"\bbro\b",
            r"\bbrother\b",
            r"\bfriend\b",
            r"\bfriends\b",
            r"\bfamily\b",
            r"\bmom\b",
            r"\bdad\b",
            r"\bnormal\s+chat\b",
            r"\btalk\s+like\s+a\s+human\b",
            r"\bcasual\s+tone\b",
            r"\bpersonal\s+chat\b",
            r"\bchat\s+with\s+(?!customer\b|client\b)",
        ]
        pattern = "|".join(keywords)
        return bool(re.search(pattern, goal, re.IGNORECASE))

    def build_business_guide_prompt(self) -> str:
        """Construct a structured prompt guiding Artemis on brand voice, FAQs, and escalation."""
        self._check_reload()
        cfg = self._business_config
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

    def build_casual_guide_prompt(self) -> str:
        """Construct a structured prompt guiding Artemis on authentic, natural human chatting."""
        self._check_reload()
        cfg = self._casual_config
        user_name = cfg.get("user_name", "User")
        c_tone = cfg.get("casual_tone", "Warm, natural, informal, friendly, authentic")
        rules = cfg.get("style_rules", [])
        rules_text = "\n".join(f"   - {r}" for r in rules) if rules else (
            "   - Text like a real human friend or sibling chatting on WhatsApp.\n"
            "   - Keep sentences natural, short (1-2 sentences), and casual.\n"
            "   - NEVER use corporate or robotic greetings (e.g. 'Greetings', 'I hope this finds you well').\n"
            "   - Read the last 3-5 messages in the chat before replying to maintain context."
        )

        return (
            f"\n\n{'=' * 60}\n"
            f"[CASUAL CHAT PERSONA INSTRUCTIONS - Chatting on Behalf of {user_name}]:\n"
            f"You are texting a personal contact (friend / sister / family) on behalf of {user_name}.\n"
            f"Act like a real human, NOT a robotic AI or corporate assistant:\n\n"
            f"1. CASUAL HUMAN TONE:\n"
            f"   - Tone: {c_tone}\n"
            f"{rules_text}\n\n"
            f"2. CONTEXT AWARENESS & MULTI-TURN FLOW:\n"
            f"   - BEFORE typing your message, read the last 3-5 messages in the chat.\n"
            f"   - Understand what the other person is asking or talking about and react directly to it.\n"
            f"   - DO NOT just send one cold, isolated sentence and immediately declare the task completed.\n"
            f"   - If they asked a question or shared news, reply warmly and naturally (e.g. 'Arre haan! Tu bata kya plan hai?').\n\n"
            f"3. LANGUAGE & VIBE MIRRORING:\n"
            f"   - If they text in Hinglish: reply in natural, friendly Hinglish.\n"
            f"   - If they text in Hindi: reply in natural conversational Hindi.\n"
            f"   - If they text in English: reply in relaxed, casual English.\n"
            f"   - Use natural emojis casually (👍, 😂, 😊, 😅) where fitting.\n\n"
            f"4. SAFETY BOUNDARIES:\n"
            f"   - Never share passwords, bank details, OTPs, or agree to financial transactions.\n"
            f"{'=' * 60}\n"
        )

    def enrich_task_goal(self, goal: str, persona: str | None = None) -> str:
        """Enrich a task goal based on requested or detected persona (business vs casual)."""
        if not goal:
            return goal

        # Idempotency guard: do not double-enrich
        if "[BUSINESS CUSTOMER ASSISTANT INSTRUCTIONS" in goal or "[CASUAL CHAT PERSONA INSTRUCTIONS" in goal:
            return goal

        # 1. Check explicit persona parameter or tags
        persona_lower = (persona or "").strip().lower()

        if persona_lower == "casual" or self.is_explicit_casual_mode(goal):
            if self.is_casual_enabled():
                guide = self.build_casual_guide_prompt()
                logger.info("Enriched task goal with CASUAL CHAT persona guidelines.")
                return f"{goal.strip()}{guide}"

        if persona_lower == "business" or self.is_explicit_business_mode(goal):
            if self.is_business_enabled():
                guide = self.build_business_guide_prompt()
                logger.info(f"Enriched task goal with BUSINESS guidelines for '{self._business_config.get('business_name')}'.")
                return f"{goal.strip()}{guide}"

        # 2. Check intent keywords (business priority if customer-related)
        if self.is_customer_chat_intent(goal):
            if self.is_business_enabled():
                guide = self.build_business_guide_prompt()
                logger.info(f"Enriched task goal with BUSINESS guidelines for '{self._business_config.get('business_name')}'.")
                return f"{goal.strip()}{guide}"

        if self.is_casual_chat_intent(goal):
            if self.is_casual_enabled():
                guide = self.build_casual_guide_prompt()
                logger.info("Enriched task goal with CASUAL CHAT persona guidelines.")
                return f"{goal.strip()}{guide}"

        return goal


# Singleton instance
persona_manager = PersonaManager()

# Backwards compatibility alias
BusinessAssistantManager = PersonaManager
business_assistant_manager = persona_manager
