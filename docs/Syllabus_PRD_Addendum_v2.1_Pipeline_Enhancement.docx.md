

**SYLLABUS**

**PRD Addendum**

**Pipeline Enhancement**

Prompting Architecture · Scaffolding Framework · Schema Extensions

| Field | Value |
| :---- | :---- |
| Document Type | PRD Addendum — Companion to Syllabus PRD v2.0.0 |
| Addendum Version | v2.1.0 |
| Base PRD Version | v2.0.0 (Project 10K Format) |
| Date | March 2026 |
| Sections Modified | 5.2 (Pipeline Architecture), 7 (Agent Boundaries), 8.2 (Evaluation Rubric) |
| Sections Extended | CourseSpec schema (5.4), ContentNode prompting, QANode logic |
| New Sections | A (Prompting Architecture), B (Scaffolding Framework), C (Schema Extensions), D (Layer 2–3 Features), E (Updated Rubric) |
| Implementation Layers | Layer 1: Prompt-level (now) · Layer 2: Schema \+ logic (V2) · Layer 3: Architecture (V3) |

*This addendum does not replace the base PRD. It extends pipeline intelligence while preserving all product scope, billing, personas, infrastructure, and success metrics from v2.0.0.*

# **Table of Contents**

# **Changelog — Base PRD Impact**

This addendum triggers the following changelog entry in the base PRD (Section 0):

v2.0.0 → v2.1.0: Pipeline Enhancement Addendum added as companion document.

  Modifies: Section 5.2 (Pipeline Architecture), Section 7 (Agent Boundaries),

            Section 8.2 (Evaluation Rubric).

  Extends:  CourseSpec schema (Section 5.4) with 4 new fields.

  Adds:     Prompting Architecture (9 principles), Scaffolding Framework

            (6 dimensions), Layer 2–3 feature specs with Gherkin AC.

  Does NOT modify: Sections 1–4, 6, 9–13 (product scope, billing,

            personas, NFRs, infra, metrics, stakeholders unchanged).

## **Current Implementation State (Pre-Addendum)**

| Component | Status | Relevance to Addendum |
| :---- | :---- | :---- |
| V1 MVP (F-001 through F-004) | Complete | All Layer 1 changes are prompt upgrades to these existing, working nodes |
| Pipeline (5 nodes) | Complete | IntentNode, OutlineNode, ContentNode, QANode receive prompt upgrades; ResearchNode unchanged |
| CourseSpec schema | Complete | Extended with 4 new fields (Layer 2); backward compatible |
| Flashcards/Quizzes (F-005) | Schema \+ pipeline only; no UI | Layer 2 schema changes align with V2 UI sprint |
| RAG (Chroma \+ PubMed) | Complete | No changes; ResearchNode unaffected by this addendum |
| V2 features (F-006, F-010) | Not started | Layer 2 ships alongside V2 sprint |
| V3 features (F-007–F-009) | Not started | Layer 3 ships with V3 |

# **Section A: Prompting Architecture**

**\[planning\]  \[code\]  \[test\]**

*These 9 principles govern how every agent in the pipeline is prompted. They are system-level design patterns, not user-facing features. Implementation is pure prompt engineering on existing nodes — zero code architecture change.*

## **P1: Pedagogy in Architecture, Not User Prompts**

| Aspect | Detail |
| :---- | :---- |
| Principle | Embed learning science directly into agent system prompts. The user types “teach me IVF” and never mentions pedagogy — but every agent already operates with prerequisite theory, cognitive load theory, active recall theory, and objective alignment. |
| Applies to | All 5 nodes (system prompts) |
| Current state | Not implemented. Nodes have functional prompts but no embedded pedagogical framework. |
| Implementation | Add the following to every node’s system prompt preamble: “You operate within an educational pipeline governed by: (1) prerequisite ordering — no concept appears before its dependencies are covered, (2) cognitive load management — max one new concept layer per lesson, (3) active recall integration — every lesson must create opportunities for retrieval practice, (4) objective alignment — every piece of content must serve the stated end-state.” |
| Layer | Layer 1 (now) |

## **P2: Persistent Objective Injection**

| Aspect | Detail |
| :---- | :---- |
| Principle | The parsed end-state is re-injected into every agent’s system prompt at every call. No agent can act without the objective as an explicit anchor. |
| Applies to | IntentNode (produces it), OutlineNode, ResearchNode, ContentNode, QANode (all consume it) |
| Current state | IntentNode parses intake into structured fields (journey\_stage, diagnosis, confusion, level). No explicit end-state extraction. |
| Implementation | IntentNode extracts a one-sentence target\_end\_state. Example: “By the end of this course, you will be able to explain your IVF protocol options to your partner and ask informed questions at your next RE consultation.” Store in IntakeData. Inject as the first line of every downstream node’s prompt context: “LEARNER OBJECTIVE: {target\_end\_state}” |
| Schema change | Add target\_end\_state: str to IntakeData (see Section C) |
| Layer | Layer 1 (now) |

