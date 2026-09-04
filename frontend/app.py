"""
Streamlit frontend — Phase 1-4: AI LinkedIn Content Planner + Post Generation + Infographics.

Tab 1 (📅 Content Planner):
  - Form to generate a day-by-day LinkedIn learning plan via the backend API
  - Results table: Day | Topic | Category | Difficulty | Objective
  - Actions: Regenerate, Delete Plan

Tab 2 (📊 System Status):
  - Phase 1 health/status dashboard (unchanged)

Tab 3 (📋 Content Calendar):
  - Select a content plan
  - Per-row table: Day | Topic | Status | Actions
  - Actions per row: Generate, View, Edit, Regenerate, Approve
  - Generate All Posts button (bulk)
  - View: expander with post content, status, timestamp
  - Edit: text_area pre-filled with content + Save button

Tab 4 (🎨 Infographic):
  - Phase 4: Cloudflare Workers AI infographic generation
  - Select a post
  - Preview and edit InfographicSpec
  - Generate infographic with Cloudflare Flux
  - Download PNG
  - Retry failed generations
"""
import logging
import os
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = 5
GENERATE_TIMEOUT_SECONDS = 180  # LLM can be slow
BULK_GENERATE_TIMEOUT_SECONDS = 600  # bulk generation of all posts

st.set_page_config(
    page_title="LinkedIn AI Content Generator",
    page_icon="🧠",
    layout="wide",
)


# ──────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────

