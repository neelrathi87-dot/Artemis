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

"""Contacts parsing and vCard (VCF) generation helper for Artemis.

Parses contacts from PDF, CSV, Excel, TXT, or vCard formats, normalizes phone numbers,
applies optional naming prefixes, and generates standard vCard 3.0 (.vcf) files for instant,
bulk contact importation on Android devices.
"""

from pathlib import Path
import re
from typing import Any

from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)


def extract_contacts_from_text(text: str) -> list[dict[str, str]]:
    """Extract contact (name, phone) pairs from unstructured or tabular text."""
    if not text:
        return []

    contacts: list[dict[str, str]] = []
    lines = text.splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Ignore obvious header lines
        if any(h in line.lower() for h in ["phone number", "full name", "contact name", "type / tag"]):
            continue

        # Look for international or national phone patterns
        phone_match = re.search(r"(\+?\d[\d\s\-\(\)]{7,}\d)", line)
        if not phone_match:
            continue

        raw_phone = phone_match.group(1).strip()
        clean_phone = re.sub(r"[^\d+]", "", raw_phone)

        # Phone numbers should have between 7 and 16 digits
        digits_only = re.sub(r"\D", "", clean_phone)
        if len(digits_only) < 7 or len(digits_only) > 16:
            continue

        # Extract name part before the phone number
        name_part = line[: phone_match.start()].strip()
        name_part = re.sub(r"^[\d#\-\.\,\:\;\s]+", "", name_part).strip()

        # If name is still empty, check after phone number (e.g. CSV format: +12345678, John Doe)
        if not name_part:
            after_phone = line[phone_match.end() :].strip()
            after_phone = re.sub(r"^[\,\:\;\-\s]+", "", after_phone).strip()
            if after_phone and not re.search(r"mobile|cell|work|home", after_phone, re.IGNORECASE):
                name_part = after_phone

        # Filter out invalid names
        if not name_part or len(name_part) < 2:
            continue

        contacts.append({"name": name_part, "phone": clean_phone})

    return contacts


def generate_vcf(contacts: list[dict[str, str]], prefix: str = "") -> str:
    """Generate a valid vCard 3.0 multi-contact text string."""
    cards = []
    for c in contacts:
        name = c.get("name", "").strip()
        phone = c.get("phone", "").strip()
        if not name or not phone:
            continue

        full_name = f"{prefix}{name}".strip()
        cards.append(
            f"BEGIN:VCARD\n"
            f"VERSION:3.0\n"
            f"FN:{full_name}\n"
            f"TEL;TYPE=CELL:{phone}\n"
            f"END:VCARD"
        )
    return "\n".join(cards) + "\n"


def extract_prefix_from_goal(goal: str) -> str:
    """Extract requested contact prefix from a task goal if present."""
    if not goal:
        return ""
    # Matches: prefix 'Client_' or prefix "Client_" or with prefix Client_
    m = re.search(r"prefix\s+['\"]?([\w\-\_]+)['\"]?", goal, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""