**Acceptance Criteria:**

Scenario: Objective persists across all pipeline nodes

  Given a user submits intake with confusion "I don't understand stim protocols"

  When IntentNode processes the intake

  Then IntakeData contains a target\_end\_state field (1 sentence, \< 50 words)

  And every downstream node's prompt context begins with "LEARNER OBJECTIVE: {target\_end\_state}"

  And no lesson in the generated course fails to serve this objective

## **P3: KLI Framework (Knowledge-Learning-Instruction)**

Agents auto-detect knowledge type per lesson and shift instructional method accordingly. Fertility content is mostly conditional knowledge (“when should I ask about progesterone support?”), requiring case-based scenarios and decision-tree framing rather than pure declarative explanation.

| Knowledge Type | What It Is | Instructional Method in Agent Prompt | Fertility Example |
| :---- | :---- | :---- | :---- |
| Declarative | Facts, concepts | Explanation → elaboration → example → recall quiz | "What is AMH?" |
| Procedural | Skills, sequences | Step-by-step → demonstration description → practice scenario | "How do I inject Gonal-F?" |
| Conditional | When/why to apply knowledge | Case-based scenarios → decision-tree framing → reflection prompt | "When is IUI preferred over IVF?" |

| Aspect | Detail |
| :---- | :---- |
| Applies to | ContentNode (primary), OutlineNode (secondary — tags each lesson with knowledge\_type) |
| Implementation | OutlineNode adds knowledge\_type: declarative | procedural | conditional to each lesson in the outline. ContentNode reads knowledge\_type and applies the corresponding instructional method from its system prompt. |
| Schema change | Add knowledge\_type: str to Lesson (see Section C) |
| Layer | Layer 1 (knowledge\_type detection via prompt) \+ Layer 2 (schema field) |

## **P4: Role Isolation (Prevent Role Bleed)**

| Aspect | Detail |
| :---- | :---- |
| Principle | Each agent’s system prompt is scoped to exactly one job. No agent bleeds into another’s domain. This prevents quality collapse from competing prompt constraints. |
| Current state | Already partially implemented — your 5 nodes each have distinct roles. But prompts may contain cross-cutting concerns (e.g., ContentNode making format decisions that should belong to a format step). |
| Implementation | Audit each node’s system prompt. Remove any instructions that belong to another node’s responsibility. Specifically: ContentNode must not decide whether to include a quiz (that’s format selection). QANode must not rewrite content (it only flags). OutlineNode must not write lesson content (it only structures). |
| Layer | Layer 1 (now) |

## **P5: Collaborative Debate (Conquer and Merge)**

| Aspect | Detail |
| :---- | :---- |
| Principle | Multiple agents independently generate their version of a lesson, then a merge agent synthesizes the strongest elements from each. Prevents commitment bias of sequential pipelines. |
| Current state | Not implemented. Single ContentNode per lesson. |
| Implementation (V3) | For fertility content: run two ContentNode instances per lesson — one prompted from a clinical accuracy angle, one from a patient empowerment angle. A MergeNode receives both outputs and synthesizes. Prompt: “Identify where each version excelled and construct a version that captures those specific strengths.” |
| Cost impact | Doubles LLM cost per lesson for ContentNode. Only justified if V2 quality metrics plateau. |
| Trigger to implement | V2 evaluation rubric scores for “tone” and “medical accuracy” diverge (high accuracy but cold tone, or warm tone but shallow accuracy). |
| Layer | Layer 3 (V3 only if metrics justify) |

**Acceptance Criteria:**

Scenario: Collaborative debate produces higher-quality output

  Given a lesson topic "Understanding IVF Stim Protocols"

  When two ContentNode instances generate independently

    (Instance A: clinical accuracy prompt, Instance B: patient empowerment prompt)

  And MergeNode synthesizes both outputs

  Then the merged lesson scores ≥ 4/5 on BOTH medical accuracy AND tone dimensions

  And the merged lesson is not a simple concatenation of A and B

## **P6: Chain-of-Thought Forced Reasoning**

| Aspect | Detail |
| :---- | :---- |
| Principle | Before writing any content, ContentNode must reason through a mandatory scratchpad. The reasoning steps are part of the system prompt, not optional. They constrain what the LLM can generate. |
| Implementation | Add to ContentNode system prompt: “Before writing this lesson, reason through the following steps (include your reasoning in \<thinking\> tags, which will be stripped from output): 1\. What is the learner’s objective for this course? 2\. What does the learner already know at this point in the arc (from prior lessons)? 3\. What is the single concept this lesson must add? 4\. What is the most common misconception about this concept? 5\. What is the minimum vocabulary the learner needs? 6\. Now write the lesson.” |
| Why it matters | An LLM that reasons “the chapter must add the concept of egg retrieval” physically cannot write a chapter that wanders into unrelated fertility history — the chain-of-thought acts as a guardrail. |
| Layer | Layer 1 (now) |

