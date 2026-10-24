---
id: 001
title: Ratify HCM Lite Agentic AI Constitution
stage: constitution
date: 2026-10-25
surface: agent
model: claude-opus-5-5
feature: none
branch: master
user: Abdullah-18-Ahmed
command: /sp.constitution
labels: ["constitution", "governance", "rag", "openai-agents-sdk", "chainlit", "security"]
links:
  spec: null
  ticket: null
  adr: null
  pr: null
files:
 - .specify/memory/constitution.md
 - .specify/templates/plan-template.md
 - .specify/templates/tasks-template.md
 - history/prompts/constitution/001-ratify-hcm-lite-constitution.constitution.prompt.md
tests:
 - none (governance document; no code)
---

## Prompt

/sp.constitution

Note: the user's argument contained the complete constitution text below repeated three times
back-to-back with identical content; one full copy is recorded here.

# HCM Lite Agentic AI — Project Constitution

**Version:** 1.1.0  
**Project:** HCM Lite — AI-Powered Human Capital Management  
**Module:** M8 — Agentic AI  
**Development Methodology:** Spec-Driven Development (SDD)

## Article I: Mission and Objectives

Build a fully functional, runnable, and demonstrable Agentic AI application for the HCM Lite Hackathon.

The application must provide an AI-powered HR assistant capable of understanding natural-language requests, selecting appropriate tools, retrieving HR information through Retrieval-Augmented Generation (RAG), summarizing HR metrics, answering HR policy questions, and preparing leave requests for user review.

The application must use:

- Python for backend development.
- OpenAI API for language-model access.
- OpenAI Agents SDK for agent orchestration and tool execution.
- Chainlit for the interactive chat interface.
- Retrieval-Augmented Generation (RAG) for retrieving relevant information from the configured HR data sources.
- Pydantic for data validation and structured schemas.
- pytest for automated testing.

**The primary objective is to deliver a working end-to-end application, not merely code examples, mockups, or disconnected modules.**

The system MUST use RAG as its primary information-retrieval mechanism instead of relying on a locally hardcoded employee database. It must retrieve information from an explicitly configured document repository, vector store, or connected HR data source.

RAG MUST NOT be treated as a replacement for authorization, data validation, or transactional business logic.

## Article II: Mandatory Technology Stack

The following technologies are mandatory:

1. **Python:** Use a compatible, documented Python version.
2. **OpenAI API:** Use the official API for LLM interactions and supported embedding models.
3. **OpenAI Agents SDK:** Use the official Python package `openai-agents`.
4. **Chainlit:** Use Chainlit as the primary user interface.
5. **RAG:** Implement document ingestion, chunking, embedding generation, vector retrieval, and grounded answer generation.
6. **Vector store:** Use a supported vector database or vector-store service, such as Qdrant, Chroma, or another documented compatible option. Choose one implementation and configure it consistently.
7. **Embeddings:** Use an embedding model supported by the OpenAI API.
8. **Pydantic:** Validate tool inputs, structured outputs, and configuration.
9. **Environment configuration:** Use environment variables and `python-dotenv` for local development.
10. **Testing:** Use pytest for automated testing.

Use the Agents SDK's `Agent`, `Runner`, function tools, and guardrails as appropriate.

Do not replace the required OpenAI Agents SDK or Chainlit stack with another agent or UI framework without explicit approval.

Official documentation:

- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- OpenAI API: https://developers.openai.com/api/docs/
- Chainlit: https://docs.chainlit.io/
- Qdrant: https://qdrant.tech/documentation/
- Chroma: https://docs.trychroma.com/

## Article III: Spec-Driven Development Principles

Every feature MUST follow the specification-first development process.

1. **Specify:** Define the feature, user story, inputs, outputs, business rules, security constraints, dependencies, and acceptance criteria.
2. **Design:** Define modules, retrieval interfaces, data contracts, tools, and integration points.
3. **Implement:** Write the smallest complete implementation that satisfies the specification.
4. **Test:** Execute automated tests and validate error handling.
5. **Demonstrate:** Verify the feature through Chainlit or a documented integration test.
6. **Document:** Update the README and specification with setup instructions, behavior, and limitations.

All specifications MUST be maintained in a version-controlled `specs/` directory.

Recommended specification files:

- `specs/001-agent-chat.md`
- `specs/002-rag-pipeline.md`
- `specs/003-hr-retrieval-tools.md`
- `specs/004-smart-leave.md`
- `specs/005-dashboard-summary.md`
- `specs/006-policy-assistant.md`
- `specs/007-security-and-testing.md`

A feature is not complete until its acceptance criteria pass.

Never silently invent business rules or data sources. Document assumptions or ask for clarification when requirements are ambiguous.

## Article IV: RAG Architecture and Requirements

RAG MUST be a core component of the application.

The application must retrieve relevant information from a configured HR information source before generating factual answers that depend on that information.

### 4.1 RAG pipeline

Implement the following pipeline:

1. **Data ingestion:** Load authorized HR documents or records from the configured source.
2. **Preprocessing:** Normalize text and extract relevant metadata.
3. **Chunking:** Divide supported documents into meaningful, retrievable sections.
4. **Embedding generation:** Generate vector embeddings using a configured embedding model.
5. **Indexing:** Store embeddings, text chunks, and metadata in the configured vector store.
6. **Query processing:** Accept a user's natural-language question and prepare a retrieval query.
7. **Retrieval:** Search the vector store for relevant chunks using semantic similarity and appropriate metadata filters.
8. **Context preparation:** Select relevant retrieved content and include source metadata.
9. **Grounded generation:** Supply retrieved context to the agent or answer-generation component.
10. **Response validation:** Ensure that the response does not present unsupported information as fact.
11. **Citation:** Provide source references for document-grounded answers when available.

The pipeline must be modular, testable, and documented.

### 4.2 Required RAG components

The implementation MUST provide:

- A document loader or ingestion interface.
- Text cleaning and chunking.
- An embedding-generation component.
- A vector-store integration.
- A retrieval service.
- Metadata filtering.
- A grounded answer-generation workflow.
- Source tracking and citation metadata.
- Error handling for missing, malformed, or inaccessible documents.
- Tests for retrieval quality and source-grounded responses.

### 4.3 No hardcoded HR database

The application MUST NOT depend on a locally hardcoded employee database as its primary source of HR facts.

Do not create fake employee records and present them as real organizational information.

The retrieval system must use a configured source, such as:

- Authorized HR documents.
- Imported HR files and structured exports.
- An existing HR backend.
- A configured external database or service connected through an approved retrieval adapter.

For a standalone demonstration, provide a small, clearly labeled demo document collection that is ingested into the RAG pipeline. This collection is test content, not a replacement for a real organizational data source.

The application MUST visibly identify demo mode.

### 4.4 Structured data versus semantic retrieval

RAG is required for retrieving relevant HR documents and contextual information. However, semantic similarity alone MUST NOT be used to calculate exact numeric metrics or guarantee the completeness of structured records.

For questions requiring exact employee counts, payroll totals, attendance percentages, or leave balances:

- Use an authorized structured-data retrieval adapter, query service, or verified API where available.
- Use RAG to retrieve contextual information, explanations, and related policies when useful.
- Validate and calculate numeric results using trusted application code.
- Clearly report when the configured source cannot provide an exact answer.

The architecture MUST support both document retrieval and structured HR data retrieval without introducing a hardcoded local employee database.

## Article V: HR Assistant Functionalities

### 5.1 Interactive HR assistant

The application MUST:

- Accept natural-language messages through Chainlit.
- Generate responses using the configured OpenAI model.
- Maintain conversational context within the active session.
- Retrieve relevant information from the RAG system when required.
- Ask clarifying questions when essential information is missing.
- Provide processing feedback for longer operations.
- Handle unavailable information and service failures gracefully.
- Never fabricate HR facts.

### 5.2 HR retrieval tools

Implement the following seven tools using the OpenAI Agents SDK.

**Tool 1: `get_headcount`**

Retrieve total employee counts and department breakdowns from an authorized structured HR data source. Use verified structured queries or APIs for exact counts.

**Tool 2: `get_attendance_summary`**

Retrieve attendance statistics for a specified period using an authorized structured source.

**Tool 3: `get_late_comers`**

Retrieve authorized late-attendance records for a specified date or period.

**Tool 4: `get_leave_summary`**

Retrieve leave statistics, including relevant counts and statuses.

**Tool 5: `get_my_leave_balance`**

Retrieve the authenticated user's leave balance through a trusted HR service or authorized structured data source.

**Tool 6: `get_payroll_summary`**

