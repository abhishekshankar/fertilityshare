

**PROJECT 10K FORMAT**

**SYLLABUS**

AI Fertility Learning Platform

Product Requirements Document

| Field | Value |
| :---- | :---- |
| Version | 2.0.0 |
| Status | Active — Enhanced per Project 10K |
| Date | March 2026 |
| Tier | Startup (Sections 0–13) |
| Pipeline Stages | planning | design | orchestrate | code | test | deploy | automation |
| Decisions Locked | Fertility vertical · Custom LangGraph · Audio deferred to V3 |

*Every requirement is a testable predicate. Every section is stage-tagged. Every change is versioned.*

# **Table of Contents**

# **Section 0: Document Metadata**

**\[planning\]  \[design\]  \[orchestrate\]  \[code\]  \[test\]  \[deploy\]  \[automation\]**

| Field | Value |
| :---- | :---- |
| PRD ID | SYLLABUS-PRD-001 |
| Version | 2.0.0 (semver: major.minor.patch) |
| Status | Active |
| Owner | Product Lead |
| Last Updated | 2026-03-09 |
| Changelog | v1.1 → v2.0: Restructured per Project 10K 15-section template. Added Gherkin AC, stage tags, NFRs as KV pairs, agent boundaries, risk register with mitigations, success metrics with kill thresholds. |
| Alignment Drift Score | 0 (freshly baselined) |
| Ambiguity Index | Low — all requirements have testable predicates |

# **Section 1: Problem & Context**

**\[planning\]**

## **1.1 Problem Statement**

People going through fertility journeys — IUI, IVF, egg freezing, failed cycles — are overwhelmed. Clinics are time-constrained and cannot educate beyond the immediate protocol. Google returns conflicting Reddit threads. ChatGPT gives generic answers that feel unsafe to trust. There is no structured, medically-grounded, emotionally-aware educational product that meets a person where they are in their fertility journey and walks them through it systematically.

## **1.2 Evidence & Quantification**

| Signal | Source | Data Point |
| :---- | :---- | :---- |
| Market gap | Oboe validation | AI-generated structured course model is fundable and wanted |
| Willingness to pay | Fertility vertical research | High WTP due to emotional urgency and information asymmetry |
| Content gap | Patient forums (r/infertility, FB groups) | Consistent complaints about jargon-heavy, conflicting information |
| Clinic limitation | RE practice research | Average consult is 15–20 min; no time for deep education |
| Trust deficit | User interviews | Generic AI answers feel unsafe for medical decisions |

## **1.3 Vision**

*The education your clinic doesn’t have time to give you.*

A patient learning they have PCOS, or starting their first IVF cycle, or processing a failed transfer should be able to generate a complete, personalized, medically-grounded learning plan in under 60 seconds — structured by their exact diagnosis, journey stage, and biggest areas of confusion.

## **1.4 Hypothesis**

**If** we provide structured, medically-grounded, emotionally-aware fertility education personalized to journey stage and diagnosis, **then** 70%+ of users will complete at least one full lesson and 40%+ will return within 7 days, **because** the current alternatives (generic search, rushed clinic visits, unstructured AI) fail to meet the intersection of medical accuracy, emotional sensitivity, and personalization that fertility patients need.

## **1.5 Strategic Context**

**Why fertility vertical first:** Sharper positioning, higher willingness to pay, clear community distribution channels (r/infertility, Facebook fertility groups, clinic partnerships). The Oboe model proves AI-generated structured courses work — this applies that model where the pain is deepest.

# **Section 2: Users & Personas**

**\[planning\]  \[design\]**

## **2.1 Persona Definitions**

| Persona | Journey Stage | Primary Need | WTP Signal |
| :---- | :---- | :---- | :---- |
| The Newly Diagnosed | Just got a diagnosis (PCOS, low AMH, MFI, unexplained) | Understand what it means without jargon | High — desperate for clarity |
| The Protocol Preparer | Preparing for first IUI or IVF cycle | Know what to expect, questions to ask RE | High — anxiety-driven |
| The Veteran | After failed cycle, or cycle 3+ | Deeper clinical understanding \+ processing grief | Very high — invested |
| The Egg Freezer | Elective preservation, usually younger | Lower urgency, high curiosity | Medium — preventive mindset |
| The Partner | Supporting someone through treatment | Understand partner’s experience | Medium — empathy-driven |

## **2.2 User Stories**

Each story is linked to features (Section 3), tagged with pipeline stages, and prioritized using MoSCoW.

**US-001 \[Must Have\]** \[planning\] \[code\] \[test\] → F-001

