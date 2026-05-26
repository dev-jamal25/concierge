# Graph Report - .  (2026-05-25)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 340 nodes · 435 edges · 33 communities (22 shown, 11 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d9b406cb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `Concierge Implementation Plan` - 41 edges
2. `Concierge Platform Feature Specification` - 29 edges
3. `Concierge Phase 0 Research & Decisions` - 14 edges
4. `Concierge Constitution` - 11 edges
5. `Concierge Data Model` - 11 edges
6. `Docker Compose Stack` - 10 edges
7. `files` - 9 edges
8. `Tenant Entity` - 9 edges
9. `Concierge Quickstart Guide` - 9 edges
10. `speckit` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Concierge Data Model` --conceptually_related_to--> `Tenant Isolation`  [INFERRED]
  specs/001-concierge-platform/data-model.md → .specify/memory/constitution.md
- `Clean Architecture & Dependency Rule` --conceptually_related_to--> `AgentTurnUseCase`  [INFERRED]
  .specify/memory/constitution.md → specs/001-concierge-platform/plan.md
- `Defense-in-Depth Security` --conceptually_related_to--> `OriginCheckMiddleware`  [INFERRED]
  .specify/memory/constitution.md → specs/001-concierge-platform/plan.md
- `Speckit Plan Context Reference` --references--> `Concierge Implementation Plan`  [EXTRACTED]
  CLAUDE.md → specs/001-concierge-platform/plan.md
- `speckit-analyze Skill` --references--> `Concierge Constitution`  [EXTRACTED]
  .claude/skills/speckit-analyze/SKILL.md → .specify/memory/constitution.md

## Hyperedges (group relationships)
- **Tenant Isolation Defense-in-Depth** — framework_tenant_context_middleware, infra_postgres_rls, adapter_tenant_repo, concept_tenant_isolation [INFERRED]
- **Agent Tool-Calling Triad** — usecase_rag_search, usecase_capture_lead, usecase_escalate, usecase_agent_turn [INFERRED]
- **Four CI Eval Gates** — eval_classifier_gate, eval_tool_selection_gate, eval_rag_gate, eval_redteam_gate [INFERRED]

## Communities (33 total, 11 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (49): Specification Quality Checklist, Paragraph-Aware Chunking Strategy (400/50/600 tokens), 5-Label Classifier Taxonomy, Concierge Phase 0 Research & Decisions, Cross-Encoder Rerank (top-20 → top-5), docs/DECISIONS.md, EmbeddingClient Protocol, Hosted Embedding Provider (Voyage/Cohere/OpenAI) (+41 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (47): ChunkRepository Adapter, ModelserverClassifierClient Adapter, ConversationRepository Adapter, HostedEmbeddingClient Adapter, NeMoGuardrailsClient Adapter, LeadRepository Adapter, AnthropicLLMClient Adapter, MinIOObjectStorage Adapter (+39 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (23): Streamlit Tenant Admin UI, Alembic Database Migrations, FastAPI Backend Service, Concierge Quickstart Guide, Docker Compose Stack, NeMo Guardrails Sidecar, MinIO Object Storage Service, model_card.yaml (Modelserver Artifact) (+15 more)

### Community 3 - "Community 3"
Cohesion: 0.11
Nodes (21): POST /chat, CMS Pages Endpoints, Leads Endpoints, Manager Tenants Endpoints, Schema: ChatTurnResponse, Schema: CMSPage, Schema: Lead, Schema: TenantSummary (+13 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (20): Admin Allowed Origins Endpoints, Admin Tenant Settings Endpoints, Auth Endpoints (fastapi-users), Concierge Platform API, Schema: AllowedOrigin, Schema: TenantSettings, Schema: WidgetConfig, Session Cookie Security Scheme (fastapi-users) (+12 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (16): ai, ai_skills, branch_numbering, context_file, here, script, speckit_version, invoke_separator (+8 more)

### Community 6 - "Community 6"
Cohesion: 0.23
Nodes (11): Find-FeatureDirByPrefix(), Find-SpecifyRoot(), Get-CurrentBranch(), Get-FeatureDirFromBranchPrefixOrExit(), Get-FeaturePathsEnv(), Get-Python3Command(), Get-RepoRoot(), Get-SpecKitEffectiveBranchName() (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.16
Nodes (15): Extensions Configuration, speckit.git.commit Command, speckit.git.feature Command, speckit.git.initialize Command, speckit.git.remote Command, speckit.git.validate Command, Git Config Template, Git Config (Active) (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.21
Nodes (13): Admin Guardrails Endpoints, Schema: TenantGuardrailConfig, Widget JWT Security Scheme (Ed25519), NeMo Guardrails, tenant_id JWT Claim (Single Source of Tenancy Truth), Vault Key Management (Ed25519 JWT signing), POST /check (Guardrails), Guardrails Sidecar Internal API (+5 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (12): files, .specify/scripts/powershell/check-prerequisites.ps1, .specify/scripts/powershell/common.ps1, .specify/scripts/powershell/create-new-feature.ps1, .specify/scripts/powershell/setup-plan.ps1, .specify/templates/checklist-template.md, .specify/templates/constitution-template.md, .specify/templates/plan-template.md (+4 more)

### Community 10 - "Community 10"
Cohesion: 0.21
Nodes (12): Checklist Template, Constitution Template, Plan Template, Spec Template, speckit-checklist Skill, speckit-constitution Skill, speckit-implement Skill, speckit-plan Skill (+4 more)

### Community 11 - "Community 11"
Cohesion: 0.20
Nodes (3): _extract_highest_number(), get_highest_from_branches(), create-new-feature.sh script

### Community 12 - "Community 12"
Cohesion: 0.36
Nodes (11): Concierge Data Model, Allowed Origin Entity, Audit Entry Entity, Chunk Entity (Vector Store), CMS Page Entity, Conversation Entity, Lead Entity, Tenant Entity (+3 more)

### Community 13 - "Community 13"
Cohesion: 0.20
Nodes (9): schema_version, description, installed_at, name, source, updated_at, version, workflows (+1 more)

### Community 14 - "Community 14"
Cohesion: 0.22
Nodes (8): files, .claude/skills/speckit-clarify/SKILL.md, .claude/skills/speckit-implement/SKILL.md, .claude/skills/speckit-plan/SKILL.md, .claude/skills/speckit-taskstoissues/SKILL.md, installed_at, integration, version

### Community 15 - "Community 15"
Cohesion: 0.39
Nodes (7): ConvertTo-CleanBranchName(), Get-BranchName(), Get-HighestNumberFromBranches(), Get-HighestNumberFromNames(), Get-HighestNumberFromRemoteRefs(), Get-HighestNumberFromSpecs(), Get-NextBranchNumber()

### Community 16 - "Community 16"
Cohesion: 0.46
Nodes (7): ConvertTo-CleanBranchName(), Get-BranchName(), Get-HighestNumberFromBranches(), Get-HighestNumberFromNames(), Get-HighestNumberFromRemoteRefs(), Get-HighestNumberFromSpecs(), Get-NextBranchNumber()

## Knowledge Gaps
- **106 isolated node(s):** `PreToolUse`, `feature_directory`, `ai`, `ai_skills`, `branch_numbering` (+101 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Concierge Implementation Plan` connect `Community 1` to `Community 12`?**
  _High betweenness centrality (0.144) - this node is a cross-community bridge._
- **Why does `Paragraph-Aware Chunking Strategy (400/50/600 tokens)` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **Why does `ReindexTenantChunksUseCase` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.106) - this node is a cross-community bridge._
- **What connects `PreToolUse`, `feature_directory`, `ai` to the rest of the system?**
  _108 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06037414965986394 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.06938020351526364 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.09486166007905138 - nodes in this community are weakly interconnected._