def fetch_json(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bool, dict | None, str | None]:
    """GET a URL. Returns (success, json_data, error_message). Never raises."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.ConnectionError:
        msg = f"Could not connect to backend at {url}. Is FastAPI running?"
        logger.warning(msg)
        return False, None, msg
    except requests.exceptions.Timeout:
        msg = f"Request to {url} timed out."
        logger.warning(msg)
        return False, None, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"Unexpected error calling {url}: {exc}"
        logger.error(msg)
        return False, None, msg


def fetch_bytes(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bool, bytes | None, str | None]:
    """GET binary content such as a generated PNG without JSON decoding."""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return True, response.content, None
    except requests.exceptions.ConnectionError:
        return False, None, f"Could not connect to backend at {url}. Is FastAPI running?"
    except requests.exceptions.Timeout:
        return False, None, f"Request to {url} timed out."
    except requests.exceptions.HTTPError as exc:
        return False, None, f"API error ({exc.response.status_code}): {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"Unexpected error calling {url}: {exc}"


def post_json(url: str, payload: dict, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bool, dict | None, str | None]:
    """POST JSON to a URL. Returns (success, json_data, error_message). Never raises."""
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.ConnectionError:
        msg = f"Could not connect to backend at {url}. Is FastAPI running?"
        logger.warning(msg)
        return False, None, msg
    except requests.exceptions.Timeout:
        msg = f"Request to {url} timed out. The LLM may need more time — try fewer days."
        logger.warning(msg)
        return False, None, msg
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        msg = f"API error ({exc.response.status_code}): {detail}"
        logger.warning(msg)
        return False, None, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"Unexpected error calling {url}: {exc}"
        logger.error(msg)
        return False, None, msg


def put_json(url: str, payload: dict, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bool, dict | None, str | None]:
    """PUT JSON to a URL. Returns (success, json_data, error_message). Never raises."""
    try:
        response = requests.put(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.ConnectionError:
        msg = f"Could not connect to backend at {url}. Is FastAPI running?"
        logger.warning(msg)
        return False, None, msg
    except requests.exceptions.Timeout:
        msg = f"Request to {url} timed out."
        logger.warning(msg)
        return False, None, msg
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        msg = f"API error ({exc.response.status_code}): {detail}"
        logger.warning(msg)
        return False, None, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"Unexpected error calling {url}: {exc}"
        logger.error(msg)
        return False, None, msg


def delete_request(url: str) -> tuple[bool, str | None]:
    """DELETE a URL. Returns (success, error_message). Never raises."""
    try:
        response = requests.delete(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return True, None
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return False, f"API error ({exc.response.status_code}): {detail}"
    except Exception as exc:  # noqa: BLE001
        return False, f"Unexpected error: {exc}"


def render_status_badge(label: str, is_ok: bool, detail: str = "") -> None:
    """Render a colored status line for a given component."""
    icon = "✅" if is_ok else "❌"
    st.markdown(f"**{label}:** {icon} {'Connected' if is_ok else 'Not Connected'}")
    if detail:
        st.caption(detail)


# ──────────────────────────────────────────────
# Tab 1: Content Planner (UNCHANGED)
# ──────────────────────────────────────────────

def render_content_planner() -> None:
    st.header("🧠 AI LinkedIn Content Planner")
    st.caption("Generate a structured day-by-day LinkedIn learning series powered by local AI.")

    # ── Input form ──
    with st.form("content_plan_form"):
        main_subject = st.text_input(
            "Main subject",
            value=st.session_state.get("form_main_subject", ""),
            placeholder="e.g. Generative AI",
        )
        col1, col2 = st.columns(2)
        with col1:
            number_of_days = st.number_input(
                "Number of days",
                min_value=1,
                max_value=100,
                value=st.session_state.get("form_number_of_days", 30),
                step=1,
            )
        with col2:
            difficulty = st.selectbox(
                "Difficulty",
                options=[
                    "Beginner",
                    "Beginner → Intermediate",
                    "Intermediate",
                    "Intermediate → Advanced",
                    "Advanced",
                ],
                index=st.session_state.get("form_difficulty_index", 1),
            )
        audience = st.text_input(
            "Audience",
            value=st.session_state.get("form_audience", ""),
            placeholder="e.g. Students and developers",
        )
        submitted = st.form_submit_button("🚀 Generate Content Plan")

    if submitted:
        if not main_subject.strip():
            st.error("Please enter a main subject.")
            return
        if not audience.strip():
            st.error("Please enter an audience description.")
            return

        difficulty_options = [
            "Beginner", "Beginner → Intermediate", "Intermediate",
            "Intermediate → Advanced", "Advanced",
        ]
        st.session_state["form_main_subject"] = main_subject
        st.session_state["form_number_of_days"] = number_of_days
        st.session_state["form_difficulty_index"] = difficulty_options.index(difficulty)
        st.session_state["form_audience"] = audience
        st.session_state["last_payload"] = {
            "main_subject": main_subject,
            "number_of_days": int(number_of_days),
            "audience": audience,
            "difficulty": difficulty,
        }

        with st.spinner(f"Generating {int(number_of_days)}-day plan for '{main_subject}'… This may take up to 2 minutes."):
            ok, data, err = post_json(
                f"{BACKEND_URL}/api/content-plans/generate",
                st.session_state["last_payload"],
                timeout=GENERATE_TIMEOUT_SECONDS,
            )

        if not ok or data is None:
            st.error(f"Failed to generate plan: {err}")
            return

        st.session_state["current_plan"] = data.get("plan")
        plan = data.get("plan", {})
        st.session_state["saved_plan_id"] = plan.get("id") if plan else None
        st.success(data.get("message", "Plan generated!"))

    plan = st.session_state.get("current_plan")
    if plan:
        topics = plan.get("topics", [])
        if topics:
            df = pd.DataFrame([
                {
                    "Day": t["day_number"],
                    "Topic": t["title"],
                    "Category": t["category"],
                    "Difficulty": t["difficulty"],
                    "Objective": t["learning_objective"],
                }
                for t in sorted(topics, key=lambda x: x["day_number"])
            ])
            st.subheader(f"📅 {plan.get('main_subject', '')} — {len(topics)}-Day Plan")
            st.dataframe(df, use_container_width=True, hide_index=True)

            col_regen, col_delete, _ = st.columns([1, 1, 4])

            with col_regen:
                if st.button("🔄 Regenerate"):
                    payload = st.session_state.get("last_payload")
                    if payload:
                        with st.spinner("Regenerating plan…"):
                            ok, data, err = post_json(
                                f"{BACKEND_URL}/api/content-plans/generate",
                                payload,
                                timeout=GENERATE_TIMEOUT_SECONDS,
                            )
                        if not ok or data is None:
                            st.error(f"Regeneration failed: {err}")
                        else:
                            st.session_state["current_plan"] = data.get("plan")
                            new_plan = data.get("plan", {})
                            st.session_state["saved_plan_id"] = new_plan.get("id") if new_plan else None
                            st.success("Plan regenerated!")
                            st.rerun()

            with col_delete:
                plan_id = st.session_state.get("saved_plan_id")
                if plan_id and st.button("🗑️ Delete Plan"):
                    ok, err = delete_request(f"{BACKEND_URL}/api/content-plans/{plan_id}")
                    if ok:
                        st.session_state["current_plan"] = None
                        st.session_state["saved_plan_id"] = None
                        st.success("Plan deleted.")
                        st.rerun()
                    else:
                        st.error(f"Delete failed: {err}")


# ──────────────────────────────────────────────
# Tab 2: System Status (UNCHANGED)
# ──────────────────────────────────────────────

def render_system_status() -> None:
    st.header("📊 System Status")
    st.caption("Phase 1 infrastructure health dashboard.")

    health_ok, health_data, health_error = fetch_json(f"{BACKEND_URL}/health")
    render_status_badge(
        "Backend (FastAPI)",
        health_ok and health_data is not None and health_data.get("status") == "ok",
        health_error or (f"Response: {health_data}" if health_data else ""),
    )

    status_ok, status_data, status_error = fetch_json(f"{BACKEND_URL}/status")
    if status_ok and status_data:
        db_info = status_data.get("database", {})
        ollama_info = status_data.get("ollama", {})

        render_status_badge(
            "Database (PostgreSQL)",
            db_info.get("connected", False),
            db_info.get("message", ""),
        )
        render_status_badge(
            "Ollama (Local LLM)",
            ollama_info.get("connected", False),
            ollama_info.get("message", ""),
        )

        st.divider()
        st.subheader("Configured Model")
        model_name = ollama_info.get("model", "unknown")
        model_available = ollama_info.get("model_available")
        if model_available is True:
            st.success(f"Model **{model_name}** is pulled and ready.")
        elif model_available is False:
            st.warning(f"Model **{model_name}** is configured but not pulled. Run: `ollama pull {model_name}`")
        else:
            st.info(f"Configured model: **{model_name}** (availability unknown — Ollama unreachable)")
    else:
        st.error(f"Could not retrieve system status: {status_error}")
        render_status_badge("Database (PostgreSQL)", False, "Unknown — backend /status unreachable")
        render_status_badge("Ollama (Local LLM)", False, "Unknown — backend /status unreachable")


# ──────────────────────────────────────────────
# Tab 3: Content Calendar (NEW)
# ──────────────────────────────────────────────

def render_content_calendar() -> None:
    """Render the Content Calendar tab for generating and managing LinkedIn posts."""
    st.header("📋 Content Calendar")
    st.caption("Generate, review, edit, and approve LinkedIn posts for each day of a content plan.")

    # ── Plan selector ──
    ok, plans_data, err = fetch_json(f"{BACKEND_URL}/api/content-plans/")
    if not ok or plans_data is None:
        st.error(f"Could not load plans: {err}")
        return

    if not plans_data:
        st.info("No content plans found. Go to the **Content Planner** tab to create one first.")
        return

    plan_options = {
        f"{p['main_subject']} ({p['number_of_days']} days)": p["id"]
        for p in plans_data
    }
    selected_label = st.selectbox("Select a content plan", list(plan_options.keys()))
    plan_id = plan_options[selected_label]

    # ── Load full plan ──
    ok, plan_resp, err = fetch_json(f"{BACKEND_URL}/api/content-plans/{plan_id}")
    if not ok or plan_resp is None:
        st.error(f"Could not load plan details: {err}")
        return

    topics = sorted(plan_resp["plan"]["topics"], key=lambda t: t["day_number"])

    # ── Load existing posts for this plan ──
    ok, posts_resp, _ = fetch_json(f"{BACKEND_URL}/api/posts/by-plan/{plan_id}")
    posts_by_topic: dict[str, dict] = {}
    if ok and posts_resp:
        for post in posts_resp:
            posts_by_topic[post["day_topic_id"]] = post

    # ── Generate All Posts button ──
    if st.button("🚀 Generate All Posts", help="Generate posts for all days sequentially. This may take several minutes."):
        with st.spinner("Generating all posts sequentially — this may take several minutes…"):
            ok, result, err = post_json(
                f"{BACKEND_URL}/api/content-plans/{plan_id}/generate-posts",
                {},
                timeout=BULK_GENERATE_TIMEOUT_SECONDS,
            )
        if ok and result:
            generated = result.get("generated", 0)
            failed = result.get("failed", 0)
            if failed == 0:
                st.success(f"✅ Generated {generated} posts successfully.")
            else:
                st.warning(f"Generated {generated} posts, {failed} failed.")
            st.rerun()
        else:
            st.error(f"Bulk generation failed: {err}")

    st.divider()

    # ── Column headers ──
    hcol1, hcol2, hcol3, hcol4 = st.columns([1, 4, 2, 5])
    with hcol1:
        st.markdown("**Day**")
    with hcol2:
        st.markdown("**Topic**")
    with hcol3:
        st.markdown("**Status**")
    with hcol4:
        st.markdown("**Actions**")

    st.divider()

    # ── Per-row calendar ──
    for topic in topics:
        topic_id = topic["id"]
        post = posts_by_topic.get(topic_id)
        has_post = post is not None
        status_label = post["status"] if has_post else "—"

        col_day, col_topic, col_status, col_actions = st.columns([1, 4, 2, 5])

        with col_day:
            st.write(f"**{topic['day_number']}**")
        with col_topic:
            st.write(topic["title"])
        with col_status:
            # Color-code status
            if status_label == "APPROVED":
                st.success(status_label)
            elif status_label == "FAILED":
                st.error(status_label)
            elif status_label == "DRAFT":
                st.info(status_label)
            else:
                st.write(status_label)

        with col_actions:
            a1, a2, a3, a4, a5 = st.columns(5)

            with a1:
                gen_label = "🔄" if has_post else "⚡"
                if st.button(gen_label, key=f"gen_{topic_id}", help="Generate post"):
                    with st.spinner(f"Generating day {topic['day_number']}…"):
                        ok, resp_data, err = post_json(
                            f"{BACKEND_URL}/api/posts/generate/{topic_id}",
                            {},
                            timeout=GENERATE_TIMEOUT_SECONDS,
                        )
                    if ok and resp_data and resp_data.get("success"):
                        st.rerun()
                    elif ok and resp_data and not resp_data.get("success"):
                        st.error(f"Generation failed — stored as FAILED.")
                        st.rerun()
                    else:
                        st.error(f"Error: {err}")

            with a2:
                view_clicked = st.button(
                    "👁", key=f"view_{topic_id}",
                    disabled=not has_post,
                    help="View post",
                )
            with a3:
                edit_clicked = st.button(
                    "✏️", key=f"edit_{topic_id}",
                    disabled=not has_post,
                    help="Edit post",
                )
            with a4:
                if st.button(
                    "♻️", key=f"regen_{topic_id}",
                    disabled=not has_post,
                    help="Regenerate post",
                ):
                    with st.spinner(f"Regenerating day {topic['day_number']}…"):
                        ok, resp_data, err = post_json(
                            f"{BACKEND_URL}/api/posts/{post['id']}/regenerate",
                            {},
                            timeout=GENERATE_TIMEOUT_SECONDS,
                        )
                    if ok:
                        st.rerun()
                    else:
                        st.error(f"Regeneration failed: {err}")
            with a5:
                if st.button(
                    "✅", key=f"appr_{topic_id}",
                    disabled=not has_post or (has_post and post.get("status") == "APPROVED"),
                    help="Approve post",
                ):
                    ok, resp_data, err = post_json(
                        f"{BACKEND_URL}/api/posts/{post['id']}/approve",
                        {},
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
                    if ok:
                        st.rerun()
                    else:
                        st.error(f"Approval failed: {err}")

        # ── View expander ──
        if has_post and view_clicked:
            with st.expander(
                f"📄 Day {topic['day_number']}: {topic['title']}",
                expanded=True,
            ):
                st.caption(
                    f"**Status:** {post['status']}  |  "
                    f"**Version:** {post['version']}  |  "
                    f"**Generated:** {post.get('created_at', 'unknown')}"
                )
                st.text(post.get("content") or "*(no content)*")

        # ── Edit area ──
        if has_post and edit_clicked:
            st.markdown(f"**Editing Day {topic['day_number']}: {topic['title']}**")
            new_content = st.text_area(
                "Post content",
                value=post.get("content") or "",
                height=400,
                key=f"textarea_{topic_id}",
                label_visibility="collapsed",
            )
            save_col, cancel_col, _ = st.columns([1, 1, 4])
            with save_col:
                if st.button("💾 Save", key=f"save_{topic_id}"):
                    if not new_content.strip():
                        st.error("Content cannot be blank.")
                    else:
                        ok, resp_data, err = put_json(
                            f"{BACKEND_URL}/api/posts/{post['id']}",
                            {"content": new_content},
                            timeout=REQUEST_TIMEOUT_SECONDS,
                        )
                        if ok:
                            st.success("Saved!")
                            st.rerun()
                        else:
                            st.error(f"Save failed: {err}")


# ──────────────────────────────────────────────
# Tab 4: Infographic Generation (Phase 4)
# ──────────────────────────────────────────────

def render_infographic_generator() -> None:
    """Phase 4: Cloudflare Workers AI infographic generation."""
    st.header("🎨 Infographic Generator")
    st.caption("Phase 4: Generate professional educational infographics using Cloudflare Workers AI.")

    # Free quota warning
    st.info(
        "🔵 **Cloudflare Workers AI:** This uses Cloudflare's free daily neuron allocation. "
        "Usage beyond the free limit may require billing. "
        "[Learn more](https://developers.cloudflare.com/workers-ai/)"
    )

    # Step 1: Select a post
    st.subheader("1️⃣ Select a Post")

    # Load posts from the real content plans instead of a placeholder plan ID.
    all_posts: list[dict] = []
    seen_post_ids: set[str] = set()

    # Prefer the currently selected plan from the app state if available.
    current_plan = st.session_state.get("current_plan")
    if current_plan and current_plan.get("id"):
        ok_plan_posts, plan_posts_data, plan_posts_err = fetch_json(
            f"{BACKEND_URL}/api/posts/by-plan/{current_plan['id']}", timeout=30
        )
        if ok_plan_posts and plan_posts_data:
            for post in plan_posts_data:
                post_id = str(post.get("id"))
                if post_id not in seen_post_ids:
                    all_posts.append(post)
                    seen_post_ids.add(post_id)

    if not all_posts:
        ok_plans, plans_data, _ = fetch_json(f"{BACKEND_URL}/api/content-plans", timeout=10)
        if ok_plans and plans_data:
            for plan in plans_data:
                ok_posts, posts_for_plan, _ = fetch_json(
                    f"{BACKEND_URL}/api/posts/by-plan/{plan['id']}", timeout=10
                )
                if ok_posts and posts_for_plan:
                    for post in posts_for_plan:
                        post_id = str(post.get("id"))
                        if post_id not in seen_post_ids:
                            all_posts.append(post)
                            seen_post_ids.add(post_id)

    if not all_posts:
        ok_prev_posts, previous_posts_data, err = fetch_json(
            f"{BACKEND_URL}/api/posts/by-plan/00000000-0000-0000-0000-000000000000",
            timeout=10,
        )
        if ok_prev_posts and previous_posts_data:
            for post in previous_posts_data:
                post_id = str(post.get("id"))
                if post_id not in seen_post_ids:
                    all_posts.append(post)
                    seen_post_ids.add(post_id)

    if not all_posts:
        st.warning("No posts available. Generate posts first in the Content Calendar tab.")
        return

    # Filter posts with content
    posts_with_content = [p for p in all_posts if p.get("content")]
    if not posts_with_content:
        st.warning("No posts with content available.")
        return

    # Post selector
    post_options = {
        f"Day {p.get('day_number', '?')}: {p.get('content', '').split(chr(10))[0][:60]}": p
        for p in posts_with_content
    }

    selected_post_label = st.selectbox(
        "Select a post",
        options=list(post_options.keys()),
        label_visibility="collapsed",
    )

    selected_post = post_options.get(selected_post_label)
    if not selected_post:
        st.error("Post selection failed")
        return

    post_id = selected_post.get("id")

    # Step 2: Configure infographic
    st.subheader("2️⃣ Configure Infographic")

    col1, col2 = st.columns(2)

    with col1:
        num_panels = st.selectbox(
            "Number of panels",
            options=[3, 4],
            index=0,
            help="3 or 4 content panels"
        )

    with col2:
        theme = st.selectbox(
            "Visual theme",
            options=["blue_navy", "light_blue", "professional_tech"],
            index=0,
            help="Professional educational infographic style"
        )

    accent_color = st.selectbox(
        "Accent color",
        options=["cyan", "teal", "white", "navy"],
        index=0,
    )

    # Step 3: Generate
    st.subheader("3️⃣ Generate Infographic")

    col_gen, col_info = st.columns([2, 3])

    with col_gen:
        # Duplicate-click prevention using session state
        if "last_infographic_post_id" not in st.session_state:
            st.session_state["last_infographic_post_id"] = None
        if "last_infographic_generation_id" not in st.session_state:
            st.session_state["last_infographic_generation_id"] = None

        is_generating = (
            st.session_state.get("last_infographic_post_id") == post_id
            and st.session_state.get("last_infographic_generation_id") is not None
        )

        if st.button(
            "🚀 Generate Infographic",
            disabled=is_generating,
            key="btn_generate_infographic",
        ):
            st.session_state["last_infographic_post_id"] = post_id

            with st.spinner("Generating infographic with Cloudflare Flux…"):
                query = urlencode({
                    "num_panels": num_panels,
                    "theme": theme,
                    "accent_color": accent_color,
                })
                ok, resp_data, err = post_json(
                    f"{BACKEND_URL}/api/posts/{post_id}/infographic?{query}",
                    {},
                    timeout=180,  # Cloudflare can be slow
                )

            if ok and resp_data:
                generation = resp_data.get("generation")
                if generation:
                    st.session_state["last_infographic_generation_id"] = generation.get("id")
                    st.session_state["last_infographic_generation"] = generation
                    st.success(resp_data.get("message", "Infographic generated!"))
                    st.rerun()
                else:
                    st.error("Generation failed: No generation data returned")
            else:
                st.error(f"Generation failed: {err}")

    with col_info:
        st.markdown("**Provider:** 🔵 Cloudflare Workers AI (Flux)")
        st.markdown("**Model:** `@cf/black-forest-labs/flux-2-klein-9b`")
        st.markdown("**Size:** 1536 × 864 (16:9)")

    # Step 4: View result
    st.subheader("4️⃣ Generation Status & Download")

    if st.session_state.get("last_infographic_generation"):
        gen = st.session_state["last_infographic_generation"]
        gen_id = gen.get("id")

        # Fetch latest status
        ok, status_data, err = fetch_json(f"{BACKEND_URL}/api/infographics/{gen_id}")

        if ok and status_data:
            gen = status_data.get("generation")
            status = gen.get("status", "UNKNOWN")
            created_at = gen.get("created_at", "unknown")

            st.markdown(f"**Status:** `{status}`")
            st.markdown(f"**Generation ID:** `{gen_id}`")
            st.markdown(f"**Created:** {created_at}")

            if status == "COMPLETED":
                st.success("✅ Infographic ready!")

                # Download button
                if gen.get("output_path"):
                    ok_img, img_data, err_img = fetch_bytes(
                        f"{BACKEND_URL}/api/infographics/{gen_id}/image",
                        timeout=10,
                    )

                    if ok_img and img_data:
                        st.image(img_data, use_container_width=True)

                        # Download link
                        col_dl, col_retry = st.columns(2)
                        with col_dl:
                            st.download_button(
                                label="📥 Download PNG",
                                data=img_data,
                                file_name=f"infographic_{gen_id}.png",
                                mime="image/png",
                            )

                        with col_retry:
                            if st.button("🔄 Regenerate", key="btn_regenerate_image"):
                                ok, resp, err = post_json(
                                    f"{BACKEND_URL}/api/infographics/{gen_id}/retry",
                                    {"regenerate_image": True},
                                    timeout=180,
                                )
                                if ok:
                                    st.success("Regeneration started!")
                                    st.rerun()
                                else:
                                    st.error(f"Retry failed: {err}")

                    elif err_img:
                        st.error(f"Could not load image: {err_img}")

            elif status == "PROCESSING":
                st.info("⏳ Generating image… This may take 1-2 minutes.")
                if st.button("🔄 Refresh Status"):
                    st.rerun()

            elif status == "FAILED":
                error_msg = gen.get("error_message", "Unknown error")
                st.error(f"❌ Generation failed: {error_msg}")

                if st.button("🔄 Retry Generation"):
                    ok, resp, err = post_json(
                        f"{BACKEND_URL}/api/infographics/{gen_id}/retry",
                        {"regenerate_image": True},
                        timeout=180,
                    )
                    if ok:
                        st.success("Retry started!")
                        st.rerun()
                    else:
                        st.error(f"Retry failed: {err}")

            elif status == "PENDING":
                st.info("📋 Pending generation…")
                if st.button("🔄 Check Status"):
                    st.rerun()
    else:
        st.info("Generate an infographic to see results here.")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    st.title("🧠 LinkedIn AI Content Generator")

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 Content Planner",
        "📊 System Status",
        "📋 Content Calendar",
        "🎨 Infographic (Phase 4)",
    ])

    with tab1:
        render_content_planner()

    with tab2:
        render_system_status()

    with tab3:
        render_content_calendar()

    with tab4:
        render_infographic_generator()



if __name__ == "__main__":
    main()