As a Newly Diagnosed patient, I want to describe my diagnosis and confusion in my own words so that I receive a personalized learning plan that starts from where I am.

**US-002 \[Must Have\]** \[planning\] \[code\] \[test\] → F-002

As a Protocol Preparer, I want to see my course being built in real time so that I trust the system is working and personalized for me.

**US-003 \[Must Have\]** \[planning\] \[code\] \[test\] → F-003

As any user, I want every lesson to end with “what to ask your RE” so that I never receive prescriptive medical advice.

**US-004 \[Must Have\]** \[planning\] \[code\] \[test\] → F-004

As a returning user, I want to resume my course from where I left off so that I can learn incrementally.

**US-005 \[Should Have\]** \[planning\] \[code\] \[test\] → F-005

As a Veteran, I want flashcards and quizzes generated from my lesson content so that I retain what I learn.

**US-006 \[Should Have\]** \[planning\] \[code\] \[test\] → F-006

As any user, I want to share my course via a public link so that others in my situation can benefit.

**US-007 \[Could Have\]** \[planning\] \[code\] \[test\] → F-007

As a Partner, I want a parallel version of my partner’s lessons reframed from the support role so that I understand what they’re going through.

## **2.3 Misuse Cases & Adversarial Personas**

| Adversarial Persona | Goal | Attack Vector | Mitigation |
| :---- | :---- | :---- | :---- |
| Medical Advice Seeker | Get prescriptive treatment decisions | Prompt injection through intake free text | QA node flags prescriptive language; compliance\_note block in every lesson |
| Content Scraper | Bulk-download generated courses for resale | API abuse on Pro tier | Rate limiting (Section 6.7); terms of service enforcement |
| Misinformation Amplifier | Share medically inaccurate course publicly | Generate, share, and promote without verification | RAG grounding \+ QA node \+ human nurse reviewer from V2 |

# **Section 3: Solution Definition & Scope**

**\[planning\]  \[design\]  \[code\]**

## **3.1 Solution Overview**

Syllabus is an AI fertility learning platform that takes a patient’s journey stage, diagnosis, confusion area, and knowledge level as intake, then generates a complete, personalized, medically-grounded course via a custom LangGraph pipeline. The output is a structured CourseSpec JSON consumed by a Next.js frontend that renders modules, lessons, content blocks, flashcards, and quizzes.

## **3.2 Core Concepts**

| Concept | Definition | Role |
| :---- | :---- | :---- |
| Intake | Journey stage \+ diagnosis \+ confusion area \+ level | Drives all downstream generation |
| CourseSpec (JSON) | Canonical artifact; all UI renderers consume this | Never hardcode content |
| Module | Thematic cluster (e.g., “Understanding Your Diagnosis”) | Top-level organization |
| Lesson | Single focused unit inside a module | Core learning unit |
| Content Block | Atomic unit: explanation, example, exercise, reflection, compliance\_note | Building block of lessons |
| Compliance Boundary | Every lesson ends with “what to ask your RE” | Never “what to do” |

## **3.3 Feature Specifications with Acceptance Criteria**

**Feature F-001: Intake Flow**

**Linked Stories:** US-001

**Description:** 4-step intake UI that captures journey stage, diagnosis, confusion area, and knowledge level.

**Complexity:** M

**Acceptance Criteria (Gherkin):**

Scenario: Complete intake happy path

  Given a new user lands on the intake page

  When they select "Preparing for first IVF" as journey stage

  And select "PCOS" as diagnosis

  And enter "I don't understand stim protocols" as confusion

  And select "beginner" as knowledge level

  Then the system submits a valid intake payload

  And the pipeline begins generation within 2 seconds

Scenario: Partial intake (no diagnosis)

  Given a user selects "I don't know yet" for diagnosis

  When they complete remaining steps

  Then the system generates a course with broader diagnostic education

  And does not assume any specific condition

**Edge Cases:**

| Condition | Expected Behavior | User Message | Severity |
| :---- | :---- | :---- | :---- |
| Empty free-text confusion field | System uses journey stage \+ diagnosis to infer confusion | "We’ll focus on the most common questions for your stage" | Medium |
| Injection attempt in free text | IntentNode sanitizes input; QA flags prescriptive output | Normal course generated | Critical |
| User selects all journey stages | System uses first selection only | "We’ll start with your primary stage" | Low |

**Feature F-002: Real-Time Generation Stream**

**Linked Stories:** US-002

**Description:** SSE-based progress stream showing pipeline state to user during course generation.

**Acceptance Criteria (Gherkin):**

