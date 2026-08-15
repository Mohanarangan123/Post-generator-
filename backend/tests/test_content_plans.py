"""
Tests for Phase 2: content plan generation, persistence, and API endpoints.

Uses:
- FastAPI TestClient (synchronous) for API tests
- SQLite in-memory DB via SQLAlchemy (overrides the real PostgreSQL session)
- unittest.mock.patch for mocking Ollama HTTP calls
- hypothesis for property-based tests
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.content_plan import ContentPlanModel, DayTopicModel
from app.schemas.content_plan import ContentPlanRequest, DayTopic
from app.services.content_plan_repository import ContentPlanRepository
from app.services.curriculum_service import (
    _build_prompt,
    _parse_json_array,
    _validate_topics,
)

# ---------------------------------------------------------------------------
# In-memory SQLite engine for tests
# Uses a single shared connection so all operations see the same in-memory DB.
# ---------------------------------------------------------------------------
SQLITE_URL = "sqlite://"


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )
    # Enable FK constraints so cascade deletes also work at the DB level
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    # Use a single connection so all operations see the same in-memory SQLite DB.
    connection = db_engine.connect()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()
    yield session
    session.close()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: valid topic list factory
# ---------------------------------------------------------------------------
def make_topics(n: int, subject: str = "AI") -> list[dict]:
    return [
        {
            "day_number": i,
            "main_subject": subject,
            "title": f"Topic {i} for {subject}",
            "short_description": f"Description for day {i}.",
            "difficulty": "Beginner",
            "category": "Fundamentals",
            "learning_objective": f"Understand concept {i}.",
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Mock helper for Ollama
# ---------------------------------------------------------------------------
def mock_ollama_response(topics: list[dict]):
    """Return an async mock for httpx.AsyncClient.post yielding a valid Ollama response."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps(topics)}
    mock_post = AsyncMock(return_value=mock_response)
    return mock_post


# ===========================================================================
# 1. API Validation Tests
# ===========================================================================


def test_missing_main_subject_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={"number_of_days": 5, "audience": "developers", "difficulty": "Beginner"},
    )
    assert resp.status_code == 422


def test_missing_number_of_days_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={"main_subject": "AI", "audience": "developers", "difficulty": "Beginner"},
    )
    assert resp.status_code == 422


def test_missing_audience_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={"main_subject": "AI", "number_of_days": 5, "difficulty": "Beginner"},
    )
    assert resp.status_code == 422


def test_missing_difficulty_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={"main_subject": "AI", "number_of_days": 5, "audience": "developers"},
    )
    assert resp.status_code == 422


def test_number_of_days_zero_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={
            "main_subject": "AI",
            "number_of_days": 0,
            "audience": "developers",
            "difficulty": "Beginner",
        },
    )
    assert resp.status_code == 422


def test_number_of_days_101_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={
            "main_subject": "AI",
            "number_of_days": 101,
            "audience": "developers",
            "difficulty": "Beginner",
        },
    )
    assert resp.status_code == 422


def test_whitespace_main_subject_returns_422(client):
    resp = client.post(
        "/api/content-plans/generate",
        json={
            "main_subject": "   ",
            "number_of_days": 5,
            "audience": "developers",
            "difficulty": "Beginner",
        },
    )
    assert resp.status_code == 422


# ===========================================================================
# 2. LLM Response Tests
# ===========================================================================


def test_valid_llm_response_creates_plan(client):
    topics = make_topics(3, "Python")
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "Python",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["plan"]["main_subject"] == "Python"
    assert len(data["plan"]["topics"]) == 3


def test_invalid_llm_response_returns_422(client):
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"response": "This is not JSON at all!!!"}
        mock_post = AsyncMock(return_value=mock_response)
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_post
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 422


def test_duplicate_day_numbers_returns_422(client):
    topics = make_topics(3, "AI")
    topics[1]["day_number"] = 1  # duplicate day 1
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 422


def test_duplicate_titles_returns_422(client):
    topics = make_topics(3, "AI")
    topics[1]["title"] = topics[0]["title"]  # duplicate title
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 422


def test_ollama_unreachable_returns_503(client):
    import httpx as real_httpx

    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(
            side_effect=real_httpx.ConnectError("Connection refused")
        )
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 503


def test_ollama_timeout_returns_504(client):
    import httpx as real_httpx

    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(
            side_effect=real_httpx.TimeoutException("Timed out")
        )
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 504


# ===========================================================================
# 3. Database Persistence Tests
# ===========================================================================


def test_persistence_round_trip(client):
    topics = make_topics(3, "Python")
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "Python",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 200
    plan_id = resp.json()["plan"]["id"]

    get_resp = client.get(f"/api/content-plans/{plan_id}")
    assert get_resp.status_code == 200
    plan = get_resp.json()["plan"]
    assert plan["main_subject"] == "Python"
    assert len(plan["topics"]) == 3
    assert plan["created_at"] is not None


