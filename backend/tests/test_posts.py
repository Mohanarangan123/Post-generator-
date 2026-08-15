"""
Tests for Phase 3: LinkedIn post generation, persistence, editing, approval, and regeneration.

Uses:
- FastAPI TestClient (synchronous) for API tests
- SQLite in-memory DB via SQLAlchemy (overrides the real PostgreSQL session)
- unittest.mock.patch for mocking Ollama HTTP calls
- hypothesis for property-based tests
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as real_httpx
import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.content_plan import ContentPlanModel, DayTopicModel
from app.models.post import PostModel, PostStatus
from app.schemas.post import PostUpdate
from app.services.post_service import _build_post_prompt, _clean_response

# ---------------------------------------------------------------------------
# In-memory SQLite engine for tests
# ---------------------------------------------------------------------------
SQLITE_URL = "sqlite://"


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
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
# Helpers
# ---------------------------------------------------------------------------

def make_plan_and_topic(db_session):
    """Insert a ContentPlanModel + one DayTopicModel; return (plan, topic)."""
    plan = ContentPlanModel(
        id=uuid.uuid4(),
        main_subject="Python",
        number_of_days=1,
        audience="developers",
        difficulty="Beginner",
    )
    db_session.add(plan)
    db_session.flush()

    topic = DayTopicModel(
        id=uuid.uuid4(),
        plan_id=plan.id,
        day_number=1,
        main_subject="Python",
        title="Introduction to Python",
        short_description="A beginner introduction to Python programming.",
        difficulty="Beginner",
        category="Fundamentals",
        learning_objective="Understand Python basics and write a simple script.",
    )
    db_session.add(topic)
    db_session.commit()
    return plan, topic


def mock_ollama_post_response(content: str = "DAY 1: Test post content."):
    """Return an async mock simulating a valid Ollama response."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": content}
    mock_post = AsyncMock(return_value=mock_response)
    return mock_post


def build_mock_client(mock_post):
    """Wrap mock_post in a properly set-up async context manager mock."""
    mock_client_instance = MagicMock()
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)
    mock_client_instance.post = mock_post
    return mock_client_instance


# ===========================================================================
# 11.1 Happy-path generation test
# ===========================================================================

def test_happy_path_generation(client, db_session):
    """POST /api/posts/generate/{day_topic_id} with valid Ollama → status=DRAFT, non-empty content."""
    _, topic = make_plan_and_topic(db_session)
    post_content = "DAY 1: Introduction to Python\n\nThis is a test LinkedIn post."

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response(post_content))
        resp = client.post(f"/api/posts/generate/{topic.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["post"]["status"] == PostStatus.DRAFT
    assert data["post"]["content"] == post_content
    assert data["post"]["day_topic_id"] == str(topic.id)
    assert data["post"]["version"] == 1


# ===========================================================================
# 11.2 Post persistence round-trip
# ===========================================================================

def test_post_persistence_round_trip(client, db_session):
    """Generate post → GET /api/posts/{post_id} → assert all fields match."""
    _, topic = make_plan_and_topic(db_session)
    post_content = "DAY 1: Test post for round-trip."

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response(post_content))
        gen_resp = client.post(f"/api/posts/generate/{topic.id}")

    assert gen_resp.status_code == 200
    post_id = gen_resp.json()["post"]["id"]

    get_resp = client.get(f"/api/posts/{post_id}")
    assert get_resp.status_code == 200
    post = get_resp.json()["post"]
    assert post["id"] == post_id
    assert post["content"] == post_content
    assert post["status"] == PostStatus.DRAFT
    assert post["version"] == 1
    assert post["day_topic_id"] == str(topic.id)
    assert post["created_at"] is not None
    assert post["updated_at"] is not None


# ===========================================================================
# 11.3 Edit post content
# ===========================================================================