Scenario: Generation progress stream

  Given a user has submitted a valid intake

  When the pipeline processes their request

  Then the UI displays sequential progress messages:

    "Parsing your intake..."

    "Building outline..."

    "Writing Lesson N of M..."

  And the total generation time is \< 75 seconds

  And the course page renders within 3 seconds of completion

**Feature F-003: Compliance Boundary Enforcement**

**Linked Stories:** US-003

**Description:** Every lesson contains a compliance\_note block styled as a soft banner, ending with “what to ask your RE.” QA node enforces this.

**Acceptance Criteria (Gherkin):**

Scenario: Compliance note present in every lesson

  Given a course has been generated

  When any lesson in the CourseSpec JSON is inspected

  Then it contains at least one block with type \= "compliance\_note"

  And the block text includes a question to ask a doctor

  And the block never contains prescriptive language

Scenario: QA node catches prescriptive violation

  Given the ContentNode produces a lesson with "you should take 150mg"

  When the QA node evaluates the lesson

  Then the lesson is flagged and regenerated

  And the violation is logged for monitoring

**Feature F-004: Course Persistence & Resume**

**Linked Stories:** US-004

**Acceptance Criteria (Gherkin):**

Scenario: Resume from last position

  Given a user has completed 3 of 6 lessons

  When they return to the course page

  Then the UI scrolls to lesson 4

  And the progress bar shows 50% completion

  And lessons 1-3 are marked as complete

**Feature F-005: Flashcards & Quizzes (V2)**

**Linked Stories:** US-005

**Acceptance Criteria (Gherkin):**

Scenario: Flashcard generation from lesson

  Given a lesson has been generated

  When the user opens flashcard mode

  Then at least 3 flashcards are displayed as flip cards

  And each flashcard maps to content in the lesson

  And spaced repetition intervals are tracked in Postgres

Scenario: End-of-module quiz

  Given a user completes all lessons in a module

  When they take the quiz

  Then at least 3 multiple-choice questions are presented

  And 1 short reflection question is presented

  And wrong answers show explanations

  And scores are stored permanently

**Feature F-006: Course Sharing (V2)**

**Linked Stories:** US-006

**Acceptance Criteria (Gherkin):**

Scenario: Share course via public link

  Given a user toggles "Share this course"

  Then a unique public slug URL is generated

  And anyone with the link can view (read-only)

  And viewers can "Copy to my library" to fork it

## **3.4 Scope Boundaries**

**In Scope (Per Version)**

| Version | Scope |
| :---- | :---- |
| V0 (2 weeks) | Pipeline \+ schema validation. CLI only. 5 LangGraph nodes. Pydantic CourseSpec. Manual eval across 10 prompts. |
| V1 (4 weeks post-V0) | MVP web app. Intake UI. SSE streaming. RAG (ASRM/PubMed). Auth. Dashboard. Feedback. Invite-only. |
| V2 (6 weeks post-V1) | Monetization. Flashcards/quizzes. Sharing. Stripe billing. Public API. |
| V3 (8 weeks post-V2) | Adaptive learning. Partner mode. Audio (TTS). Specialist content packs. Human review loop. |

**Out of Scope (All Versions)**

| Item | Rationale | Future? |
| :---- | :---- | :---- |
| Live coaching / human-in-the-loop tutoring | Doesn’t scale; changes product model | No |
| Prescriptive medical advice | Legal/ethical boundary; non-negotiable | Never |
| Video content generation | Complexity and cost vs. text value | Evaluate post-V3 |
| Native mobile app | Web-first; PWA if needed | Evaluate post-V3 |
| LMS / EHR integrations | Enterprise scope; premature | V4+ if demand |

## **3.5 Feature Prioritization (MoSCoW)**

| ID | Feature | Priority | Effort | Impact | Version |
| :---- | :---- | :---- | :---- | :---- | :---- |
| F-001 | Intake Flow | Must Have | M | H | V1 |
| F-002 | Generation Stream (SSE) | Must Have | M | H | V1 |
| F-003 | Compliance Enforcement | Must Have | S | Critical | V0 |
| F-004 | Course Persistence & Resume | Must Have | M | H | V1 |
| F-005 | Flashcards & Quizzes | Should Have | L | H | V2 |
| F-006 | Course Sharing | Should Have | M | M | V2 |
| F-007 | Partner Mode | Could Have | L | M | V3 |
| F-008 | Audio (TTS) | Could Have | L | M | V3 |
| F-009 | Adaptive Learning | Could Have | XL | H | V3 |
| F-010 | Billing (Stripe) | Must Have | M | Critical | V2 |

