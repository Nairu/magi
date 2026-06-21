"""Tests for tolerant JSON extraction from model output."""

import pytest

from magi.deliberation import extract_json


def test_clean_json():
    raw = '{"verdict": "APPROVE", "confidence": 80, "reasoning": "ok"}'
    assert extract_json(raw)["verdict"] == "APPROVE"


def test_markdown_fence():
    raw = '```json\n{"verdict": "REJECT", "confidence": 90, "reasoning": "no"}\n```'
    out = extract_json(raw)
    assert out["verdict"] == "REJECT"
    assert out["confidence"] == 90


def test_plain_fence_without_language():
    raw = '```\n{"verdict": "CONDITIONAL", "confidence": 50, "reasoning": "maybe"}\n```'
    assert extract_json(raw)["verdict"] == "CONDITIONAL"


def test_prose_before_json():
    raw = (
        "Here is my analysis:\n"
        "I think this should be approved.\n"
        '{"verdict": "APPROVE", "confidence": 75, "reasoning": "fine"}'
    )
    out = extract_json(raw)
    assert out["verdict"] == "APPROVE"


def test_prose_around_json():
    raw = (
        'Some preamble. {"verdict": "REJECT", "confidence": 88, '
        '"reasoning": "bad idea"} Some afterthought.'
    )
    out = extract_json(raw)
    assert out["verdict"] == "REJECT"
    assert out["confidence"] == 88


def test_invalid_raises():
    with pytest.raises(Exception):
        extract_json("definitely not json")