Retrieve authorized aggregate payroll statistics through a trusted structured data source.

**Tool 7: `search_employees`**

Search authorized employee records using supported filters. Use structured retrieval for exact matches and RAG when semantic search across authorized employee profiles is appropriate.

Each tool MUST have:

- A clear name and description.
- Validated input parameters.
- Predictable output schemas.
- Appropriate authorization checks.
- Safe error handling.
- Unit tests.
- A documented data source and retrieval strategy.

The LLM MUST use tools to retrieve factual HR data instead of inventing answers from pretrained knowledge.

Tools MUST NOT treat semantically similar retrieved text as proof that a numeric value or employee record is complete or correct.

## Article VI: Agent Architecture

Use a modular architecture that separates the UI, agent orchestration, retrieval pipeline, tools, business services, and data access.

Recommended project structure:

    hcm-lite-agent/
    ├── app.py
    ├── agents/
    │   ├── hr_agent.py
    │   ├── instructions.py
    │   └── guardrails.py
    ├── tools/
    │   ├── employee_tools.py
    │   ├── attendance_tools.py
    │   ├── leave_tools.py
    │   └── payroll_tools.py
    ├── rag/
    │   ├── ingestion.py
    │   ├── chunking.py
    │   ├── embeddings.py
    │   ├── vector_store.py
    │   ├── retriever.py
    │   ├── reranker.py
    │   └── citations.py
    ├── services/
    │   ├── data_provider.py
    │   ├── summary_service.py
    │   ├── smart_leave_service.py
    │   └── policy_service.py
    ├── models/
    │   ├── requests.py
    │   └── responses.py
    ├── data/
    │   ├── documents/
    │   └── policies/
    ├── specs/
    ├── tests/
    ├── .env.example
    ├── .gitignore
    ├── requirements.txt
    ├── README.md
    └── CONSTITUTION.md

This structure may be adjusted when justified by implementation needs, but the separation of responsibilities MUST be preserved.

Chainlit MUST NOT contain the entire application business logic.

The agent MUST access data only through approved retrieval services, registered tools, and authorized business services.

## Article VII: RAG Source Management and Indexing

All data sources MUST be explicitly configured and documented.

### 7.1 Document ingestion

The ingestion process MUST:

- Support the document formats required by the project.
- Validate files before processing.
- Reject unsupported or malformed documents safely.
- Extract text and useful metadata.
- Split text into meaningful chunks.
- Generate embeddings.
- Store chunks and metadata in the configured vector store.
- Avoid accidental duplicate ingestion.
- Record document identifiers and ingestion status.
- Support re-indexing when documents change.

The system MUST distinguish source content from system instructions. Retrieved document text MUST never be executed as code or treated as trusted agent instructions.

### 7.2 Metadata

Where applicable, each indexed chunk SHOULD retain:

- Document identifier.
- Document title.
- Source location or path.
- Chunk identifier.
- Page or section number.
- Document type.
- Department or access scope.
- Last-updated timestamp.
- Version information.

Metadata MUST be used to support source citations, filtering, traceability, and authorized retrieval.

### 7.3 Retrieval behavior

The retrieval service SHOULD support configurable:

- Top-k results.
- Similarity thresholds.
- Metadata filters.
- Chunk size and overlap.
- Embedding model.
- Vector-store connection settings.

Use reranking only when it provides measurable benefit and is justified by the specification.

If retrieval returns no sufficiently relevant information, the assistant MUST state that the configured sources do not provide a reliable answer.

The assistant MUST NOT fill missing context with invented HR policies or records.

### 7.4 Index lifecycle

The system MUST document how to:

- Configure the vector store.
- Ingest source documents.
- Build or rebuild the index.
- Update changed documents.
- Inspect ingestion errors.
- Clear or recreate a development index safely.

The ingestion process MUST be reproducible.

## Article VIII: Smart Leave Assistant

The agent MUST interpret natural-language leave requests and prepare structured drafts containing:

- Leave type.
- Start date.
- End date.
- Reason.
- Missing information requiring clarification.

The assistant MUST:

1. Extract the requested details.
2. Ask follow-up questions when required information is missing.
3. Validate date formats, ranges, and applicable rules.
4. Retrieve relevant leave policies through RAG when appropriate.
5. Display a readable leave summary.
6. Allow the user to review the draft.

The initial implementation MUST NOT automatically submit, approve, or reject official leave requests.