## **3.6 MVP Definition (V1)**

Walking skeleton: Intake → LangGraph pipeline (with RAG) → CourseSpec JSON → Rendered course page with module sidebar, lesson content, compliance notes, progress tracking, and lesson-level feedback. Auth via Google OAuth \+ email/password. All courses stored permanently per user.

# **Section 4: Design & UX Requirements**

**\[design\]  \[code\]**

## **4.1 Design Principles**

* Empathy first — tone is warm, never clinical or cold

* Progressive disclosure — don’t overwhelm; reveal complexity gradually

* Medical safety is visible — compliance notes are styled prominently, not hidden

* Trust through transparency — show citations, show generation progress, show what the AI doesn’t know

## **4.2 Key UI States**

| State | Description | Visual Treatment |
| :---- | :---- | :---- |
| Intake Flow | 4-step wizard: journey → diagnosis → confusion → level | Card-based steps, progress dots, warm illustrations |
| Generation Loading | SSE stream showing pipeline progress | Animated progress bar with descriptive messages |
| Course View | Module sidebar \+ lesson content area | Clean reading layout, compliance banners in soft blue/yellow |
| Flashcard Mode | Flip-card UI per lesson | Card stack with flip animation, spaced repetition counter |
| Quiz Mode | MCQ \+ reflection | Clean form, instant feedback per question, score summary |
| Dashboard | All courses, status, completion % | Card grid with progress indicators |
| Shared Course (Public) | Read-only view with “Copy to library” CTA | Stripped nav, prominent fork button |

## **4.3 Content Block Rendering**

| Block Type | Visual Treatment |
| :---- | :---- |
| explanation | Standard prose, comfortable reading width |
| example | Indented card with subtle background |
| exercise | Interactive prompt with text input area |
| reflection | Italic text in a distinct soft box |
| compliance\_note | Soft banner (blue/yellow), not alarming; distinct from content |

# **Section 5: Technical Architecture**

**\[design\]  \[orchestrate\]  \[code\]**

## **5.1 Tech Stack**

| Layer | Technology | Rationale |
| :---- | :---- | :---- |
| Pipeline | Python \+ LangGraph | Custom 5-node DAG; STORM pattern adapted |
| API | FastAPI | Async, SSE support, Pydantic native |
| Frontend | Next.js \+ Tailwind \+ Shadcn | SSR, modern React, rapid UI development |
| Database | Postgres (JSONB) | CourseSpec stored as JSONB; relational for users/progress |
| Cache | Redis | Session, rate limiting, generation queue |
| Storage | S3 | Audio files (V3), exports |
| Vector Store | Chroma or FAISS (V1) | RAG for ASRM/PubMed content |
| Auth | Google OAuth \+ email/password | Standard web auth |
| Payments | Stripe (V2) | Subscriptions \+ one-time content packs |

## **5.2 Pipeline Architecture**

Custom LangGraph graph. Five nodes in sequence. Research node is an LLM stub in V0, real RAG in V1.

IntentNode → OutlineNode → ResearchNode → ContentNode × N → QANode → CourseSpec JSON

| Node | Model | Function | V0 Behavior | V1+ Behavior |
| :---- | :---- | :---- | :---- | :---- |
| IntentNode | gpt-4o-mini | Parse raw intake into structured fields | Same | Same |
| OutlineNode | gpt-4o | Generate module/lesson structure with objectives | Same | Same |
| ResearchNode | gpt-4o-mini | Ground each lesson in key facts | LLM stub | RAG: ASRM/PubMed vector retrieval |
| ContentNode | gpt-4o (parallel) | Write all content blocks, flashcards, quiz | Same | Same \+ citations from RAG |
| QANode | Rules \+ gpt-4o-mini | Flag prescriptive language, missing compliance notes | Same | Same \+ violation logging |

## **5.3 API Contracts**

**POST /v1/generate**

Request: { journey\_stage: string, diagnosis: string | null,

          confusion: string, level: "beginner" | "intermediate" | "advanced" }

Response: { job\_id: string, status: "queued" }

**GET /v1/course/{id}**

Response: CourseSpec JSON (full schema in Pydantic model)

**GET /v1/generate/{job\_id}/stream (SSE)**

Event stream: { stage: string, message: string, progress: 0-100 }

## **5.4 CourseSpec Schema (Pydantic)**

