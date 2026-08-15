# Requirements Document

## Introduction

Phase 2 adds an AI-powered LinkedIn Content Planner on top of the Phase 1 infrastructure. Users provide a main subject, a duration in days, an audience description, and a difficulty level. The system uses a locally-running Ollama + Qwen3 4B model to generate a structured, curriculum-style day-by-day learning plan, persists it in PostgreSQL, and exposes full CRUD operations via a FastAPI backend and a Streamlit frontend.

All Phase 1 endpoints (`/health`, `/status`) and the Phase 1 Streamlit dashboard remain unchanged and fully functional.

---

## Glossary

- **Content_Planner**: The Phase 2 FastAPI + Streamlit application responsible for generating, storing, and serving LinkedIn content plans.
- **Curriculum_Service**: The backend service that constructs an LLM prompt, calls Ollama, parses the JSON response, and validates the resulting list of day topics.
- **ContentPlanRequest**: The Pydantic schema representing an incoming request to generate a plan (main_subject, number_of_days, audience, difficulty).
- **ContentPlan**: The Pydantic schema representing a full content plan including its list of `DayTopic` objects.
- **DayTopic**: A single entry in the plan representing one day's learning material (day_number, main_subject, title, short_description, difficulty, category, learning_objective).
- **ContentPlanModel**: The SQLAlchemy ORM model mapped to the `content_plans` PostgreSQL table.
- **DayTopicModel**: The SQLAlchemy ORM model mapped to the `day_topics` PostgreSQL table with a foreign key to `ContentPlanModel`.
- **Ollama_Client**: The component that sends HTTP POST requests to the Ollama `/api/generate` endpoint and returns the raw text response.
- **JSON_Parser**: The component within Curriculum_Service that extracts and repairs a JSON array from the raw LLM text response.
- **Duplicate_Detector**: The component within Curriculum_Service that validates uniqueness of day numbers and topic titles.
- **Plan_Repository**: The component responsible for all database read/write/delete operations for `ContentPlanModel` and `DayTopicModel`.
- **Frontend_UI**: The Streamlit application providing the content planner form, result table, and action buttons.
- **UUID**: Universally Unique Identifier used as the primary key for database records.

---

## Requirements

### Requirement 1: Content Plan Generation via LLM

**User Story:** As a LinkedIn content creator, I want to generate a day-by-day learning plan for a given subject, so that I can plan a structured educational content series for my audience.

#### Acceptance Criteria

1. WHEN a POST request is made to `/api/content-plans/generate` with a valid `ContentPlanRequest`, THE `Content_Planner` SHALL call the `Curriculum_Service` to generate a list of `DayTopic` objects equal in count to `number_of_days`.
2. WHEN the `Curriculum_Service` is invoked, THE `Ollama_Client` SHALL send an HTTP POST request to `{OLLAMA_BASE_URL}/api/generate` using the `qwen3:4b` model with `stream` set to `false`.
3. WHEN constructing the LLM prompt, THE `Curriculum_Service` SHALL include instructions requiring the model to return ONLY a valid JSON array with no markdown fences, no commentary, and no `<think>` tags.
4. WHEN constructing the LLM prompt, THE `Curriculum_Service` SHALL include instructions enforcing a logical learning progression from fundamentals to advanced concepts, no duplicate topics, no near-duplicate topics, no unrelated topics, real-world learning objectives, and concise titles.
5. WHEN the LLM response is received, THE `JSON_Parser` SHALL extract and parse the JSON array from the raw response text.
6. IF the raw LLM response contains malformed or non-JSON content, THEN THE `JSON_Parser` SHALL attempt to extract a valid JSON array substring before raising a parse error.
7. IF the JSON cannot be repaired or parsed after extraction attempts, THEN THE `Curriculum_Service` SHALL raise a descriptive error indicating that the LLM returned unparseable content.
8. WHEN the parsed list of `DayTopic` objects is produced, THE `Curriculum_Service` SHALL validate that day numbers are sequential starting from 1 and contain no duplicates.
9. WHEN the parsed list of `DayTopic` objects is produced, THE `Duplicate_Detector` SHALL validate that all topic titles are unique with no near-duplicate titles.
10. IF day number validation fails, THEN THE `Curriculum_Service` SHALL raise a descriptive validation error identifying the conflicting day numbers.
11. IF duplicate title validation fails, THEN THE `Curriculum_Service` SHALL raise a descriptive validation error identifying the conflicting titles.