def test_cascade_delete_removes_topics(client, db_session):
    topics = make_topics(3, "AI")
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": "AI",
                "number_of_days": 3,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 200
    plan_id = resp.json()["plan"]["id"]

    del_resp = client.delete(f"/api/content-plans/{plan_id}")
    assert del_resp.status_code == 200

    get_resp = client.get(f"/api/content-plans/{plan_id}")
    assert get_resp.status_code == 404

    # Expire the session cache so the query hits the DB rather than the identity map
    db_session.expire_all()

    # Verify via ORM query that topics are gone (ORM-level cascade)
    remaining = db_session.query(DayTopicModel).filter(
        DayTopicModel.plan_id == uuid.UUID(plan_id)
    ).all()
    assert len(remaining) == 0


def test_get_nonexistent_plan_returns_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/content-plans/{fake_id}")
    assert resp.status_code == 404


def test_delete_nonexistent_plan_returns_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.delete(f"/api/content-plans/{fake_id}")
    assert resp.status_code == 404


def test_list_plans_returns_all(client):
    for subject in ["Python", "AI", "Docker"]:
        n = 2
        topics = make_topics(n, subject)
        with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = MagicMock()
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_instance.post = mock_ollama_response(topics)
            mock_client_cls.return_value = mock_client_instance
            client.post(
                "/api/content-plans/generate",
                json={
                    "main_subject": subject,
                    "number_of_days": n,
                    "audience": "devs",
                    "difficulty": "Beginner",
                },
            )

    resp = client.get("/api/content-plans/")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ===========================================================================
# 4. Phase 1 Compatibility Test
# ===========================================================================


def test_phase1_health_still_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ===========================================================================
# 5. Unit Tests for Curriculum Service Functions
# ===========================================================================


def test_build_prompt_contains_required_directives():
    prompt = _build_prompt("Generative AI", 30, "developers", "Beginner")
    assert "JSON array" in prompt
    assert "Generative AI" in prompt
    assert "30" in prompt
    assert "developers" in prompt
    assert "Beginner" in prompt
    assert "day_number" in prompt
    assert "learning_objective" in prompt
    assert "duplicate" in prompt.lower()


def test_parse_json_array_valid():
    topics = make_topics(2)
    raw = json.dumps(topics)
    result = _parse_json_array(raw)
    assert len(result) == 2
    assert result[0]["day_number"] == 1


def test_parse_json_array_strips_think_tags():
    topics = make_topics(2)
    raw = f"<think>Some thinking here...</think>\n{json.dumps(topics)}"
    result = _parse_json_array(raw)
    assert len(result) == 2


def test_parse_json_array_strips_markdown_fences():
    topics = make_topics(2)
    raw = f"```json\n{json.dumps(topics)}\n```"
    result = _parse_json_array(raw)
    assert len(result) == 2


def test_parse_json_array_extracts_embedded_array():
    topics = make_topics(2)
    raw = f"Here is the plan:\n{json.dumps(topics)}\nEnd of plan."
    result = _parse_json_array(raw)
    assert len(result) == 2


def test_parse_json_array_invalid_raises_value_error():
    with pytest.raises(ValueError, match="could not be parsed"):
        _parse_json_array("This is not JSON at all!!!")


def test_validate_topics_valid():
    topics = [DayTopic(**t) for t in make_topics(3)]
    _validate_topics(topics, 3)  # should not raise


def test_validate_topics_duplicate_day_number_raises():
    raw = make_topics(3)
    raw[1]["day_number"] = 1
    topics = [DayTopic(**t) for t in raw]
    with pytest.raises(ValueError, match="sequential"):
        _validate_topics(topics, 3)


def test_validate_topics_duplicate_title_raises():
    raw = make_topics(3)
    raw[1]["title"] = raw[0]["title"]
    topics = [DayTopic(**t) for t in raw]
    with pytest.raises(ValueError, match="Duplicate"):
        _validate_topics(topics, 3)


# ===========================================================================
# 6. Property-Based Tests
# ===========================================================================
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st


@h_settings(max_examples=50)
@given(
    subject=st.text(min_size=1, max_size=50),
    n=st.integers(min_value=1, max_value=100),
    audience=st.text(min_size=1, max_size=50),
    difficulty=st.text(min_size=1, max_size=30),
)
def test_prompt_completeness(subject, n, audience, difficulty):
    """**Validates: Requirements 4.1** — prompt must contain all required directive keywords."""
    prompt = _build_prompt(subject, n, audience, difficulty)
    assert "JSON array" in prompt
    assert subject in prompt
    assert str(n) in prompt
    assert audience in prompt
    assert difficulty in prompt
    assert "day_number" in prompt
    assert "learning_objective" in prompt


