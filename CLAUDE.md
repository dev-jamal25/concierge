<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/001-concierge-platform/plan.md`. Supporting artifacts:

- Specification: `specs/001-concierge-platform/spec.md`
- Research & decisions: `specs/001-concierge-platform/research.md`
- Data model + RLS policies: `specs/001-concierge-platform/data-model.md`
- API contract: `specs/001-concierge-platform/contracts/api.openapi.yaml`
- Widget loader contract: `specs/001-concierge-platform/contracts/widget-loader.md`
- Internal contracts: `specs/001-concierge-platform/contracts/internal/`
- Quickstart (compose-up to first chat turn): `specs/001-concierge-platform/quickstart.md`
- Constitution (NON-NEGOTIABLE principles): `.specify/memory/constitution.md`
- Tasks (owner implementation checklist): `specs/001-concierge-platform/tasks.md`
<!-- SPECKIT END -->

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

# Owner A skills
Use `.claude/skills/tenant-isolation-auditor/SKILL.md` before and after Owner A tenancy/RLS/provisioning changes.

# Project skills
## 🛡️ Quality Assurance & Auditing (Phase Transition)
When asked to "run QA", "audit the project", or begin the quality assurance phase, you must **NOT** attempt to manually review or modify the codebase yourself. Instead, you must strictly delegate the entire process by invoking the custom skill located at `.claude/skills/full-project-qa-auditor/SKILL.md`. This will correctly initialize the read-only Orchestrator and the multi-agent testing pipeline.