## **P7: Tone Calibration as First-Class Constraint**

Different tone per agent output type. For fertility specifically, content written in cold clinical register produces anxiety, not learning. The tone constraint is the mechanism that makes content feel empathetic.

| Agent / Output Type | Tone Instruction (System Prompt) | Anti-Pattern |
| :---- | :---- | :---- |
| ContentNode (lesson text) | "Write as a warm, knowledgeable friend who has been through IVF and also understands the science. Accessible but intelligent, no jargon without explanation." | Encyclopedia register, clinical coldness |
| ContentNode (exercise blocks) | "A tutor who is checking understanding, not trying to trick the learner. Supportive, not evaluative." | Adversarial quiz tone, gotcha questions |
| Podcast script (V3) | "Two hosts who genuinely find this subject fascinating, reference the prior episode, build on each other’s sentences." | Lecture read-aloud, monotone delivery |
| Compliance notes | "A caring nurse explaining what you can bring up at your next appointment. Empowering, not alarming." | Legal disclaimer tone, fear-inducing |

| Aspect | Detail |
| :---- | :---- |
| Layer | Layer 1 (now) — add tone instructions to existing ContentNode system prompt |

## **P8: Structured Output Contracts**

| Aspect | Detail |
| :---- | :---- |
| Principle | Every agent outputs to a rigid structured schema, not free-form text. When an LLM is instructed to return a JSON schema with specific fields, it cannot hallucinate structure — the format is enforced. |
| Current state | Already implemented via Pydantic CourseSpec. ContentNode outputs to ContentBlock schema. |
| Extension | Add emotional\_sensitivity\_level field to ContentBlock. The format decision logic (Layer 2\) uses this signal: when emotional\_sensitivity\_level is high, generate a reflection prompt instead of a recall quiz. This prevents the failure mode of forcing recall after emotionally loaded content (e.g., a lesson about failed transfers should end with reflection, not a multiple-choice test). |
| Schema change | Add emotional\_sensitivity\_level: str (low | medium | high) to ContentBlock (see Section C) |
| Layer | Layer 2 (V2 sprint) |

## **P9: Parallel Execution with Shared-Only-Arc Context**

| Aspect | Detail |
| :---- | :---- |
| Principle | Lesson agents run in parallel but receive only: (1) global objective anchor, (2) their position in the arc, (3) key concepts from adjacent lessons — NOT full text of other lessons. Prevents cross-lesson phrasing plagiarism and commitment bias. |
| Current state | ContentNode runs parallel per lesson. Needs verification that full text of other lessons is NOT passed as context. |
| Implementation | Audit ContentNode’s LangGraph invocation. Ensure each parallel call receives: target\_end\_state, lesson.title, lesson.objective, lesson.position\_in\_arc (e.g., “Lesson 3 of 6”), and a list of adjacent lesson titles/objectives only. Strip any full lesson text from context. |
| Layer | Layer 1 (now) — context isolation check on existing parallel execution |

## **Principle-to-Node Mapping Summary**

| Principle | IntentNode | OutlineNode | ResearchNode | ContentNode | QANode | Layer |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| P1: Pedagogy in architecture | ✓ | ✓ | ✓ | ✓ | ✓ | 1 |
| P2: Objective injection | Produces | Consumes | Consumes | Consumes | Validates | 1 |
| P3: KLI framework | — | Tags type | — | Applies method | — | 1+2 |
| P4: Role isolation | Audit | Audit | Audit | Audit | Audit | 1 |
| P5: Collaborative debate | — | — | — | Dual instances | Merge node | 3 |
| P6: Forced reasoning | — | — | — | Scratchpad | — | 1 |
| P7: Tone calibration | — | — | — | Tone rules | Tone rules | 1 |
| P8: Structured output | ✓ | ✓ | ✓ | New field | ✓ | 2 |
| P9: Parallel context isolation | — | — | — | Verify | — | 1 |

# **Section B: Scaffolding Framework**

**\[planning\]  \[code\]  \[test\]**

*These 6 dimensions replace the vague “lessons build logically” language in PRD Section 8.2 with testable scaffolding rules. They govern OutlineNode’s arc design and ContentNode’s lesson construction.*

## **D1: Objective-Driven Backward Arc**