---

### Requirement 2: Content Plan Persistence

**User Story:** As a content creator, I want generated plans to be saved to the database automatically, so that I can retrieve and reuse them later without regenerating.

#### Acceptance Criteria

1. WHEN a content plan is successfully generated, THE `Plan_Repository` SHALL persist one `ContentPlanModel` record containing `main_subject`, `number_of_days`, `audience`, `difficulty`, and a UUID primary key.
2. WHEN a content plan is persisted, THE `Plan_Repository` SHALL persist one `DayTopicModel` record per day, each containing `day_number`, `main_subject`, `title`, `short_description`, `difficulty`, `category`, `learning_objective`, a UUID primary key, and a foreign key referencing the parent `ContentPlanModel`.
3. WHEN a `ContentPlanModel` is created, THE `Plan_Repository` SHALL assign a `created_at` timestamp with the UTC time of creation.
4. WHEN a `DayTopicModel` is deleted by cascading from its parent `ContentPlanModel`, THE `Plan_Repository` SHALL remove all associated `DayTopicModel` records from the database.

---

### Requirement 3: Content Plan Retrieval

**User Story:** As a content creator, I want to retrieve previously generated plans, so that I can review or reuse them without re-invoking the LLM.

#### Acceptance Criteria

1. WHEN a GET request is made to `/api/content-plans/`, THE `Content_Planner` SHALL return a list of all stored content plans containing at minimum `id`, `main_subject`, `number_of_days`, and `created_at` for each plan.
2. WHEN a GET request is made to `/api/content-plans/{plan_id}`, THE `Content_Planner` SHALL return the full `ContentPlan` including all associated `DayTopic` objects for the specified plan.
3. IF the specified `plan_id` does not exist in the database, THEN THE `Content_Planner` SHALL return an HTTP 404 response with a descriptive error message.

---

### Requirement 4: Content Plan Deletion

**User Story:** As a content creator, I want to delete plans I no longer need, so that I can keep my plan list clean and relevant.

#### Acceptance Criteria

1. WHEN a DELETE request is made to `/api/content-plans/{plan_id}`, THE `Content_Planner` SHALL remove the `ContentPlanModel` record and all associated `DayTopicModel` records from the database.
2. WHEN a plan is successfully deleted, THE `Content_Planner` SHALL return an HTTP 200 response confirming deletion.
3. IF the specified `plan_id` does not exist, THEN THE `Content_Planner` SHALL return an HTTP 404 response with a descriptive error message.

---

### Requirement 5: API Input Validation

**User Story:** As a developer integrating with the API, I want the API to validate all inputs, so that invalid requests are rejected with clear error messages before reaching the LLM or database.

#### Acceptance Criteria

1. WHEN a POST request to `/api/content-plans/generate` is missing any required field (`main_subject`, `number_of_days`, `audience`, `difficulty`), THE `Content_Planner` SHALL return an HTTP 422 response with a field-level error description.
2. WHEN `number_of_days` is less than 1 or greater than 100, THE `Content_Planner` SHALL return an HTTP 422 response indicating the value is out of range.
3. WHEN `main_subject` is an empty string or whitespace-only, THE `Content_Planner` SHALL return an HTTP 422 response indicating the field is required.
4. WHEN `audience` is an empty string or whitespace-only, THE `Content_Planner` SHALL return an HTTP 422 response indicating the field is required.
5. WHEN `difficulty` is an empty string or whitespace-only, THE `Content_Planner` SHALL return an HTTP 422 response indicating the field is required.

---

### Requirement 6: Database Schema Migration

**User Story:** As a developer, I want the database schema to be managed via Alembic migrations, so that schema changes are versioned and reproducible across environments.

#### Acceptance Criteria

1. THE `Content_Planner` SHALL include an Alembic configuration file at `backend/alembic.ini`.
2. THE `Content_Planner` SHALL include Alembic migration scripts in `backend/alembic/`.
3. WHEN Alembic `env.py` is loaded, THE `Content_Planner` SHALL import `Base` from `app.db.base` and import all ORM models so that autogenerate can discover all tables.
4. WHEN the initial migration is run, THE `Content_Planner` SHALL create the `content_plans` table and the `day_topics` table with all defined columns, constraints, and foreign keys.

---

### Requirement 7: LLM Error Handling

**User Story:** As a developer, I want LLM errors and unexpected responses to produce clear HTTP error responses, so that the frontend can surface useful feedback to users.