Any future submission functionality MUST require explicit user confirmation, authorization, and server-side validation through the normal HCM workflow.

RAG-retrieved policy text may inform the draft but MUST NOT replace authoritative validation of leave balances, eligibility, or submission rules.

## Article IX: Dashboard Summaries

The agent MUST summarize available HR dashboard metrics into concise, useful observations.

- Retrieve exact metrics through authorized structured queries or APIs.
- Use RAG to retrieve contextual information or policy explanations where relevant.
- Calculate statistics using trusted application code.
- Never invent employee counts, attendance rates, payroll totals, or trends.
- Clearly state when data is unavailable or incomplete.
- Include source information when appropriate.

The LLM may explain verified metrics but MUST NOT independently fabricate numerical results.

## Article X: HR Policy Assistant

The agent MUST use RAG as the primary retrieval method for answering questions about configured HR policies.

The policy workflow MUST:

1. Receive the user's question.
2. Retrieve relevant policy chunks.
3. Filter results according to the user's authorization.
4. Provide retrieved context to the answer-generation component.
5. Generate an answer grounded in the retrieved content.
6. Include policy source references where available.
7. Acknowledge uncertainty or missing information.

If no suitable policy content is found, the agent MUST say that the answer could not be verified from the available sources.

It MUST NOT invent policy rules or claim that a policy exists when the indexed content does not support the claim.

## Article XI: OpenAI API and Agents SDK Requirements

- Use the official OpenAI Agents SDK for Python.
- Read `OPENAI_API_KEY` from the environment.
- Read `OPENAI_MODEL` from the environment.
- Read `OPENAI_EMBEDDING_MODEL` from the environment.
- Never hardcode secrets.
- Verify model availability and configuration.
- Use documented SDK interfaces.
- Register HR operations as explicit tools.
- Use typed schemas and validation.
- Configure reasonable timeouts and execution limits.
- Handle API errors and rate limits.
- Avoid infinite retries and unbounded agent execution.
- Keep agent orchestration independent of Chainlit.
- Keep the embedding and retrieval layers independent of the UI.
- Use the configured vector store instead of silently substituting a local employee database.

The system MUST distinguish retrieval failures, model failures, and business-service failures in its internal error handling.

## Article XII: Security and Privacy

Security MUST be enforced in the application, retrieval layer, and tools.

Mandatory requirements:

- Store secrets in environment variables.
- Exclude `.env` and sensitive files from Git.
- Enforce authorization before retrieving or returning sensitive information.
- Apply document-level and metadata-level access filtering where necessary.
- Prevent unauthorized retrieval of employee, leave, and payroll information.
- Never rely on the LLM to determine the user's permissions.
- Treat user messages and retrieved documents as untrusted input.
- Protect against prompt injection in indexed content.
- Avoid returning sensitive content from unrelated documents.
- Validate tool arguments and results.
- Avoid logging unnecessary personal data.
- Handle failures without exposing stack traces or secrets.
- Document demo-mode limitations.

**Authorization MUST be enforced before sensitive content reaches the model.** Hiding unauthorized content only in the final response is insufficient.

If the vector store does not support the required access controls natively, enforce equivalent filtering through a trusted retrieval service before returning chunks.

RAG MUST NOT be treated as a security boundary.

## Article XIII: Chainlit UI Standards

Chainlit MUST be the primary interactive interface.

The interface MUST provide:

- A clear HCM Lite AI Assistant title.
- A brief description of its capabilities.
- A visible demo-mode indicator when demo content is used.
- A working chat input.
- Readable agent responses.
- Suggested prompts for common HR questions.
- Clear presentation of leave drafts and summaries.
- Processing feedback where appropriate.
- Understandable error messages.
- Session-safe conversational context.
- A way to start a fresh conversation.
- Source references or citations for RAG-grounded answers when available.

Recommended suggested prompts:

- "How many employees are in the organization?"
- "Summarize attendance for this month."
- "What is my remaining annual leave balance?"
- "Prepare a leave request for next Monday and Tuesday."
- "What is the annual leave policy?"
- "Summarize the current HR dashboard."

Suggested prompts MUST trigger real application functionality.

The application MUST be usable during a live demonstration without requiring the reviewer to inspect source code or invoke backend functions manually.

## Article XIV: Configuration and Reproducible Execution

A new developer MUST be able to run the project by following the README.