| Aspect | Detail |
| :---- | :---- |
| Rule | OutlineNode starts from the target end-state and works backward. Each lesson exists only because it unlocks understanding for the next. Lessons that don’t serve the arc are discarded, even if topically relevant. |
| Applies to | OutlineNode system prompt |
| Prompt addition | "Design the course arc backward from the learner’s objective. The final lesson targets the goal directly. Each prior lesson scaffolds exactly the knowledge needed to understand the next. If a potential lesson does not serve the arc, discard it even if it is topically relevant." |
| Test | For any generated course: remove any one lesson. If the course still makes sense without it, the arc was not tight enough — flag as a scaffolding failure. |

## **D2: Cognitive Load Management**

Three mechanisms, all encoded in OutlineNode and ContentNode system prompts:

| Mechanism | Rule | Prompt Instruction |
| :---- | :---- | :---- |
| Scope compression | Reduce breadth to essential arc, even when user asks for maximal depth | "The learner should feel the arc is achievable. Fewer modules that each land a clear milestone are better than comprehensive coverage. Maximum 4 modules, 3–5 lessons per module." |
| Chapter pacing | Each lesson introduces exactly one new concept layer | "Each lesson adds exactly ONE new layer of understanding. Concepts from prior lessons may be reactivated (not re-taught) to build on existing mental models." |
| Milestone insertion | Quizzes/checkpoints at moments of maximum cognitive accumulation, not fixed intervals | "Insert a quiz or reflection checkpoint when the learner has absorbed enough new material to need consolidation before moving forward. This is contextual, not every-N-lessons." |

*Fertility-specific: Anxiety actively suppresses working memory capacity. Scope compression must be more aggressive than neutral-topic courses. An overwhelmed patient learns nothing.*

## **D3: Zone of Proximal Development (ZPD) Alignment**

| ZPD Type | When Applied | Mechanism |
| :---- | :---- | :---- |
| Static ZPD | Course generation time | User’s stated level (beginner / intermediate / advanced) calibrates vocabulary complexity, assumed prior knowledge, and density of prerequisite explanations. A beginner course doesn’t assume you know what FSH is — it explains before using. |
| Dynamic ZPD | V2+ (quiz performance feedback) | Quiz results signal where the learner’s ZPD currently sits. V3 adaptive learning modulates subsequent lesson depth based on performance. For V2: quiz scores stored; adjustment is manual (next course generation considers prior scores). |

## **D4: Knowledge Topology Detection**

OutlineNode auto-detects content topology from the intake and applies the corresponding scaffold structure. Fertility content sits in the clinical/healthcare topology.

| Topology | Natural Structure | Scaffold Strategy | When Detected |
| :---- | :---- | :---- | :---- |
| Procedural | Sequential steps | Linear arc, numbered progressions, milestones after each step | "How to inject Gonal-F", medication protocols |
| Conceptual/Scientific | Hierarchical prerequisite tree | Bottom-up from foundations, definitions before application | "What is AMH?", hormone cycle education |
| Clinical/Healthcare | Decision-tree \+ procedural hybrid | Symptom → diagnosis → treatment arcs, patient narratives, guideline citations | Most fertility content (IVF, IUI, PCOS management) |
| Emotional/Processing | Non-linear, narrative-driven | Thematic arcs, reflection-heavy, minimal quizzes, validation-first | Failed cycles, grief processing, decision fatigue |

| Aspect | Detail |
| :---- | :---- |
| Implementation | OutlineNode system prompt: "Detect the primary knowledge topology of this course: procedural, conceptual, clinical/healthcare, or emotional/processing. Tag each lesson with its topology. Apply the corresponding scaffold strategy." |
| Layer | Layer 1 (prompt-level detection) \+ Layer 2 (schema field on Lesson) |

## **D5: Piecemeal and Achievable Constraint**

At every point in the course, the learner must feel: “I just understood something,” “The next step feels within reach,” and “I am making visible progress.”

* Key Takeaways at TOP of each lesson (not bottom) — primes recall and reduces anxiety before the learner reads the full content

* Progressive disclosure within each lesson: broad concept first → nuance → edge cases. Never drop the learner into the middle of complexity.

* Every lesson ends with a clear “Now you understand X” moment — never “There’s still so much more to cover”

* Visual arc indicators: learner always sees their position in the full course (already implemented in course sidebar)

| Aspect | Detail |
| :---- | :---- |
| Schema change | Add key\_takeaways: List\[str\] (3–5 items) to Lesson (see Section C) |
| Frontend change | Render key\_takeaways as a card above lesson content, visually distinct from body text |
| Layer | Layer 2 (V2 sprint) |

## **D6: Active/Passive Modality Switching**

The pipeline determines when to switch between passive consumption (reading) and active engagement (quiz, flashcard, reflection) based on content context, not fixed intervals.

