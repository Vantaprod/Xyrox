"""Xyrox — Wake Word Tests (Phase 6.4)"""

import pytest
from app.backend.voice.wake_word import detect_wake, WakeMatch


def test_exact_wake_word():
    m = detect_wake("hey xyrox")
    assert m.matched
    assert m.command == ""


def test_wake_word_with_command():
    m = detect_wake("Hey Xyrox, create a task.")
    assert m.matched
    assert m.wake_phrase == "hey xyrox"
    assert m.command == "create a task"


def test_wake_word_case_insensitive():
    assert detect_wake("HEY XYROX DO THIS").matched


def test_wake_word_punctuation_tolerant():
    assert detect_wake("Hey, Xyrox! Do that.").matched


def test_simple_xyrox_alone():
    m = detect_wake("xyrox open browser")
    assert m.matched
    assert m.command == "open browser"


def test_no_wake_word():
    m = detect_wake("please create a task")
    assert not m.matched
    assert m.command == "please create a task"


def test_empty_transcript():
    m = detect_wake("")
    assert not m.matched


def test_custom_phrases():
    m = detect_wake("jarvis do it", wake_phrases=["jarvis"])
    assert m.matched
    assert m.command == "do it"


def test_rejects_non_string():
    with pytest.raises(TypeError):
        detect_wake(123)  # type: ignore


def test_rejects_empty_phrases():
    with pytest.raises(ValueError):
        detect_wake("hi", wake_phrases=[])


def test_longest_phrase_wins():
    m = detect_wake("hey xyrox do it",
                    wake_phrases=["xyrox", "hey xyrox"])
    assert m.matched
    assert m.wake_phrase == "hey xyrox"
    assert m.command == "do it"