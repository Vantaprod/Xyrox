"""Xyrox — Voice API Tests (Phase 6.4)"""

import base64
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models.models import Base
from app.backend.services import auth_service
from app.backend.main import app
from app.backend.config import settings


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "voice_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(auth_service, "SessionLocal", TestSession)
    yield
    engine.dispose()


def _register_and_login():
    r = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "username": "voicetest",
            "email": "vt@example.com",
            "password": "securepass123",
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"username": "voicetest", "password": "securepass123"},
    )
    token = r.json()["token"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _silent_wav_b64():
    import soundfile as sf
    import io
    sr = 16000
    buf = io.BytesIO()
    sf.write(buf, np.zeros(sr, dtype=np.float32), sr, format="WAV")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ============================================================
# AUTH
# ============================================================
def test_transcribe_requires_auth():
    r = client.post(
        f"{settings.API_V1_STR}/voice/transcribe",
        json={"audio_base64": "AAAA"},
    )
    assert r.status_code == 401


def test_profiles_list_requires_auth():
    r = client.get(f"{settings.API_V1_STR}/voice/profiles")
    assert r.status_code == 401


# ============================================================
# TRANSCRIBE
# ============================================================
def test_transcribe_rejects_bad_base64():
    headers = _register_and_login()
    r = client.post(
        f"{settings.API_V1_STR}/voice/transcribe",
        json={"audio_base64": "!!!!"},
        headers=headers,
    )
    assert r.status_code == 400


def test_transcribe_rejects_short_audio():
    headers = _register_and_login()
    tiny = base64.b64encode(b"abc").decode("ascii")
    r = client.post(
        f"{settings.API_V1_STR}/voice/transcribe",
        json={"audio_base64": tiny},
        headers=headers,
    )
    assert r.status_code == 400


# ============================================================
# PROFILES
# ============================================================
def test_list_profiles_empty_authenticated():
    headers = _register_and_login()
    r = client.get(
        f"{settings.API_V1_STR}/voice/profiles", headers=headers,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)