The repository MUST include:

- A dependency file.
- A `.env.example` containing variable names but no real credentials.
- A `.gitignore`.
- A README.
- Source documents for the demo.
- An ingestion command or documented ingestion workflow.
- A configured vector-store adapter.
- Automated tests.
- Troubleshooting instructions.

Required environment configuration SHOULD include:

    OPENAI_API_KEY=
    OPENAI_MODEL=
    OPENAI_EMBEDDING_MODEL=
    VECTOR_STORE_PROVIDER=
    VECTOR_STORE_URL=
    VECTOR_STORE_API_KEY=
    RAG_TOP_K=
    RAG_SIMILARITY_THRESHOLD=

Only the variables required by the selected vector-store implementation need to be set. Secrets MUST remain outside version control.

The README MUST document:

1. Python environment setup.
2. Dependency installation.
3. Environment configuration.
4. Vector-store setup.
5. Document ingestion.
6. Index creation or initialization.
7. Application startup.
8. Test execution.
9. Troubleshooting.

Expected application command:

    chainlit run app.py

Expected test command:

    pytest -q

These commands MUST be verified against the actual implementation.

The application MUST NOT require an unavailable external service or production database to demonstrate its initial RAG workflow. If a vector-store service is required, document how to start or access it and verify that the configured connection works.

## Article XV: Testing Requirements

All important components MUST have automated tests.

### Agent tests

- Agent initialization.
- Basic conversation.
- Correct tool registration.
- Appropriate tool selection.
- Safe tool execution.
- Invalid tool arguments.
- Model errors and timeouts.

### RAG tests

- Document ingestion.
- Text extraction and chunking.
- Embedding generation with mocks where appropriate.
- Vector-store insertion and retrieval.
- Metadata filtering.
- Relevance threshold behavior.
- Empty retrieval results.
- Source attribution.
- Updated-document re-indexing.
- Malformed or unsupported documents.
- Prompt injection contained within retrieved content.
- Prevention of unauthorized document retrieval.
- Grounded answers that match retrieved content.

### HR workflow tests

- Exact metrics returned by structured services.
- Unauthorized requests.
- Smart leave extraction and validation.
- Missing leave information.
- Policy questions with relevant sources.
- Policy questions without relevant sources.
- Safe error handling.

### UI and integration tests

- Chainlit-to-agent integration.
- Session isolation.
- Demo-mode labeling.
- RAG retrieval through the actual application.
- Correct display of source references.
- Safe handling of API and vector-store failures.

Use mocked dependencies for deterministic unit tests where appropriate. Provide optional integration tests for real OpenAI and vector-store connections when credentials are configured.

Never claim that tests passed unless they were actually executed and verified.

## Article XVI: Acceptance Criteria

The initial application is demonstrable only when:

- [ ] The project installs in a clean Python environment.
- [ ] Chainlit starts using the documented command.
- [ ] The configured OpenAI model produces a real response.
- [ ] The OpenAI Agents SDK agent can call a registered tool.
- [ ] The RAG ingestion pipeline processes the configured source documents.
- [ ] The vector store contains indexed document chunks.
- [ ] The retriever returns relevant chunks for a supported question.
- [ ] The agent can answer a question using retrieved context.
- [ ] RAG-grounded answers provide source references when available.
- [ ] Unsupported answers are acknowledged instead of fabricated.
- [ ] No hardcoded local employee database is used as the primary source of HR facts.
- [ ] Exact numeric metrics use an authorized structured source.
- [ ] The seven required HR tools are implemented or explicitly tracked as incomplete.
- [ ] Smart leave produces a reviewable draft without automatically submitting it.
- [ ] Sensitive information is protected by authorization checks.
- [ ] Demo data is clearly identified.
- [ ] Relevant automated tests pass.
- [ ] README setup and run commands are verified.
- [ ] A reviewer can reproduce the demonstration.

Placeholders, pseudocode, and unimplemented features MUST NOT be reported as complete.

## Article XVII: Incremental Implementation Strategy

### Milestone 1: Runnable Foundation

- Set up Python and dependencies.
- Configure OpenAI credentials and model settings.
- Build the Chainlit interface.
- Create an OpenAI Agents SDK agent.
- Verify a real LLM response.

### Milestone 2: Basic RAG Pipeline

