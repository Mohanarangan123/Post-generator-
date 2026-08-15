"""
Tests for Phase 4: Infographic generation pipeline.

Uses:
- FastAPI TestClient (synchronous) for API tests
- SQLite in-memory DB via SQLAlchemy (overrides the real PostgreSQL session)
- unittest.mock.patch for mocking Ollama HTTP calls and Playwright
- hypothesis for property-based tests
"""
import asyncio
import json
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as real_httpx
import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.content_plan import ContentPlanModel, DayTopicModel
from app.models.image import ImageModel, ImageStatus
from app.models.post import PostModel, PostStatus
from app.schemas.image import VisualSpec
from app.services.image_providers import ImageProviderError, MockImageProvider
from app.services.image_service import run_pipeline
from app.services.image_template import build_html

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

def make_post(db_session, topic: DayTopicModel = None) -> PostModel:
    """Insert a PostModel with status DRAFT. If no topic provided, creates one."""
    if topic is None:
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
        db_session.flush()

    post = PostModel(
        id=uuid.uuid4(),
        day_topic_id=topic.id,
        content="DAY 1: Introduction to Python\n\nPython is a versatile programming language.",
        status=PostStatus.DRAFT,
        version=1,
    )
    db_session.add(post)
    db_session.commit()
    return post