CourseSpec {

  id: UUID, title: str, intake: IntakeData,

  modules: List\[Module {

    id: UUID, title: str, objective: str,

    lessons: List\[Lesson {

      id: UUID, title: str, objective: str,

      blocks: List\[ContentBlock {

        type: "explanation"|"example"|"exercise"|"reflection"|"compliance\_note",

        content: str, citations: List\[Citation\]? }\],

      flashcards: List\[Flashcard { front: str, back: str }\],

      quiz: Quiz { questions: List\[QuizQuestion\], reflection: str }

    }\]

  }\],

  metadata: { generated\_at: datetime, pipeline\_version: str, model\_versions: dict }

}

## **5.5 Project Structure**

syllabus/

├── pipeline/          \# LangGraph nodes

│   ├── intent.py       \# IntentNode

│   ├── outline.py      \# OutlineNode

│   ├── research.py     \# ResearchNode (stub → RAG)

│   ├── content.py      \# ContentNode

│   ├── qa.py           \# QANode

│   └── graph.py        \# LangGraph orchestration

├── api/               \# FastAPI routes

├── web/               \# Next.js frontend

├── models/            \# Pydantic schemas

├── rag/               \# Vector store \+ indexing

├── tests/             \# Test suites

└── PRD.md             \# This document (markdown mirror)

# **Section 6: Non-Functional Requirements**

**\[design\]  \[code\]  \[test\]  \[deploy\]**

## **6.1 Performance Budgets**

| Flow | P95 Latency | Max Payload | Throughput | Timeout |
| :---- | :---- | :---- | :---- | :---- |
| Intake submission | \< 500ms | 10KB | 100 RPS | 5s |
| Course generation (V0, no RAG) | \< 60s end-to-end | N/A | 10 concurrent | 90s |
| Course generation (V1, with RAG) | \< 75s end-to-end | N/A | 10 concurrent | 120s |
| Course page load (cached) | \< 2s TTI | 500KB | 500 RPS | 10s |
| API response (GET course) | \< 200ms | 2MB | 500 RPS | 5s |
| SSE stream latency | \< 1s between events | N/A | 50 concurrent streams | 120s |

## **6.2 Reliability & Availability**

| Metric | Target |
| :---- | :---- |
| Uptime SLA | 99.5% (V1 beta) → 99.9% (V2 production) |
| RPO (Recovery Point Objective) | \< 1 hour |
| RTO (Recovery Time Objective) | \< 4 hours |
| Data durability | 99.999999999% (Postgres \+ S3) |
| QA node compliance catch rate | 100% of injected violations |

## **6.3 Scalability**

| Metric | Launch (V1) | 12-Month Target |
| :---- | :---- | :---- |
| Concurrent users | 100 | 5,000 |
| Stored courses | 1,000 | 100,000 |
| Generation queue depth | 10 | 100 |
| Vector store documents | 500 (ASRM \+ PubMed) | 10,000 |

## **6.4 Security Requirements**

| Requirement | Implementation |
| :---- | :---- |
| Authentication | Google OAuth 2.0 \+ email/password (bcrypt) |
| Authorization | RBAC: user (own courses), admin (all courses \+ metrics) |
| Encryption at rest | AES-256 (Postgres, S3) |
| Encryption in transit | TLS 1.3 |
| Secrets management | Environment variables (V0–V1) → AWS Secrets Manager (V2+) |
| Audit logging | All auth events, generation requests, data access |
| Input sanitization | IntentNode sanitizes all user free-text before pipeline |

## **6.5 Rate Limiting**

| Endpoint Pattern | Limit | Window | Response |
| :---- | :---- | :---- | :---- |
| /v1/generate | Tier-based (Free: 2/mo, Plus: 15/mo, Pro: unlimited) | Monthly | 429 \+ tier upgrade prompt |
| /api/\* | 100 requests | 1 minute | 429 \+ Retry-After header |
| /v1/course/\* (public) | 30 requests | 1 minute | 429 |

# **Section 7: Agent Boundaries & Orchestration**

**\[orchestrate\]  \[code\]**

## **7.1 Agent Behavioral Boundaries**

**✅ Always:** 

* Run tests before committing

* Follow existing code patterns and project structure (Section 5.5)

* Use exact commands from Section 5.6 (see below)

* Match I/O contracts in Section 5.3

* Ensure every generated lesson has a compliance\_note block

**⚠️ Ask first:** 

* Database schema changes

* Adding new dependencies

* Modifying pipeline node order or model selection

* Changes to auth/permissions logic

**🚫 Never:** 

* Commit secrets or API keys

* Skip linting or tests

* Delete test files

* Generate prescriptive medical advice in any content block

* Bypass the QA node in the pipeline

## **7.2 Task Decomposition (V1 Sprint)**

