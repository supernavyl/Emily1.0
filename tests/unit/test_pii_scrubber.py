"""Unit tests for security.pii_scrubber.PIIScrubber."""

from __future__ import annotations

import pytest

from security.pii_scrubber import PIIScrubber


@pytest.fixture()
def scrubber():
    return PIIScrubber(spacy_model="nonexistent_model_for_test")


def test_scrub_email(scrubber):
    result = scrubber.scrub("Contact me at alice@example.com for details.")
    assert "<EMAIL>" in result.scrubbed
    assert "alice@example.com" not in result.scrubbed
    assert result.was_modified


def test_scrub_phone(scrubber):
    result = scrubber.scrub("Call me at 555-123-4567.")
    assert "<PHONE>" in result.scrubbed
    assert "555-123-4567" not in result.scrubbed


def test_scrub_ssn(scrubber):
    result = scrubber.scrub("My SSN is 123-45-6789.")
    assert "<SSN>" in result.scrubbed
    assert "123-45-6789" not in result.scrubbed


def test_scrub_ip(scrubber):
    result = scrubber.scrub("Server at 192.168.1.100 is down.")
    assert "<IP_ADDRESS>" in result.scrubbed


def test_scrub_credit_card(scrubber):
    result = scrubber.scrub("Card number 4111111111111111 on file.")
    assert "<CREDIT_CARD>" in result.scrubbed
    assert "4111111111111111" not in result.scrubbed


def test_scrub_no_pii(scrubber):
    text = "The weather is nice today."
    result = scrubber.scrub(text)
    assert not result.was_modified
    assert result.scrubbed == text


def test_scrub_dict_flat(scrubber):
    data = {"name": "Contact alice@example.com", "count": 42}
    result = scrubber.scrub_dict(data)
    assert "<EMAIL>" in result["name"]
    assert result["count"] == 42


def test_scrub_dict_recursive_nested(scrubber):
    data = {
        "user": {
            "email": "bob@test.com",
            "phone": "555-123-4567",
        },
        "notes": "Clean data",
    }
    result = scrubber.scrub_dict(data)
    assert "<EMAIL>" in result["user"]["email"]
    assert "<PHONE>" in result["user"]["phone"]
    assert result["notes"] == "Clean data"


def test_scrub_dict_recursive_list(scrubber):
    data = {
        "contacts": [
            {"email": "a@b.com"},
            "Call 555-123-4567",
        ]
    }
    result = scrubber.scrub_dict(data)
    assert "<EMAIL>" in result["contacts"][0]["email"]
    assert "<PHONE>" in result["contacts"][1]


def test_scrub_dict_with_fields_filter(scrubber):
    data = {"secret": "alice@example.com", "public": "bob@example.com"}
    result = scrubber.scrub_dict(data, fields=["secret"])
    assert "<EMAIL>" in result["secret"]
    assert result["public"] == "bob@example.com"


@pytest.mark.asyncio
async def test_scrub_async(scrubber):
    result = await scrubber.scrub_async("Email: test@test.com")
    assert "<EMAIL>" in result.scrubbed


@pytest.mark.asyncio
async def test_scrub_dict_async(scrubber):
    data = {"msg": "Call 555-123-4567"}
    result = await scrubber.scrub_dict_async(data)
    assert "<PHONE>" in result["msg"]