- Select and configure the vector store.
- Add a small, clearly labeled demo document collection.
- Implement ingestion, chunking, embeddings, and indexing.
- Implement semantic retrieval.
- Return a grounded answer with a source reference.
- Verify the workflow through Chainlit.

### Milestone 3: Agentic RAG

- Expose retrieval through a registered agent tool where appropriate.
- Allow the agent to decide when retrieval is necessary.
- Validate retrieved context before use.
- Add safe handling for empty or irrelevant retrieval results.
- Test the full agent-to-RAG workflow.

### Milestone 4: HR Tools

- Implement all seven required HR tools.
- Connect tools to authorized structured services or retrieval adapters.
- Add input validation and access controls.
- Use structured queries or APIs for exact numeric results.

### Milestone 5: HR Workflows

- Implement smart leave drafting.
- Implement dashboard summaries.
- Implement policy Q&A using RAG.
- Add citations, suggested prompts, and readable result formatting.

### Milestone 6: Security and Reliability

- Enforce document-level and record-level permissions.
- Add guardrails and execution limits.
- Test prompt-injection attempts.
- Test missing data and service failures.
- Verify session isolation and safe error handling.

### Milestone 7: Final Demonstration

- Run the complete test suite.
- Verify setup instructions from a clean environment.
- Demonstrate document ingestion and retrieval.
- Demonstrate an agent tool call.
- Demonstrate a grounded policy answer with a source reference.
- Document limitations and unfinished work.

Each milestone MUST leave the application in a runnable state.

## Article XVIII: Rules for AI Coding Agents

Any AI coding assistant working on this repository MUST:

1. Read this constitution and the relevant feature specification before making changes.
2. Inspect the repository before creating or replacing files.
3. Implement the smallest complete solution that satisfies the specification.
4. Preserve existing working functionality.
5. Use official OpenAI Agents SDK, OpenAI API, and Chainlit documentation.
6. Implement the actual RAG pipeline rather than simulating retrieval with hardcoded answers.
7. Avoid silently substituting a local employee database for the configured retrieval architecture.
8. Keep specifications, code, tests, and documentation synchronized.
9. Run relevant tests after implementation.
10. Fix discovered errors rather than hiding them.
11. Report changed files, commands executed, actual test outcomes, and limitations.
12. Never claim successful execution without verification.
13. Never expose secrets or sensitive HR information.
14. Never invent policies or organizational records.
15. Ask for clarification when ambiguity materially affects security, data integrity, or business behavior.

## Article XIX: Definition of Done

A feature is complete only when:

- Its specification exists.
- Its implementation satisfies the specification.
- Its inputs and outputs are validated.
- Its security requirements are enforced.
- Its retrieval behavior is tested where applicable.
- Its tests have been executed.
- Its behavior can be demonstrated through Chainlit or an integration test.
- Its setup and usage are documented.
- Its limitations are recorded.

**Final principle: Build a small, secure, runnable Agentic AI application with real RAG retrieval first. Expand it incrementally through specifications, verified tool execution, grounded responses, and automated testing.**

## Response snapshot

Replaced the placeholder template at `.specify/memory/constitution.md` with the 19 supplied
Articles (deduplicated from the triplicated input, content unchanged), prepended a Sync Impact
Report, and added a Governance section (supremacy, amendment procedure, semver policy, compliance
review). Version 1.1.0 (as supplied), ratified and last amended 2026-10-25. Propagated: filled the
Constitution Check gates in `plan-template.md` from Articles II–XVII; changed `tasks-template.md`
so tests are mandatory (Art. XV) instead of optional. `spec-template.md` reviewed, no change.

## Outcome

- ✅ Impact: Project constitution ratified at v1.1.0; plan/tasks templates aligned.
- 🧪 Tests: none (documentation only).
- 📁 Files: constitution.md, plan-template.md, tasks-template.md, this PHR.
- 🔁 Next prompts: /sp.specify for 001-agent-chat (Milestone 1); choose vector store (ADR candidate).
- 🧠 Reflection: Input was pasted three times; deduplicated. Governance section was missing from
  input and was added to satisfy the template's mandatory Governance heading.

## Evaluation notes (flywheel)

- Failure modes observed: duplicated user input; no prior constitution version to bump from.
- Graders run and results (PASS/FAIL): placeholder scan PASS (no bracket tokens remain).
- Prompt variant (if applicable): none
- Next experiment (smallest change to try): none