| Task ID | Description | Depends On | Agent Role | Est. |
| :---- | :---- | :---- | :---- | :---- |
| T-001 | Implement IntentNode with Pydantic intake schema | None | Engineer | S |
| T-002 | Implement OutlineNode with module/lesson generation | T-001 | Engineer | M |
| T-003 | Implement ResearchNode (LLM stub for V0) | T-002 | Engineer | S |
| T-004 | Implement ContentNode with parallel execution | T-003 | Engineer | L |
| T-005 | Implement QANode with compliance rules | T-004 | Engineer | M |
| T-006 | Build FastAPI routes \+ SSE streaming | T-005 | Engineer | M |
| T-007 | Build Next.js intake UI (4-step wizard) | None | Engineer | M |
| T-008 | Build course rendering page | T-006 | Engineer | L |
| T-009 | Implement auth (Google OAuth \+ email) | None | Engineer | M |
| T-010 | Write unit tests for all pipeline nodes | T-001–T-005 | QA | M |
| T-011 | Write e2e tests for intake → course flow | T-006–T-008 | QA | M |
| T-012 | Index ASRM/PubMed into vector store | None | Engineer | M |
| T-013 | Upgrade ResearchNode to RAG | T-003, T-012 | Engineer | M |

## **7.3 Glossary / Semantic Metadata**

| Term | Definition | Usage Context |
| :---- | :---- | :---- |
| RE | Reproductive Endocrinologist (fertility doctor) | Compliance notes, lesson content |
| AMH | Anti-Müllerian Hormone — marker of ovarian reserve | Diagnosis context |
| MFI | Male Factor Infertility | Persona and intake |
| PGT-A | Preimplantation Genetic Testing for Aneuploidies | Clinical content (V3) |
| Stim Protocol | Medication regimen to stimulate egg production | IVF education content |
| CourseSpec | The canonical JSON artifact produced by the pipeline | Architecture, all code |
| Compliance Note | Mandatory block ending each lesson with questions for RE | QA node, content rendering |

# **Section 8: Testing & Quality Requirements**

**\[test\]  \[code\]**

## **8.1 Test Coverage Requirements**

| Test Type | Coverage Target | Tool | Scope |
| :---- | :---- | :---- | :---- |
| Unit tests | ≥ 80% line coverage | pytest | All pipeline nodes, API routes, utility functions |
| Integration tests | All critical paths | pytest \+ httpx | Intake → pipeline → CourseSpec → API response |
| E2E tests | Core user flows | Playwright | Intake → generation → course view → lesson complete |
| Compliance tests | 100% of injected violations caught | Custom test suite | QA node catches prescriptive language, missing blocks |
| Manual evaluation | 8/10 courses pass 5-dimension rubric | Human review | Medical accuracy, structure, tone, compliance, completeness |

## **8.2 Evaluation Rubric (Per Generated Course)**

| Dimension | Pass Criteria | Fail Criteria |
| :---- | :---- | :---- |
| Medical accuracy | Facts are correct; no prescriptive advice | Any factual error or prescriptive statement |
| Structural coherence | Lessons build logically; no gaps | Random ordering or missing prerequisite concepts |
| Tone | Empathetic, warm, accessible | Clinical, cold, or condescending |
| Compliance | Every lesson has compliance\_note block | Any lesson missing compliance\_note |
| Completeness | Quizzes and flashcards present in all lessons | Missing quiz or flashcards in any lesson |

## **8.3 V0 Test Prompts (10 Required)**

| \# | Test Prompt | Journey Stage |
| :---- | :---- | :---- |
| 1 | "I was just diagnosed with PCOS and I'm starting IUI next month" | Newly Diagnosed \+ Protocol Preparer |
| 2 | "My AMH is 0.8 and my doctor said I should consider IVF" | Newly Diagnosed |
| 3 | "We're about to start our first IVF cycle and I'm terrified" | Protocol Preparer |
| 4 | "Our third transfer just failed and I don't know what to do" | Veteran |
| 5 | "I'm 32 and thinking about freezing my eggs" | Egg Freezer |
| 6 | "My wife is going through IVF and I want to understand it better" | Partner |
| 7 | "I have unexplained infertility and have been trying for 2 years" | Veteran |
| 8 | "I don't have a diagnosis yet but we've been trying for a year" | Newly Diagnosed (no diagnosis) |
| 9 | "What is PGT-A testing and should I ask about it?" | Protocol Preparer (advanced) |
| 10 | "I just had my egg retrieval and got 4 eggs. Is that normal?" | Veteran (mid-cycle) |

# **Section 9: Observability & Analytics**