| After This Content Type | Insert This Active Element | Rationale |
| :---- | :---- | :---- |
| Dense conceptual material | Quiz (recall questions) | Consolidate before new concepts are introduced |
| Procedural sequences | Flashcards (step anchoring) | Anchor steps in long-term memory |
| Emotional/narrative content | Reflection prompt (NOT quiz) | Forced recall after emotionally loaded content backfires; reflection is safer |
| Major arc section boundary | Summary \+ podcast episode (V3) | Auditory re-explanation reinforces in a different cognitive register |

| Aspect | Detail |
| :---- | :---- |
| Implementation (V2) | Embed format decision logic inside ContentNode: before writing blocks, determine active element placement based on knowledge\_type and emotional\_sensitivity\_level. Not a separate agent yet. |
| Implementation (V3) | If V2 results are inconsistent, break into standalone Format Selection Agent between OutlineNode and ContentNode. |

# **Section C: Schema Extensions**

**\[code\]  \[test\]**

Four new fields extend the existing CourseSpec Pydantic schema. All are backward-compatible (optional with defaults).

| Field | Added To | Type | Default | Produced By | Consumed By | Layer |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| target\_end\_state | IntakeData | str | "" (empty → IntentNode generates) | IntentNode | All downstream nodes \+ QANode validation | 1 (now) |
| key\_takeaways | Lesson | List\[str\] | \[\] (empty list) | ContentNode | Frontend (card above lesson content) | 2 (V2) |
| knowledge\_type | Lesson | str (declarative | procedural | conditional) | "declarative" | OutlineNode | ContentNode (instructional method selection) | 2 (V2) |
| emotional\_sensitivity\_level | ContentBlock | str (low | medium | high) | "low" | ContentNode | Format logic (quiz vs reflection decision) | 2 (V2) |

## **Schema Diff (Pydantic)**

\# IntakeData — ADD:

target\_end\_state: str \= ""  \# Extracted by IntentNode; injected into all nodes

\# Lesson — ADD:

key\_takeaways: List\[str\] \= \[\]  \# 3–5 items; rendered at top of lesson

knowledge\_type: str \= "declarative"  \# declarative | procedural | conditional

\# ContentBlock — ADD:

emotional\_sensitivity\_level: str \= "low"  \# low | medium | high

*All fields have defaults. Existing courses (generated pre-addendum) remain valid. Migration: no action required.*

# **Section D: Layer 2 & 3 Feature Specs**

**\[planning\]  \[design\]  \[code\]  \[test\]**

## **F-011: Format Selection Logic (V2 — Embedded in ContentNode)**

| Aspect | Detail |
| :---- | :---- |
| Linked Stories | US-005 (flashcards/quizzes) |
| Linked Principles | P3 (KLI), P8 (structured output), D4 (topology detection), D6 (modality switching) |
| Description | Before writing content blocks, ContentNode runs a format decision pass: based on knowledge\_type and emotional\_sensitivity\_level, it determines which block types this lesson warrants. Replaces the current “every lesson gets the same block mix” behavior. |
| Priority | Should Have (V2) |
| Complexity | M |

**Acceptance Criteria:**

Scenario: Declarative lesson gets explanation \+ quiz

  Given a lesson with knowledge\_type \= "declarative"

  And emotional\_sensitivity\_level \= "low"

  When ContentNode generates content blocks

  Then the lesson contains at least: explanation, example, exercise blocks

  And a quiz is generated for this lesson

Scenario: Emotional content gets reflection instead of quiz

  Given a lesson about failed IVF transfers

  And emotional\_sensitivity\_level \= "high"

  When ContentNode generates content blocks

  Then the lesson contains a reflection block instead of an exercise block

  And no quiz is generated for this lesson

  And the lesson ends with a supportive "Now you understand X" framing

## **F-012: Key Takeaways Rendering (V2)**

| Aspect | Detail |
| :---- | :---- |
| Linked Principles | D5 (piecemeal and achievable) |
| Description | Each lesson displays 3–5 key takeaways as a visually distinct card at the TOP of the lesson content, before the body text. Primes recall and reduces anxiety. |
| Priority | Should Have (V2) |
| Complexity | S |

**Acceptance Criteria:**

Scenario: Key takeaways displayed at top of lesson

  Given a lesson with key\_takeaways \= \["AMH measures ovarian reserve", ...\]

  When the lesson page renders

  Then a takeaways card appears ABOVE the first content block

  And it contains 3–5 bullet points

  And it is visually distinct from lesson body text (card style, different background)

## **F-013: Collaborative Debate / MergeNode (V3 — Conditional)**

| Aspect | Detail |
| :---- | :---- |
| Linked Principles | P5 (Conquer and Merge) |
| Description | Two independent ContentNode instances per lesson: one prompted for clinical accuracy, one for patient empowerment. A new MergeNode synthesizes the strongest elements from both. |
| Trigger to build | V2 evaluation rubric scores for “tone” and “medical accuracy” diverge — high accuracy but cold tone, or warm tone but shallow accuracy. |
| Priority | Could Have (V3, conditional on metrics) |
| Complexity | L |
| Cost impact | Doubles ContentNode LLM cost (\~$0.60–$1.20 per course instead of $0.30–$0.60) |
| Pipeline change | New MergeNode added after parallel ContentNode execution, before QANode |

