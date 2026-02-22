"""
vCard (.vcf) parser — bulk-imports contacts into the people database.

Parses RFC 6350 vCard files using the `vobject` library and converts each
contact into an EntityRecord + PersonRecord pair, then feeds them through
the ExtractionPipeline for proper deduplication and fact storage.

Handles both single-contact and multi-contact (stacked vCard) .vcf files.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ParsedContact:
    """A contact parsed from a vCard file, ready for import."""

    full_name: str = ""
    email_addresses: list[str] = field(default_factory=list)
    phone_numbers: list[str] = field(default_factory=list)
    organization: str = ""
    title: str = ""
    birthday: str = ""          # YYYY-MM-DD or MM-DD
    home_location: str = ""
    work_location: str = ""
    social_profiles: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    raw_text: str = ""          # Full text representation for LLM extraction


def _parse_date(val: Any) -> str:
    """Convert a vCard date value to YYYY-MM-DD or MM-DD string."""
    try:
        s = str(val)
        # YYYYMMDD
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:]}"
        # --MMDD (no year)
        if s.startswith("--") and len(s) == 6:
            return s[2:4] + "-" + s[4:6]
        return s
    except Exception:
        return ""


async def parse_vcard_file(path: Path) -> list[ParsedContact]:
    """
    Parse a .vcf file and return a list of ParsedContact objects.

    Runs vobject parsing in a thread to keep the event loop free.

    Args:
        path: Path to the .vcf file.

    Returns:
        List of ParsedContact objects, one per vCard in the file.
    """
    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    return await asyncio.to_thread(_parse_vcard_content, content)


def _parse_vcard_content(content: str) -> list[ParsedContact]:
    """
    Synchronous vCard parsing worker.

    Args:
        content: Raw vCard file content.

    Returns:
        List of ParsedContact objects.
    """
    try:
        import vobject
    except ImportError:
        log.error("vobject_not_installed")
        return []

    contacts: list[ParsedContact] = []

    try:
        for vcard in vobject.readComponents(content):
            contact = ParsedContact()

            # Name
            if hasattr(vcard, "fn"):
                contact.full_name = str(vcard.fn.value).strip()
            elif hasattr(vcard, "n"):
                n = vcard.n.value
                parts = [
                    str(n.given or ""),
                    str(n.family or ""),
                ]
                contact.full_name = " ".join(p for p in parts if p).strip()

            if not contact.full_name:
                continue  # Skip contacts with no name

            # Email
            if hasattr(vcard, "email_list"):
                contact.email_addresses = [str(e.value) for e in vcard.email_list]
            elif hasattr(vcard, "email"):
                contact.email_addresses = [str(vcard.email.value)]

            # Phone
            if hasattr(vcard, "tel_list"):
                contact.phone_numbers = [str(t.value) for t in vcard.tel_list]
            elif hasattr(vcard, "tel"):
                contact.phone_numbers = [str(vcard.tel.value)]

            # Organization / title
            if hasattr(vcard, "org"):
                org_val = vcard.org.value
                contact.organization = (
                    org_val[0] if isinstance(org_val, list) else str(org_val)
                )
            if hasattr(vcard, "title"):
                contact.title = str(vcard.title.value).strip()

            # Birthday
            if hasattr(vcard, "bday"):
                contact.birthday = _parse_date(vcard.bday.value)

            # Address (first home or work)
            if hasattr(vcard, "adr_list"):
                for adr in vcard.adr_list:
                    val = adr.value
                    addr_str = ", ".join(
                        str(p) for p in [val.city, val.region, val.country] if p
                    )
                    adr_type = str(getattr(adr, "type_param", "home")).lower()
                    if "work" in adr_type:
                        contact.work_location = addr_str
                    else:
                        contact.home_location = addr_str

            # Note
            if hasattr(vcard, "note"):
                contact.notes = str(vcard.note.value).strip()

            # Assemble raw text for LLM extraction
            parts_for_llm = [f"Name: {contact.full_name}"]
            if contact.organization:
                parts_for_llm.append(f"Organization: {contact.organization}")
            if contact.title:
                parts_for_llm.append(f"Title: {contact.title}")
            if contact.email_addresses:
                parts_for_llm.append(f"Email: {', '.join(contact.email_addresses)}")
            if contact.notes:
                parts_for_llm.append(f"Notes: {contact.notes}")
            contact.raw_text = "\n".join(parts_for_llm)

            contacts.append(contact)

    except Exception as exc:
        log.error("vcard_parse_error", error=str(exc))

    log.info("vcard_parsed", count=len(contacts), path=str(path))
    return contacts
