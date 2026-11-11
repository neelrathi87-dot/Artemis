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

"""Self-Learning Task Memory Engine for Artemis.

Learns, indexes, and fast-replays successful action sequences for repeated tasks,
eliminating repetitive exploration latency and token consumption.
"""

import json
import os
from pathlib import Path
import re
import time
from typing import Any
from artemis.config import WORKSPACE_ROOT
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

SKILLS_FILE_PATH = Path(WORKSPACE_ROOT) / "config" / "learned_skills.json"


class LearnedSkillStore:
    """Persistent storage and retrieval engine for learned task skills."""

    def __init__(self, storage_path: Path | None = None):
        self.storage_path = storage_path or SKILLS_FILE_PATH
        self._skills: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load learned skills from persistent disk storage."""
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._skills = data
                    logger.info(f"Loaded {len(self._skills)} learned skills from {self.storage_path}")
            except Exception as e:
                logger.warning(f"Failed to load learned skills from {self.storage_path}: {e}")
                self._skills = {}
        else:
            self._skills = {}

    def _save(self) -> None:
        """Save learned skills to persistent disk storage."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text(
                json.dumps(self._skills, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save learned skills to {self.storage_path}: {e}")

    @staticmethod
    def normalize_goal(goal: str) -> str:
        """Clean and normalize a goal string for robust semantic matching."""
        if not goal:
            return ""
        # Remove known passphrases, common noise words
        g = goal.lower()
        passphrase = os.environ.get("ARTEMIS_UNLOCK_PASSPHRASE", "").lower()
        if passphrase:
            g = re.sub(re.escape(passphrase), "", g, flags=re.IGNORECASE)
        # Remove punctuation, excess whitespace
        g = re.sub(r"[^\w\s]", " ", g)
        tokens = [w for w in g.split() if w not in {"please", "could", "you", "now", "artemis", "the", "a", "an", "to"}]
        return " ".join(tokens)

    def record_skill(
        self,
        goal: str,
        actions: list[dict[str, Any]],
        summary: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Store or update a learned action sequence for a given task goal."""
        if not goal or not actions:
            return None

        norm_key = self.normalize_goal(goal)
        if not norm_key:
            return None

        now = time.time()
        existing = self._skills.get(norm_key)

        if existing:
            existing["success_count"] = existing.get("success_count", 1) + 1
            existing["last_executed"] = now
            existing["summary"] = summary or existing.get("summary")
            existing["actions"] = actions  # Update with latest proven actions
            skill = existing
            logger.info(f"🧠 [Self-Learning] Updated skill '{goal}' (success count: {skill['success_count']})")
        else:
            skill = {
                "goal": goal,
                "normalized_goal": norm_key,
                "keywords": norm_key.split(),
                "actions": actions,
                "summary": summary,
                "success_count": 1,
                "created_at": now,
                "last_executed": now,
                "session_id": session_id,
            }
            self._skills[norm_key] = skill
            logger.info(f"🧠 [Self-Learning] Learned NEW skill for '{goal}' with {len(actions)} steps!")

        self._save()
        return skill

    def find_matching_skill(self, goal: str) -> dict[str, Any] | None:
        """Find a previously learned skill that matches the current goal."""
        if not goal or not self._skills:
            return None

        norm_input = self.normalize_goal(goal)
        if not norm_input:
            return None

        # 1. Exact normalized match
        if norm_input in self._skills:
            skill = self._skills[norm_input]
            logger.info(f"🧠 [Self-Learning] Exact skill match found for '{goal}' -> '{skill['goal']}'")
            return skill

        input_tokens = set(norm_input.split())
        if not input_tokens:
            return None

        best_skill = None
        best_score = 0.0

        for key, skill in self._skills.items():
            skill_tokens = set(skill.get("keywords", key.split()))
            if not skill_tokens:
                continue

            intersection = input_tokens.intersection(skill_tokens)
            union = input_tokens.union(skill_tokens)
            jaccard = len(intersection) / len(union) if union else 0.0

            # Containment score: if all key words of the skill are in the input
            containment = len(intersection) / len(skill_tokens) if skill_tokens else 0.0

            score = max(jaccard, containment * 0.9)

            if score > best_score:
                best_score = score
                best_skill = skill

        # High confidence match threshold
        if best_skill and best_score >= 0.75:
            logger.info(
                f"🧠 [Self-Learning] High-confidence match ({best_score:.2f}) for '{goal}' -> '{best_skill['goal']}'"
            )
            return best_skill

        return None

    def learn_from_session(self, session_id: str, goal: str) -> dict[str, Any] | None:
        """Extract and learn successful actions from a completed session in the database."""
        if not session_id or not goal:
            return None

        try:
            try:
                from admin_console.database.repositories.step_repository import step_repo
            except ImportError:
                from apps.admin_console.database.repositories.step_repository import step_repo

            steps = step_repo.get_session_steps(session_id)
            if not steps:
                return None

            clean_actions: list[dict[str, Any]] = []

            for st in steps:
                action_taken = st.get("action_taken")
                if not action_taken or not isinstance(action_taken, dict):
                    continue

                action_name = action_taken.get("action") or ""
                # Skip non-device actions or completion reports
                if action_name in {"report_task_status", "llm_retry", "ask_explorer", "read_note", "list_notes"}:
                    continue

                args = action_taken.get("args") or {}
                coords = (
                    action_taken.get("normalized_coordinates")
                    or action_taken.get("coordinates")
                    or args.get("normalized_coordinates")
                    or args.get("coordinate")
                    or args.get("coordinates")
                )

                step_entry: dict[str, Any] = {
                    "action": action_name,
                    "args": dict(args),
                }

                if coords:
                    step_entry["coordinates"] = coords

                if action_taken.get("target_text"):
                    step_entry["target_text"] = action_taken["target_text"]

                if action_taken.get("target_resource_id"):
                    step_entry["target_resource_id"] = action_taken["target_resource_id"]

                clean_actions.append(step_entry)

            if clean_actions:
                return self.record_skill(
                    goal=goal,
                    actions=clean_actions,
                    session_id=session_id,
                )
        except Exception as exc:
            logger.warning(f"Error learning from session {session_id}: {exc}")

        return None

    def get_all_skills(self) -> list[dict[str, Any]]:
        """Return all learned skills sorted by most recently executed."""
        skills = list(self._skills.values())
        skills.sort(key=lambda s: s.get("last_executed", 0), reverse=True)
        return skills

    def format_learned_guide(self, skill: dict[str, Any]) -> str:
        """Format a learned skill into a high-confidence prompt guide for the LLM."""
        lines = [
            f"## 🧠 Learned Skill Memory (Proven Working Recipe):",
            f"You have already successfully mastered this exact task before!",
            f"- Original Task: \"{skill.get('goal')}\"",
            f"- Proven Success Count: {skill.get('success_count', 1)} time(s)",
            f"- Proven Action Sequence:",
        ]
        for idx, act in enumerate(skill.get("actions", []), 1):
            act_name = act.get("action")
            args = act.get("args", {})
            coords = act.get("coordinates")
            target_text = act.get("target_text")
            detail = f"{act_name}("
            arg_strs = []
            for k, v in args.items():
                if k not in {"coordinates", "normalized_coordinates"}:
                    arg_strs.append(f"{k}={repr(v)}")
            if coords:
                arg_strs.append(f"coordinates={coords}")
            if target_text:
                arg_strs.append(f"target_text={repr(target_text)}")
            detail += ", ".join(arg_strs) + ")"
            lines.append(f"  {idx}. {detail}")

        lines.append("Execute this exact proven sequence directly without wasting turns on exploration.")
        return "\n".join(lines)


# Global singleton instance
learned_skill_store = LearnedSkillStore()