## **F-014: Patient Narrative Agent (V3)**

| Aspect | Detail |
| :---- | :---- |
| Description | Dedicated agent that generates relatable patient stories for emotional anchoring. Example: A lesson about egg retrieval opens with “Sarah, 34, was terrified the night before her retrieval...” Creates empathy that pure clinical explanation cannot. |
| Priority | Could Have (V3) |
| Complexity | M |
| Schema impact | New ContentBlock type: "patient\_narrative" added to block type enum |
| Pipeline change | New node that runs parallel to ContentNode; output injected at lesson start |

**Acceptance Criteria:**

Scenario: Patient narrative anchors emotional content

  Given a lesson with emotional\_sensitivity\_level \= "high"

  When PatientNarrativeAgent generates a story

  Then the story is 2–4 sentences featuring a named persona

  And the persona’s situation matches the lesson’s clinical context

  And the story appears as the first block in the lesson

  And the story never contains prescriptive medical advice

## **F-015: Iterative Refinement Loop (V3)**

| Aspect | Detail |
| :---- | :---- |
| Description | QANode feeds corrections back into ContentNode before the user sees output. Current: QA flags and the course ships or fails. New: QA flag → send flagged lesson back to ContentNode with correction instruction → ContentNode regenerates just that lesson → QA re-validates. |
| Priority | Could Have (V3) |
| Complexity | M |
| Latency impact | \+10–15 seconds per flagged lesson |
| Benefit | Zero compliance violations reach the user (vs current: violations are flagged but may still ship if the flag is a false negative) |

**Acceptance Criteria:**

Scenario: QA refinement loop catches and fixes violation

  Given ContentNode produces a lesson containing "you should take 150mg"

  When QANode flags the prescriptive language

  Then QANode sends the lesson back to ContentNode with correction instruction

  And ContentNode regenerates only the flagged lesson

  And QANode re-validates the regenerated lesson

  And the final output contains zero prescriptive statements

  And total generation time increases by \< 20 seconds

# **Section E: Updated Evaluation Rubric**

**\[test\]**

Replaces PRD Section 8.2. The original 5 dimensions are preserved. 4 new dimensions are added based on the scaffolding framework and prompting architecture.

## **E.1 Full 9-Dimension Rubric**

| \# | Dimension | Pass Criteria | Fail Criteria | Source |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Medical accuracy | Facts correct; no prescriptive advice | Any factual error or prescriptive statement | Original PRD |
| 2 | Structural coherence | Lessons build logically; no gaps | Random ordering or missing prerequisite concepts | Original PRD |
| 3 | Tone | Empathetic, warm, accessible | Clinical, cold, or condescending | Original PRD |
| 4 | Compliance | Every lesson has compliance\_note block | Any lesson missing compliance\_note | Original PRD |
| 5 | Completeness | Quizzes and flashcards present where warranted | Missing quiz or flashcards in appropriate lessons | Original PRD (modified) |
| 6 | Objective coherence | Every lesson serves the target\_end\_state | Any lesson that could be removed without affecting the arc | Addendum (P2, D1) |
| 7 | Scaffolding quality | Backward arc design; scope compression; one-concept-per-lesson pacing | Arc starts from topic beginning (not end-state); \> 1 new concept per lesson; \> 4 modules | Addendum (D1, D2) |
| 8 | Knowledge topology fit | Instructional method matches content type (declarative → quiz, procedural → practice, conditional → decision-tree, emotional → reflection) | Same block mix regardless of content type; quiz after emotionally loaded content | Addendum (P3, D4, D6) |
| 9 | Emotional calibration | Reflection prompts (not quizzes) after emotionally loaded content; supportive closure; patient-first framing | Quiz after failed cycle content; clinical register in emotional context; “there’s still so much more” endings | Addendum (P7, P8, D5) |

## **E.2 Updated Success Criteria**

| Metric | Pre-Addendum (PRD v2.0) | Post-Addendum (v2.1) | Kill Threshold |
| :---- | :---- | :---- | :---- |
| Test courses passing rubric | 8/10 pass all 5 dimensions | 8/10 pass all 9 dimensions | \< 6/10 on any dimension |
| Objective coherence score | Not measured | ≥ 8/10 courses: every lesson serves end-state | \< 6/10 |
| Knowledge type accuracy | Not measured | ≥ 7/10 lessons correctly tagged by OutlineNode | \< 5/10 |
| Emotional calibration | Not measured | 0 quizzes after emotional\_sensitivity\_level \= high content | Any quiz after high-sensitivity content |