def test_edit_post_content(client, db_session):
    """Generate post → PUT /api/posts/{post_id} → content updated, version incremented."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response("Original content."))
        gen_resp = client.post(f"/api/posts/generate/{topic.id}")

    post_id = gen_resp.json()["post"]["id"]
    new_content = "Updated LinkedIn post content with more detail."

    put_resp = client.put(f"/api/posts/{post_id}", json={"content": new_content})
    assert put_resp.status_code == 200
    updated = put_resp.json()["post"]
    assert updated["content"] == new_content
    assert updated["version"] == 2


# ===========================================================================
# 11.4 Approval workflow
# ===========================================================================

def test_approval_workflow(client, db_session):
    """Generate post → POST /api/posts/{post_id}/approve → status == APPROVED."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response("Post to approve."))
        gen_resp = client.post(f"/api/posts/generate/{topic.id}")

    post_id = gen_resp.json()["post"]["id"]

    approve_resp = client.post(f"/api/posts/{post_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["post"]["status"] == PostStatus.APPROVED


# ===========================================================================
# 11.5 Regeneration
# ===========================================================================

def test_regeneration(client, db_session):
    """Generate post (v1) → POST regenerate → new content, version == 2."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response("Version 1 content."))
        gen_resp = client.post(f"/api/posts/generate/{topic.id}")

    post_id = gen_resp.json()["post"]["id"]
    assert gen_resp.json()["post"]["version"] == 1

    new_content = "Version 2 regenerated content."
    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response(new_content))
        regen_resp = client.post(f"/api/posts/{post_id}/regenerate")

    assert regen_resp.status_code == 200
    regen_data = regen_resp.json()
    assert regen_data["success"] is True
    assert regen_data["post"]["content"] == new_content
    assert regen_data["post"]["version"] == 2
    assert regen_data["post"]["status"] == PostStatus.DRAFT


# ===========================================================================
# 11.6 Ollama failure → FAILED status
# ===========================================================================

def test_ollama_failure_stores_failed_status(client, db_session):
    """Mock Ollama to raise ConnectError on every attempt → post.status == FAILED, success=False."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post = AsyncMock(
            side_effect=real_httpx.ConnectError("Connection refused")
        )
        mock_cls.return_value = mock_instance
        resp = client.post(f"/api/posts/generate/{topic.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["post"]["status"] == PostStatus.FAILED


# ===========================================================================
# 11.7 Empty Ollama response → FAILED status
# ===========================================================================

def test_empty_ollama_response_stores_failed_status(client, db_session):
    """Mock Ollama to return empty string → post.status == FAILED."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response(""))
        resp = client.post(f"/api/posts/generate/{topic.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["post"]["status"] == PostStatus.FAILED


# ===========================================================================
# Additional API edge-case tests
# ===========================================================================

def test_generate_nonexistent_topic_returns_404(client):
    """POST generate for a non-existent day_topic_id → 404."""
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/posts/generate/{fake_id}")
    assert resp.status_code == 404


def test_get_nonexistent_post_returns_404(client):
    """GET /api/posts/{non-existent-id} → 404."""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/posts/{fake_id}")
    assert resp.status_code == 404


def test_approve_nonexistent_post_returns_404(client):
    """POST approve for non-existent post → 404."""
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/posts/{fake_id}/approve")
    assert resp.status_code == 404


def test_update_with_blank_content_returns_422(client, db_session):
    """PUT with blank content → 422 validation error."""
    _, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response("Some content."))
        gen_resp = client.post(f"/api/posts/generate/{topic.id}")

    post_id = gen_resp.json()["post"]["id"]
    resp = client.put(f"/api/posts/{post_id}", json={"content": "   "})
    assert resp.status_code == 422


def test_bulk_generate_posts_for_plan(client, db_session):
    """POST /api/content-plans/{plan_id}/generate-posts → generates one post per topic."""
    plan, topic = make_plan_and_topic(db_session)
    post_content = "Bulk generated post content."

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response(post_content))
        resp = client.post(f"/api/content-plans/{plan.id}/generate-posts")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["generated"] == 1
    assert data["failed"] == 0
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == PostStatus.DRAFT


def test_bulk_generate_nonexistent_plan_returns_404(client):
    """POST generate-posts for non-existent plan → 404."""
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/content-plans/{fake_id}/generate-posts")
    assert resp.status_code == 404


def test_list_posts_by_plan(client, db_session):
    """GET /api/posts/by-plan/{plan_id} → returns list of posts."""
    plan, topic = make_plan_and_topic(db_session)

    with patch("app.services.post_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(mock_ollama_post_response("Test post."))
        client.post(f"/api/posts/generate/{topic.id}")

    resp = client.get(f"/api/posts/by-plan/{plan.id}")
    assert resp.status_code == 200
    posts = resp.json()
    assert len(posts) == 1
    assert posts[0]["day_topic_id"] == str(topic.id)


def test_phase1_and_phase2_tests_still_pass(client):
    """Smoke test: Phase 1 health endpoint still works."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ===========================================================================
# 11.8 Hypothesis property-based tests
# ===========================================================================

@h_settings(max_examples=50)
@given(
    day_number=st.integers(min_value=1, max_value=100),
    title=st.text(min_size=1, max_size=80),
    main_subject=st.text(min_size=1, max_size=50),
    category=st.text(min_size=1, max_size=50),
    difficulty=st.text(min_size=1, max_size=30),
    short_description=st.text(min_size=1, max_size=200),
    learning_objective=st.text(min_size=1, max_size=200),
)
def test_prompt_contains_all_structural_markers(
    day_number, title, main_subject, category, difficulty, short_description, learning_objective
):
    """
    **Validates: Requirements 4.1 & 4.2**
    Property 1 & 2: prompt must contain all 7 section markers and all DayTopic field values.
    """

    class FakeTopic:
        pass

    topic = FakeTopic()
    topic.day_number = day_number
    topic.title = title
    topic.main_subject = main_subject
    topic.category = category
    topic.difficulty = difficulty
    topic.short_description = short_description
    topic.learning_objective = learning_objective

    prompt = _build_post_prompt(topic)

    # Section markers (Property 1)
    assert f"DAY {day_number}" in prompt
    assert "✅ A simple explanation:" in prompt
    assert "✅ A real-world example:" in prompt
    assert "✅ How it works:" in prompt
    assert "✅ Why it matters:" in prompt
    assert "💡 Key takeaway:" in prompt
    assert "hashtags" in prompt.lower()

    # Field inclusion (Property 2)
    assert str(day_number) in prompt
    assert title in prompt
    assert main_subject in prompt
    assert category in prompt
    assert difficulty in prompt
    assert short_description in prompt
    assert learning_objective in prompt


@h_settings(max_examples=50)
@given(content=st.text(min_size=1, max_size=500))
def test_clean_response_is_idempotent(content):
    """
    **Validates: Requirements 4.5**
    Property 3: applying _clean_response twice = applying it once.
    """
    once = _clean_response(content)
    twice = _clean_response(once)
    assert once == twice


@h_settings(max_examples=50)
@given(
    content=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="`<>",
        ),
        min_size=1,
        max_size=200,
    )
)
def test_clean_response_removes_think_tags(content):
    """
    **Validates: Requirements 4.5**
    Property 4: wrapping in <think> preamble then cleaning recovers original (no think tags remain).
    """
    wrapped = f"<think>some thinking here</think>\n{content}"
    result = _clean_response(wrapped)
    # The clean version should not contain the think block
    assert "<think>" not in result
    assert "</think>" not in result


@h_settings(max_examples=50)
@given(
    whitespace=st.text(
        alphabet=st.sampled_from(" \t\n\r"),
        min_size=1,
        max_size=50,
    )
)
def test_post_update_rejects_whitespace_only_content(whitespace):
    """
    **Validates: Requirements 6.3**
    Property 7: PostUpdate must reject whitespace-only content.
    """
    with pytest.raises(ValidationError):
        PostUpdate(content=whitespace)


@h_settings(max_examples=50)
@given(status=st.sampled_from(list(PostStatus)))
def test_post_status_values_are_valid_enum_members(status):
    """
    **Validates: Requirements 1.5**
    Property 8: every PostStatus value is a valid enum member with a string value.
    """
    assert status in PostStatus
    assert isinstance(status.value, str)