#### Acceptance Criteria

1. IF the Ollama server is unreachable during plan generation, THEN THE `Content_Planner` SHALL return an HTTP 503 response with a descriptive message indicating the LLM is unavailable.
2. IF the LLM returns a response that cannot be parsed into a valid JSON array after repair attempts, THEN THE `Content_Planner` SHALL return an HTTP 422 response with a message describing the parse failure.
3. IF the LLM returns duplicate day numbers, THEN THE `Content_Planner` SHALL return an HTTP 422 response with a message identifying the duplicate day numbers.
4. IF the LLM returns duplicate or near-duplicate topic titles, THEN THE `Content_Planner` SHALL return an HTTP 422 response with a message identifying the conflicting titles.
5. IF the Ollama HTTP request times out, THEN THE `Content_Planner` SHALL return an HTTP 504 response with a message indicating a timeout occurred.

---

### Requirement 8: Streamlit Frontend — Plan Generation UI

**User Story:** As a LinkedIn content creator, I want a web interface to generate and manage content plans, so that I can use the planner without interacting with the API directly.

#### Acceptance Criteria

1. WHEN a user opens the Streamlit application, THE `Frontend_UI` SHALL display a Phase 2 content planner section with input fields for `main_subject`, `number_of_days`, `audience`, and `difficulty`.
2. WHEN a user clicks the "Generate Content Plan" button, THE `Frontend_UI` SHALL POST a `ContentPlanRequest` to `/api/content-plans/generate` and display the resulting day-by-day plan as a table with columns: Day, Topic, Category, Difficulty, and Objective.
3. WHEN a generated plan is displayed, THE `Frontend_UI` SHALL provide a "🔄 Regenerate" button that re-submits the same request to generate a new plan.
4. WHEN a generated plan is displayed, THE `Frontend_UI` SHALL provide a "💾 Save Plan" button (or automatically save on generation — whichever is implemented, the plan must be retrievable via GET after the action).
5. WHEN a saved plan is displayed, THE `Frontend_UI` SHALL provide a "🗑️ Delete Plan" button that calls DELETE `/api/content-plans/{plan_id}` and clears the displayed plan.
6. WHILE the plan is being generated, THE `Frontend_UI` SHALL display a loading indicator so the user knows the request is in progress.
7. IF the API returns an error response, THE `Frontend_UI` SHALL display the error message to the user without crashing the application.

---

### Requirement 9: Phase 1 Compatibility

**User Story:** As a developer, I want Phase 1 endpoints and the Phase 1 dashboard to remain fully functional after Phase 2 is added, so that monitoring and health checks are not disrupted.

#### Acceptance Criteria

1. WHEN Phase 2 code is deployed, THE `Content_Planner` SHALL continue to serve GET `/health` and GET `/status` with the same response schemas defined in Phase 1.
2. WHEN the Streamlit application is opened, THE `Frontend_UI` SHALL continue to display the Phase 1 status dashboard alongside the Phase 2 content planner (e.g., in a sidebar or separate section/tab).
3. THE `Content_Planner` SHALL register the Phase 2 router in `app/main.py` without removing or modifying the Phase 1 health router registration.

---

### Requirement 10: Pydantic Schemas

**User Story:** As a developer, I want all data shapes to be defined as Pydantic schemas, so that request validation, response serialization, and OpenAPI documentation are consistent.

#### Acceptance Criteria

1. THE `Content_Planner` SHALL define a `DayTopic` Pydantic model in `app/schemas/content_plan.py` with fields: `day_number` (int), `main_subject` (str), `title` (str), `short_description` (str), `difficulty` (str), `category` (str), `learning_objective` (str).
2. THE `Content_Planner` SHALL define a `ContentPlan` Pydantic model in `app/schemas/content_plan.py` with fields: `id` (optional UUID), `main_subject` (str), `number_of_days` (int), `audience` (str), `difficulty` (str), `topics` (list of `DayTopic`), `created_at` (optional datetime).
3. THE `Content_Planner` SHALL define a `ContentPlanRequest` Pydantic model in `app/schemas/content_plan.py` with fields: `main_subject` (str, non-empty), `number_of_days` (int, 1–100), `audience` (str, non-empty), `difficulty` (str, non-empty).
4. THE `Content_Planner` SHALL define a `ContentPlanResponse` Pydantic model in `app/schemas/content_plan.py` that wraps a `ContentPlan` with a `success` (bool) flag and a `message` (str).