## **E.3 A/B Testing Protocol (Layer 1 Prompt Upgrades)**

Before and after implementing Layer 1 prompt changes, run the existing 10 test prompts (PRD Section 8.3) through both the current pipeline and the upgraded pipeline. Score both sets on the full 9-dimension rubric.

* Baseline: Score all 10 prompts on current pipeline (5-dimension rubric, extended to 9\)

* Treatment: Score all 10 prompts on Layer 1 upgraded pipeline (9-dimension rubric)

* Success: Treatment scores ≥ baseline on original 5 dimensions AND ≥ 7/10 on new 4 dimensions

* Rollback trigger: Treatment scores \< baseline on any original dimension

* Timeline: 2–3 days for implementation \+ evaluation

# **Implementation Sequencing**

**\[planning\]  \[orchestrate\]**

| Layer | When | What | Effort | Risk | Dependencies |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Layer 1 | This week | Prompt upgrades: P1, P2, P4, P6, P7, P9 on all 5 existing nodes. P3 (knowledge type detection via prompt only, no schema field yet). Add target\_end\_state to IntakeData. | 2–3 days | Zero — pure prompt engineering, fully reversible | None |
| Layer 1 eval | Immediately after | Run 10 test prompts before/after. Score on 9-dimension rubric. Validate Layer 1 improves output. | 1 day | None | Layer 1 complete |
| Layer 2 | V2 sprint | Schema: key\_takeaways, knowledge\_type, emotional\_sensitivity\_level. Format selection logic in ContentNode. Key takeaways rendering in frontend. P8 (emotional\_sensitivity field). | 1–2 weeks | Low — additive, backward-compatible | V2 sprint start (alongside F-005, F-010) |
| Layer 3 | V3 (conditional) | P5 (Collaborative Debate \+ MergeNode). F-014 (Patient Narrative Agent). F-015 (Iterative Refinement Loop). Separate Format Selection Agent if V2 results inconsistent. | 4–6 weeks | Medium — pipeline restructuring, doubles LLM cost for debate | V2 shipped \+ quality metrics baseline |

*Do not start Layer 3 until V2 is shipping revenue and you have quality baselines to measure against. The trigger for Layer 3 is metric plateau, not ambition.*

**End of PRD Addendum v2.1.0**  
Companion to Syllabus PRD v2.0.0 (Project 10K Format)

*9 prompting principles · 6 scaffolding dimensions · 4 schema extensions · 5 new feature specs · 9-dimension evaluation rubric*

## F-016: Progressive Course Delivery (V1.1)

**Linked Stories:** US-002 (real-time generation stream)
**Linked Principles:** P9 (parallel execution), D5 (piecemeal and achievable)
**Modifies:** PRD Section 5.3 (API Contracts), F-002 (Real-Time Generation Stream)
**Priority:** Must Have (V1.1 — ships before V2)
**Complexity:** M
**Effort:** ~1 week (2–3 days backend, 2–3 days frontend)
**Tags:** `[code]` `[test]` `[design]`

---

### Description

Replace the current "wait for full generation, then redirect to course page" flow with progressive lesson-by-lesson delivery. The user lands on the course page immediately after intake submission. The outline renders as a skeleton, and lessons fill in one at a time as each completes pipeline processing (ContentNode + per-lesson QANode). The user can read lesson 1 while lesson 4 is still generating.

---

### What Changes

| Component | Current Behavior | New Behavior |
|-----------|-----------------|--------------|
| SSE stream | Emits status messages ("Writing Lesson 2 of 6…"), redirects to `/course/{id}` on complete | Emits `outline_ready` with skeleton, then `lesson_ready` per lesson with full JSON, then `generation_complete` |
| Frontend generation page | Dedicated `/generate/{jobId}` page with progress bar → redirect | Course page IS the generation page. `/course/{id}` renders immediately with skeleton, fills progressively |
| QANode | Runs once on full CourseSpec after all ContentNodes complete | Runs per-lesson as each ContentNode completes. Lesson is not emitted until it passes QA |
| Database writes | Single JSONB write of full CourseSpec on completion | Outline written first (course record with module/lesson titles, empty content). Each lesson upserted as it completes |
| User experience | Stare at progress screen for 60–75 seconds | Start reading lesson 1 within ~15–20 seconds. Remaining lessons appear while reading |

---

### SSE Event Schema