**\[deploy\]  \[automation\]**

## **9.1 Service Level Objectives**

| SLI (Indicator) | SLO (Objective) | Error Budget | Alert Threshold |
| :---- | :---- | :---- | :---- |
| Generation success rate | 99.0% | 1% over 30d | \< 95% over 5min |
| Course page P95 latency | \< 2s | — | \> 5s over 5min |
| API error rate | \< 0.5% | — | \> 2% over 5min |
| QA compliance catch rate | 100% | 0% tolerance | Any miss \= P1 |
| SSE stream health | 99.5% | 0.5% over 30d | \< 98% over 10min |

## **9.2 Event Tracking Plan**

| Event Name | Trigger | Properties | Dashboard |
| :---- | :---- | :---- | :---- |
| intake\_completed | User submits intake | journey\_stage, diagnosis, level | Activation |
| generation\_started | Pipeline begins | job\_id, intake\_hash | Pipeline Health |
| generation\_completed | Pipeline finishes | job\_id, duration\_ms, module\_count | Pipeline Health |
| generation\_failed | Pipeline error | job\_id, error\_type, node | Pipeline Health |
| lesson\_completed | User marks lesson done | course\_id, lesson\_id, time\_spent | Engagement |
| course\_shared | User toggles share | course\_id | Community |
| course\_forked | Viewer copies to library | source\_course\_id | Community |
| feedback\_submitted | User submits thumbs up/down | course\_id, lesson\_id, rating | Quality |
| subscription\_created | User subscribes | tier, price | Revenue |

## **9.3 Structured Logging**

* Format: JSON structured logs

* Required fields: timestamp, level, service, trace\_id, user\_id, action, pipeline\_node

* PII handling: user email hashed in logs; free-text intake redacted after IntentNode parsing

* Retention: ERROR/WARN — 90 days; INFO — 30 days; DEBUG — 7 days

# **Section 10: Deployment & Rollout**

**\[deploy\]  \[automation\]**

## **10.1 Deployment Strategy**

| Aspect | V0–V1 | V2+ |
| :---- | :---- | :---- |
| Method | Feature flags \+ rolling deploy | Canary deploys (10% → 50% → 100%) |
| Environments | Dev → Production | Dev → Staging → Production |
| CI/CD | GitHub Actions | GitHub Actions \+ automated rollback |
| Infrastructure | Backend: Railway; frontend: Vercel (Next.js) | Containerized (Docker) on AWS/GCP |

## **10.2 Rollback Plan**

* Database: point-in-time recovery (\< 1 hour RPO)

* Application: previous container image tag, automated rollback on P95 latency \> 5s

* Pipeline: model version pinning; rollback to previous model config if QA pass rate drops below 95%

* Feature flags: kill switch per feature; disable new features without full redeploy

## **10.3 Rollout Phases**

| Phase | Audience | Duration | Success Gate |
| :---- | :---- | :---- | :---- |
| V0 Internal | Team only (CLI) | 2 weeks | 8/10 test courses pass rubric |
| V1 Private Beta | 20–50 invited users (fertility community) | 4 weeks | 70%+ lesson completion, 0 compliance violations |
| V2 Public Launch | Open registration with billing | Ongoing | 15%+ conversion, MRR ≥ $3K in 30 days |
| V3 Expansion | All users \+ partner mode | Ongoing | 50%+ course completion, MRR ≥ $10K |

# **Section 11: Risk Register**

**\[planning\]  \[orchestrate\]**

| Risk | Likelihood | Impact | Mitigation | Owner | Status |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Medical accuracy failure (hallucination) | Medium | Critical | RAG grounding \+ QA node \+ human nurse reviewer from V2 | Pipeline Lead | Open |
| Users generate, don’t return | High | High | Streak mechanic \+ flashcards \+ nudge emails from V2 | Product Lead | Open |
| LLM cost at scale | Medium | High | gpt-4o-mini for planning nodes; gpt-4o only for writing; per-tier token budgets | Eng Lead | Open |
| Compliance / liability concern | Low | Critical | Consistent “not medical advice” framing; legal review before V1; compliance\_note in every lesson | Legal \+ Product | Open |
| Community doesn’t grow organically | Medium | Medium | Seed 20 high-quality shared courses; target r/infertility \+ FB groups | Growth Lead | Open |
| Generation latency kills UX | Medium | High | SSE progress streaming from V0; async queue; latency SLO monitoring | Eng Lead | Open |
| Vector store quality degrades content | Medium | High | Human-curated source selection; relevance scoring threshold; fallback to LLM stub | Pipeline Lead | Open |
| Stripe integration delays monetization | Low | Medium | Start Stripe integration early V2; use test mode throughout V1 | Eng Lead | Open |