@h_settings(max_examples=50)
@given(n=st.integers(min_value=1, max_value=20))
def test_json_parse_round_trip(n):
    """**Validates: Requirements 4.3** — serialised topics must survive a parse round-trip."""
    topics = make_topics(n)
    raw = json.dumps(topics)
    result = _parse_json_array(raw)
    assert len(result) == n
    for i, item in enumerate(result):
        assert item["day_number"] == i + 1


@h_settings(max_examples=50)
@given(
    prefix=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="[]{}"),
        max_size=50,
    ),
    suffix=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="[]{}"),
        max_size=50,
    ),
    n=st.integers(min_value=1, max_value=5),
)
def test_json_extraction_from_noise(prefix, suffix, n):
    """**Validates: Requirements 4.3** — JSON array must be extractable even when surrounded by noise text."""
    topics = make_topics(n)
    raw = prefix + json.dumps(topics) + suffix
    result = _parse_json_array(raw)
    assert isinstance(result, list)
    assert len(result) == n


@h_settings(max_examples=50)
@given(st.integers().filter(lambda x: x < 1 or x > 100))
def test_out_of_range_days_returns_422(n):
    """**Validates: Requirements 1.2** — number_of_days outside 1-100 must fail Pydantic validation."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ContentPlanRequest(
            main_subject="AI",
            number_of_days=n,
            audience="devs",
            difficulty="Beginner",
        )


# ===========================================================================
# 7. Regression: DayTopic ID contract
# ===========================================================================


def _generate_plan_via_api(client, subject: str = "Python", n: int = 3) -> dict:
    """Helper: generate a plan and return the parsed response JSON."""
    topics = make_topics(n, subject)
    with patch("app.services.curriculum_service.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = mock_ollama_response(topics)
        mock_client_cls.return_value = mock_client_instance

        resp = client.post(
            "/api/content-plans/generate",
            json={
                "main_subject": subject,
                "number_of_days": n,
                "audience": "beginners",
                "difficulty": "Beginner",
            },
        )
    assert resp.status_code == 200
    return resp.json()


def test_generate_response_topics_contain_id(client):
    """Regression: every DayTopic in the generate response must include a non-null UUID 'id'."""
    data = _generate_plan_via_api(client, "Python", 3)
    topics = data["plan"]["topics"]
    assert len(topics) == 3
    for topic in topics:
        assert "id" in topic, "DayTopic is missing the 'id' field"
        assert topic["id"] is not None, "DayTopic 'id' must not be null"
        parsed = uuid.UUID(topic["id"])
        assert parsed.version == 4


def test_get_plan_response_topics_contain_id(client):
    """Regression: every DayTopic in GET /api/content-plans/{id} response must include 'id'."""
    data = _generate_plan_via_api(client, "Docker", 2)
    plan_id = data["plan"]["id"]

    get_resp = client.get(f"/api/content-plans/{plan_id}")
    assert get_resp.status_code == 200
    topics = get_resp.json()["plan"]["topics"]
    assert len(topics) == 2
    for topic in topics:
        assert "id" in topic, "DayTopic is missing the 'id' field in GET response"
        assert topic["id"] is not None
        parsed = uuid.UUID(topic["id"])
        assert parsed.version == 4


def test_day_topic_id_is_not_day_number(client):
    """Regression: the DayTopic 'id' must be a UUID, not the day_number integer."""
    data = _generate_plan_via_api(client, "AI", 3)
    topics = data["plan"]["topics"]
    for topic in topics:
        parsed = uuid.UUID(topic["id"])
        assert str(parsed) != str(topic["day_number"]), \
            "DayTopic 'id' must not equal the day_number"


def test_day_topic_ids_are_unique_within_plan(client):
    """Regression: all DayTopic IDs within a plan must be distinct UUIDs."""
    data = _generate_plan_via_api(client, "ML", 5)
    topics = data["plan"]["topics"]
    ids = [t["id"] for t in topics]
    assert len(ids) == len(set(ids)), "DayTopic IDs within a plan must all be unique"


def test_day_topic_id_matches_what_is_stored(client, db_session):
    """Regression: the UUID returned in the API must match what's persisted in the DB."""
    data = _generate_plan_via_api(client, "FastAPI", 2)
    plan_id = uuid.UUID(data["plan"]["id"])
    api_ids = {t["id"] for t in data["plan"]["topics"]}

    db_session.expire_all()
    db_topics = db_session.query(DayTopicModel).filter(
        DayTopicModel.plan_id == plan_id
    ).all()
    db_ids = {str(t.id) for t in db_topics}

    assert api_ids == db_ids, (
        "API-returned DayTopic IDs must match persisted DB IDs"
    )