```
# Phase 1: Skeleton (within ~10 seconds of intake)
{ event: "outline_ready", course_id: "abc", modules: [
    { title: "Understanding Your Diagnosis", lessons: [
        { title: "What PCOS Actually Means", status: "generating" },
        { title: "Your Hormone Panel Explained", status: "queued" }
    ]},
    ...
]}

# Phase 2: Lessons arrive (each within ~10-15 seconds of each other)
{ event: "lesson_ready", course_id: "abc", module_index: 0, lesson_index: 0,
  lesson: { ...full Lesson JSON with blocks, compliance_note, key_takeaways... } }

{ event: "lesson_ready", course_id: "abc", module_index: 0, lesson_index: 1,
  lesson: { ...full Lesson JSON... } }

# Phase 3: Done
{ event: "generation_complete", course_id: "abc", total_lessons: 6,
  generation_time_ms: 68000 }
```

---

### Acceptance Criteria

```gherkin
Scenario: User lands on course page immediately after intake
  Given a user has submitted a valid intake
  When the pipeline begins processing
  Then the user is routed to /course/{id} (not /generate/{jobId})
  And the course page renders within 3 seconds of intake submission
  And the sidebar shows module and lesson titles in a skeleton/greyed state
  And no redirect occurs during or after generation

Scenario: First lesson appears while pipeline is still running
  Given the pipeline has completed OutlineNode and ContentNode for lesson 1
  And ContentNode for lessons 2-6 is still running
  When QANode validates lesson 1
  Then a lesson_ready event is emitted with full lesson JSON
  And the course page renders lesson 1 with all content blocks
  And the user can scroll and read lesson 1
  And lessons 2-6 show skeleton loaders in the sidebar

Scenario: Lessons fill in progressively
  Given lesson 1 is rendered and the user is reading it
  When ContentNode completes lesson 2 and QANode validates it
  Then a lesson_ready event is emitted for lesson 2
  And the sidebar updates lesson 2 from skeleton to active state
  And the user's reading position on lesson 1 is not disrupted
  And no page reload or scroll jump occurs

Scenario: QA validation runs per-lesson before emission
  Given ContentNode produces lesson 3 with prescriptive language
  When QANode evaluates lesson 3
  Then lesson 3 is NOT emitted via SSE
  And lesson 3 is flagged and regenerated (or held for refinement loop in V3)
  And the user sees lessons 1, 2, 4 without noticing a gap
  And lesson 3 appears when a clean version passes QA

Scenario: Database writes are incremental
  Given the outline is ready
  Then a course record is created in Postgres with module/lesson titles and empty content
  And as each lesson_ready event fires, the lesson content is upserted into the course JSONB
  And if the pipeline crashes after lesson 3 of 6, lessons 1-3 are persisted and accessible
  And the course shows a "Generation incomplete — 3 of 6 lessons available" state

Scenario: Generation complete
  Given all lessons have been emitted via SSE
  When the generation_complete event fires
  Then all sidebar skeleton states are removed
  And the progress indicator disappears
  And the course is fully interactive (mark complete, feedback, resume all work)
  And total generation time is logged to the event tracking plan (Section 9.2)

Scenario: User marks lesson 1 complete while lesson 4 is generating
  Given lesson 1 is rendered and the user clicks "Mark complete"
  And lessons 4-6 are still generating
  When the completion API is called
  Then lesson 1 is marked complete in UserCourseState
  And the progress bar updates (e.g., "1 of 6 complete")
  And generation continues uninterrupted

Scenario: Returning to a partially generated course
  Given a user closes the browser while lesson 3 of 6 is generating
  When they return to /course/{id}
  Then lessons 1-2 are rendered (fully persisted)
  And lesson 3+ show either skeleton loaders (if generation resumed) or
    "Generation incomplete" state (if generation timed out)
  And the user can read and interact with completed lessons
```

---

### Edge Cases

| Condition | Expected Behavior | User Message | Severity |
|-----------|-------------------|--------------|----------|
| Pipeline crashes mid-generation | Persist completed lessons; show partial course with clear indicator | "We generated 3 of 6 lessons. You can read what's ready, or regenerate the remaining lessons." | High |
| All lessons fail QA on first pass | Hold emission; retry each. If retry fails, emit with QA warning flag | "This lesson is being reviewed for accuracy. Check back shortly." | Critical |
| User has slow connection / SSE drops | Frontend polls `GET /v1/course/{id}` as fallback; renders whatever lessons are persisted | Seamless — no user-visible error | Medium |
| Lesson arrives out of order (lesson 3 before lesson 2) | Frontend renders lesson 3 in correct position; lesson 2 slot stays in skeleton | No user message needed — sidebar ordering is stable | Low |

---

### What Stays the Same

- Intake flow (F-001) — unchanged
- Pipeline node sequence (Intent → Outline → Research → Content × N → QA) — unchanged, just QA runs per-lesson
- CourseSpec schema — unchanged (lessons are the same structure)
- Auth, dashboard, feedback — unchanged
- `GET /v1/course/{id}` — still returns full CourseSpec (with whatever lessons are available)
- `POST /v1/generate` — still returns `{ job_id, status: "queued" }`, but now also returns `course_id` immediately