def mock_ollama_visual_spec_response(visual_spec_dict: dict) -> AsyncMock:
    """Return an async mock simulating a valid Ollama response with VisualSpec JSON."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": json.dumps(visual_spec_dict)}
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
# Unit tests (example-based)
# ===========================================================================

def test_valid_visual_spec_construction():
    """
    Build a VisualSpec with all valid fields, assert model_dump() contains
    exactly the expected keys.
    **Validates: Requirements 1.1, 1.2**
    """
    spec = VisualSpec(
        day_number=5,
        title="Understanding Python Lists",
        subtitle="A beginner guide",
        visual_concept="A colorful array visualization with boxes and arrows",
        diagram_type="list",
        diagram_nodes=["item1", "item2", "item3"],
        key_points=[
            "Lists are ordered collections",
            "Lists can contain any data type",
            "Lists are mutable",
        ],
        style="dark-tech",
        aspect_ratio="1:1",
    )
    dumped = spec.model_dump()
    expected_keys = {
        "day_number",
        "title",
        "subtitle",
        "visual_concept",
        "diagram_type",
        "diagram_nodes",
        "key_points",
        "style",
        "aspect_ratio",
    }
    assert set(dumped.keys()) == expected_keys
    assert dumped["day_number"] == 5
    assert dumped["title"] == "Understanding Python Lists"
    assert dumped["diagram_type"] == "list"
    assert len(dumped["key_points"]) == 3


def test_visual_spec_invalid_too_few_key_points():
    """
    Assert ValidationError for key_points with 2 items.
    **Validates: Requirement 1.3**
    """
    with pytest.raises(ValidationError):
        VisualSpec(
            day_number=1,
            title="Test",
            subtitle="Sub",
            visual_concept="Concept",
            diagram_type="list",
            diagram_nodes=["node1"],
            key_points=["point1", "point2"],  # too few
            style="dark-tech",
            aspect_ratio="1:1",
        )


def test_visual_spec_invalid_too_many_key_points():
    """
    Assert ValidationError for key_points with 6 items.
    **Validates: Requirement 1.3**
    """
    with pytest.raises(ValidationError):
        VisualSpec(
            day_number=1,
            title="Test",
            subtitle="Sub",
            visual_concept="Concept",
            diagram_type="list",
            diagram_nodes=["node1"],
            key_points=["p1", "p2", "p3", "p4", "p5", "p6"],  # too many
            style="dark-tech",
            aspect_ratio="1:1",
        )


def test_visual_spec_invalid_day_number():
    """
    Assert ValidationError for day_number=0.
    **Validates: Requirement 1.4**
    """
    with pytest.raises(ValidationError):
        VisualSpec(
            day_number=0,  # invalid
            title="Test",
            subtitle="Sub",
            visual_concept="Concept",
            diagram_type="list",
            diagram_nodes=["node1"],
            key_points=["p1", "p2", "p3"],
            style="dark-tech",
            aspect_ratio="1:1",
        )


def test_visual_spec_invalid_empty_title():
    """
    Assert ValidationError for title="".
    **Validates: Requirement 1.6**
    """
    with pytest.raises(ValidationError):
        VisualSpec(
            day_number=1,
            title="",  # invalid
            subtitle="Sub",
            visual_concept="Concept",
            diagram_type="list",
            diagram_nodes=["node1"],
            key_points=["p1", "p2", "p3"],
            style="dark-tech",
            aspect_ratio="1:1",
        )


def test_mock_provider_returns_png_magic_bytes():
    """
    Call asyncio.run(MockImageProvider().generate("test prompt")),
    assert result starts with PNG magic bytes.
    **Validates: Requirements 2.2, 2.4**
    """
    provider = MockImageProvider()
    result = asyncio.run(provider.generate("test prompt"))
    assert result.startswith(b"\x89PNG\r\n\x1a\n")


def test_html_template_contains_required_elements():
    """
    Call build_html(valid_spec, b""), assert string contains "DAY 01",
    title, and each key point.
    **Validates: Requirements 5.1, 5.2, 5.4**
    """
    import html as html_lib
    
    valid_spec = VisualSpec(
        day_number=1,
        title="Python Basics",
        subtitle="Intro",
        visual_concept="A concept",
        diagram_type="list",
        diagram_nodes=["node1"],
        key_points=["Point A", "Point B", "Point C"],
        style="dark-tech",
        aspect_ratio="1:1",
    )
    html = build_html(valid_spec, b"")
    assert "DAY 01" in html
    assert html_lib.escape(valid_spec.title) in html
    assert html_lib.escape("Point A") in html
    assert html_lib.escape("Point B") in html
    assert html_lib.escape("Point C") in html


def test_image_model_persistence_round_trip(db_session):
    """
    Create ImageModel record in SQLite, retrieve by id, assert all fields equal.
    **Validates: Requirements 3.1, 3.7**
    """
    post = make_post(db_session)
    image = ImageModel(
        id=uuid.uuid4(),
        post_id=post.id,
        provider="TestProvider",
        prompt="test prompt",
        visual_spec={"day_number": 1, "title": "Test"},
        file_path="/tmp/test.png",
        width=1080,
        height=1080,
        status=ImageStatus.COMPLETED,
    )
    db_session.add(image)
    db_session.commit()

    retrieved = db_session.query(ImageModel).filter(ImageModel.id == image.id).first()
    assert retrieved is not None
    assert retrieved.id == image.id
    assert retrieved.post_id == post.id
    assert retrieved.provider == "TestProvider"
    assert retrieved.prompt == "test prompt"
    assert retrieved.visual_spec == {"day_number": 1, "title": "Test"}
    assert retrieved.file_path == "/tmp/test.png"
    assert retrieved.width == 1080
    assert retrieved.height == 1080
    assert retrieved.status == ImageStatus.COMPLETED


def test_pipeline_failure_when_provider_raises(db_session, tmp_path):
    """
    Mock MockImageProvider.generate to raise ImageProviderError;
    call run_pipeline; assert returned ImageModel.status == "FAILED".
    **Validates: Requirement 7.4**
    """
    post = make_post(db_session)

    valid_visual_spec = {
        "day_number": 1,
        "title": "Test",
        "subtitle": "Sub",
        "visual_concept": "Concept",
        "diagram_type": "list",
        "diagram_nodes": ["node1"],
        "key_points": ["p1", "p2", "p3"],
        "style": "dark-tech",
        "aspect_ratio": "1:1",
    }

    with patch("app.services.image_service.generate_visual_spec") as mock_gen_spec:
        mock_gen_spec.return_value = VisualSpec(**valid_visual_spec)
        with patch("app.services.image_service.get_image_provider") as mock_get_provider:
            mock_provider = AsyncMock()
            mock_provider.generate = AsyncMock(
                side_effect=ImageProviderError("test error")
            )
            mock_get_provider.return_value = mock_provider

            result = asyncio.run(run_pipeline(post.id, db_session))

    assert result.status == ImageStatus.FAILED


def test_generate_image_api_happy_path(client, db_session, tmp_path):
    """
    Mock visual_spec_service._call_ollama to return valid VisualSpec JSON string;
    mock image_renderer.render_html_to_png to write a stub PNG and return the path;
    call POST /api/images/generate/{post_id} via TestClient;
    assert HTTP 200, success=True, status="COMPLETED", file_path not null.
    **Validates: Requirements 8.1, 8.3**
    """
    post = make_post(db_session)

    valid_visual_spec = {
        "day_number": 1,
        "title": "Test Title",
        "subtitle": "Test Subtitle",
        "visual_concept": "A test visual concept",
        "diagram_type": "list",
        "diagram_nodes": ["node1", "node2"],
        "key_points": ["key1", "key2", "key3"],
        "style": "dark-tech",
        "aspect_ratio": "1:1",
    }

    # Mock Ollama call
    with patch("app.services.visual_spec_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = build_mock_client(
            mock_ollama_visual_spec_response(valid_visual_spec)
        )

        # Mock Playwright render
        with patch("app.services.image_renderer.render_html_to_png") as mock_render:
            fake_output = tmp_path / "fake.png"
            fake_output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            mock_render.return_value = fake_output

            # Mock get_settings to use tmp_path as output dir
            with patch("app.services.image_service.get_settings") as mock_settings:
                mock_settings.return_value.image_provider = "mock"
                mock_settings.return_value.image_output_dir = str(tmp_path)

                resp = client.post(f"/api/images/generate/{post.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["status"] == ImageStatus.COMPLETED
    assert data["file_path"] is not None
    assert data["post_id"] == str(post.id)


def test_generate_image_api_nonexistent_post(client):
    """
    Call POST /api/images/generate/{random_uuid}; assert HTTP 404.
    **Validates: Requirement 8.2**
    """
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/images/generate/{fake_id}")
    assert resp.status_code == 404


# ===========================================================================
# Property-based tests (Hypothesis @given, @h_settings(max_examples=100))
# ===========================================================================

# Feature: phase4-infographic-generation, Property 1: VisualSpec round-trip
@h_settings(max_examples=100)
@given(
    day_number=st.integers(min_value=1, max_value=365),
    title=st.text(min_size=1, max_size=100),
    subtitle=st.text(min_size=0, max_size=100),
    visual_concept=st.text(min_size=1, max_size=200),
    diagram_type=st.sampled_from(["flowchart", "hierarchy", "comparison", "timeline", "list"]),
    diagram_nodes=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10),
    key_points=st.lists(st.text(min_size=1, max_size=100), min_size=3, max_size=5),
    style=st.sampled_from(["dark-tech", "light-minimal", "blue-gradient"]),
    aspect_ratio=st.sampled_from(["1:1", "4:5", "16:9"]),
)
def test_visual_spec_round_trip(
    day_number, title, subtitle, visual_concept, diagram_type,
    diagram_nodes, key_points, style, aspect_ratio
):
    """
    **Validates: Requirements 1.8, 11.3**
    For any valid VisualSpec v, VisualSpec.model_validate(v.model_dump()) == v
    """
    v = VisualSpec(
        day_number=day_number,
        title=title,
        subtitle=subtitle,
        visual_concept=visual_concept,
        diagram_type=diagram_type,
        diagram_nodes=diagram_nodes,
        key_points=key_points,
        style=style,
        aspect_ratio=aspect_ratio,
    )
    round_tripped = VisualSpec.model_validate(v.model_dump())
    assert round_tripped == v


# Feature: phase4-infographic-generation, Property 2: MockImageProvider returns valid PNG for any non-empty prompt
@h_settings(max_examples=100)
@given(prompt=st.text(min_size=1, max_size=500))
def test_mock_provider_returns_valid_png(prompt):
    """
    **Validates: Requirements 2.2, 2.3, 11.4, 11.6 (via pbt)**
    For any non-empty prompt, MockImageProvider returns valid PNG with magic bytes
    and is deterministic (same prompt returns same bytes).
    """
    provider = MockImageProvider()
    result1 = asyncio.run(provider.generate(prompt))
    result2 = asyncio.run(provider.generate(prompt))

    # Check PNG magic bytes
    assert result1.startswith(b"\x89PNG\r\n\x1a\n")
    assert result2.startswith(b"\x89PNG\r\n\x1a\n")

    # Check determinism
    assert result1 == result2


# Feature: phase4-infographic-generation, Property 3: HTML template always contains title
@h_settings(max_examples=100)
@given(
    day_number=st.integers(min_value=1, max_value=365),
    title=st.text(min_size=1, max_size=100),
    subtitle=st.text(min_size=0, max_size=100),
    visual_concept=st.text(min_size=1, max_size=200),
    diagram_type=st.sampled_from(["flowchart", "hierarchy", "comparison", "timeline", "list"]),
    diagram_nodes=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=10),
    key_points=st.lists(st.text(min_size=1, max_size=100), min_size=3, max_size=5),
    style=st.sampled_from(["dark-tech", "light-minimal", "blue-gradient"]),
    aspect_ratio=st.sampled_from(["1:1", "4:5", "16:9"]),
)
def test_html_template_contains_title(
    day_number, title, subtitle, visual_concept, diagram_type,
    diagram_nodes, key_points, style, aspect_ratio
):
    """
    **Validates: Requirements 5.2, 5.9, 11.6**
    For any valid VisualSpec v, build_html(v, b"") contains v.title (HTML-escaped if needed)
    """
    import html as html_lib
    
    v = VisualSpec(
        day_number=day_number,
        title=title,
        subtitle=subtitle,
        visual_concept=visual_concept,
        diagram_type=diagram_type,
        diagram_nodes=diagram_nodes,
        key_points=key_points,
        style=style,
        aspect_ratio=aspect_ratio,
    )
    html = build_html(v, b"")
    # Check for HTML-escaped version of title (handles special chars like quotes)
    assert html_lib.escape(v.title) in html


# ===========================================================================
# Integration test (Playwright, @pytest.mark.integration)
# ===========================================================================

@pytest.mark.integration
def test_playwright_renders_correct_dimensions(tmp_path):
    """
    pytest.importorskip("playwright");
    call asyncio.run(render_html_to_png(html, tmp_path / "out.png", 1080, 1080));
    open with PIL.Image.open; assert img.size == (1080, 1080).
    **Validates: Requirements 6.1, 6.2, 11.7**
    """
    pytest.importorskip("playwright")
    from app.services.image_renderer import render_html_to_png

    html = """<!DOCTYPE html>
<html>
<head><style>
body { width: 1080px; height: 1080px; background: #0a0a1a; margin: 0; }
</style></head>
<body><div>Test</div></body>
</html>"""

    output_path = tmp_path / "out.png"
    asyncio.run(render_html_to_png(html, output_path, 1080, 1080))

    # Verify file exists and has correct dimensions
    assert output_path.exists()
    img = Image.open(output_path)
    assert img.size == (1080, 1080)