# **Section 12: Success Metrics & Post-Launch**

**\[planning\]  \[automation\]**

## **12.1 Success Metrics by Version**

| Metric | Baseline | V1 Target | V2 Target | V3 Target | Kill Threshold |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Lesson completion rate | 0% | ≥ 70% | ≥ 75% | ≥ 80% | \< 40% |
| 7-day return rate | 0% | ≥ 40% | ≥ 50% | ≥ 60% | \< 20% |
| QA compliance catch rate | N/A | 100% | 100% | 100% | Any miss |
| NPS (beta cohort) | N/A | ≥ 45 | ≥ 50 | ≥ 55 | \< 30 |
| Generation time (P95) | N/A | \< 75s | \< 75s | \< 90s (with audio) | \> 120s |
| Free-to-paid conversion | N/A | N/A | ≥ 15% | ≥ 20% | \< 5% |
| MRR | $0 | $0 | ≥ $3K | ≥ $10K | \< $1K at V2+60d |
| Course completion (full) | 0% | N/A | ≥ 30% | ≥ 50% | \< 15% |
| Partner mode adoption | N/A | N/A | N/A | ≥ 30% of Plus/Pro | \< 10% |
| Content packs sold | 0 | 0 | 0 | ≥ 3 published \+ purchased | 0 after 30d |

## **12.2 Experiment Design (V1 Beta)**

**Hypothesis:** If we provide structured fertility education personalized to journey stage, then 70%+ of beta users complete at least one full lesson, because current alternatives lack personalization \+ medical grounding.

**Test type:** Cohort analysis (invite-only beta)

**Sample size:** 20–50 users minimum

**Duration:** 4 weeks

**Primary metric:** Lesson completion rate

**Guardrails:** 0 compliance violations, generation time \< 75s, NPS ≥ 45

## **12.3 Post-Launch Review Plan**

* Review date: 2 weeks post-V1 beta launch

* Metrics review: Compare actuals to V1 targets (12.1)

* User feedback synthesis: Aggregate per-lesson thumbs \+ NPS survey \+ free text

* Decision: Ship V2 / Iterate V1 / Kill

* Retrospective: Learnings fed back into pipeline tuning and content quality

# **Section 13: Stakeholders & Communication**

**\[planning\]  \[orchestrate\]**

## **13.1 RACI Matrix**

| Decision Area | Product Lead | Eng Lead | Pipeline Lead | Design | Legal |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Scope changes | A | C | C | I | I |
| Pipeline architecture | C | A | R | I | I |
| UX decisions | C | I | I | A | I |
| Compliance framing | R | I | C | I | A |
| Launch / no-go | A | R | R | C | C |
| Pricing decisions | A | C | I | I | C |
| Content quality standards | A | I | R | I | C |

## **13.2 Communication Plan**

| Audience | Channel | Frequency | Content |
| :---- | :---- | :---- | :---- |
| Engineering team | Standup / Slack | Daily | Progress, blockers, pipeline issues |
| Stakeholders | Status update | Weekly | Milestone progress, metrics, risks |
| Beta users | Email \+ in-app | Bi-weekly | New features, feedback requests |
| Community | r/infertility \+ FB | Weekly | Content teasers, shared courses |

## **13.3 Billing Structure (V2)**

| Tier | Price | Generations/mo | Features | Course Expiry |
| :---- | :---- | :---- | :---- | :---- |
| Free | $0 | 2 | Text only | 30 days |
| Plus | $12/mo | 15 | Flashcards \+ quizzes \+ permanent courses | Never |
| Pro | $29/mo | Unlimited | API access \+ private sharing \+ priority queue | Never |

## **13.4 Open Questions Resolved**

| Question | Decision | Rationale |
| :---- | :---- | :---- |
| Vertical or horizontal first? | Fertility vertical | Sharper positioning, higher WTP, clear community distribution |
| Audio priority? | Deferred to V3 | Placeholder in UI to gauge demand first; high implementation cost |
| STORM fork or custom LangGraph? | Custom LangGraph | STORM pattern adapted, not the codebase; more control over pipeline |
| Which vector store? | Chroma or FAISS (evaluate in V1 sprint) | Both lightweight; decision deferred to implementation |
| Human review loop timing? | V2 onward | Hire 1 fertility nurse educator as contract reviewer |

**End of PRD v2.0.0 — Project 10K Format**  
*Every requirement is a testable predicate. Every section is stage-tagged. Every change is versioned.*