-- Demo tenant seed (T187) — Lumière Coffee & Helix Analytics
-- Idempotent: wrapped in ON CONFLICT DO NOTHING / DO UPDATE.
-- Run after migrations have been applied.
-- Two tenants + an "attacker" stub for the blocked-origin isolation demo.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Tenants
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO tenants (id, slug, display_name, plan, persona_config, theme_config, guardrail_config, status)
VALUES (
    'a1000000-0000-0000-0000-000000000000',
    'lumiere-coffee',
    'Lumière Coffee',
    'poc',
    '{
        "persona_summary": "You are Café, a warm and friendly assistant for Lumière Coffee — a boutique specialty coffee shop. You help visitors discover our menu, book tables, and arrange catering. Use a conversational, welcoming tone. Refer to products by their names (Ethiopian, Colombian blend, seasonal roast). Never invent prices or policies not in the knowledge base."
    }'::jsonb,
    '{"primary_color": "#6B3A2A", "logo_url": "/static/lumiere-logo.png"}'::jsonb,
    '{}'::jsonb,
    'active'
)
ON CONFLICT (slug) DO UPDATE
    SET display_name  = EXCLUDED.display_name,
        persona_config = EXCLUDED.persona_config,
        updated_at     = now();

INSERT INTO tenants (id, slug, display_name, plan, persona_config, theme_config, guardrail_config, status)
VALUES (
    'b2000000-0000-0000-0000-000000000000',
    'helix-analytics',
    'Helix Analytics',
    'poc',
    '{
        "persona_summary": "You are Nexus, a precise and professional assistant for Helix Analytics — a B2B data analytics SaaS platform. You help visitors understand integrations, pricing, API documentation, and dashboard capabilities. Use a technical, concise tone. Always cite the specific doc page when answering API questions. Never reveal internal architecture."
    }'::jsonb,
    '{"primary_color": "#1A3A6B", "logo_url": "/static/helix-logo.png"}'::jsonb,
    '{}'::jsonb,
    'active'
)
ON CONFLICT (slug) DO UPDATE
    SET display_name  = EXCLUDED.display_name,
        persona_config = EXCLUDED.persona_config,
        updated_at     = now();

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Widgets
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO widgets (id, tenant_id, public_id)
VALUES (
    'a1000000-0000-0000-0001-000000000000',
    'a1000000-0000-0000-0000-000000000000',
    'lumiere-widget-v1'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO widgets (id, tenant_id, public_id)
VALUES (
    'b2000000-0000-0000-0001-000000000000',
    'b2000000-0000-0000-0000-000000000000',
    'helix-widget-v1'
)
ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Allowed origins
--    Lumière: localhost:3001  |  Helix: localhost:3002
--    Attacker stub: localhost:4000  (NOT in allowed_origins — for blocked-origin demo)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO allowed_origins (tenant_id, origin)
VALUES ('a1000000-0000-0000-0000-000000000000', 'http://localhost:3001')
ON CONFLICT ON CONSTRAINT uq_allowed_origin DO NOTHING;

INSERT INTO allowed_origins (tenant_id, origin)
VALUES ('b2000000-0000-0000-0000-000000000000', 'http://localhost:3002')
ON CONFLICT ON CONSTRAINT uq_allowed_origin DO NOTHING;

-- localhost:4000 intentionally absent — used in isolation demo to prove CORS blocks it.

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. CMS pages — Lumière Coffee (4 published pages)
--    IDs match the RAG golden set in tests/evals/rag/golden.jsonl
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'a1000000-0000-0000-0000-000000000001',
    'a1000000-0000-0000-0000-000000000000',
    'Hours & Location',
    E'# Hours & Location\n\nLumière Coffee is open Monday to Friday 7am–8pm, Saturday 8am–9pm, Sunday 9am–6pm.\nWe are located at 42 Rue de la Paix, Ground Floor. Free Wi-Fi available throughout.\nParking is available in the adjacent multi-storey car park with 2-hour validation.',
    'published',
    'hours-location',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'a1000000-0000-0000-0000-000000000002',
    'a1000000-0000-0000-0000-000000000000',
    'Reservations',
    E'# Reservations\n\nReservations can be made online for groups of 4 or more via our booking page.\nCancellations accepted up to 2 hours before the reservation time at no charge.\nFor same-day bookings of 8+ people, please call us directly.\n\nWe hold the table for 15 minutes past the booked time before releasing it.',
    'published',
    'reservations',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'a1000000-0000-0000-0000-000000000003',
    'a1000000-0000-0000-0000-000000000000',
    'Our Coffee Menu',
    E'# Our Coffee Menu\n\nWe source three core blends year-round:\n- Single-origin Ethiopian: bright, fruity, natural process\n- Colombian blend: balanced, caramel notes, medium roast\n- Seasonal rotating roast: changes quarterly; ask the barista for today''s origin\n\nRetail bags available in-store and via online order with free shipping over $40.',
    'published',
    'coffee-menu',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'a1000000-0000-0000-0000-000000000004',
    'a1000000-0000-0000-0000-000000000000',
    'Catering & Loyalty',
    E'# Catering & Loyalty\n\n## Catering\nCatering orders require 48 hours advance notice for groups under 30.\nLarger events (30+) need 5 business days lead time.\nA 20% deposit is required to confirm a catering booking.\n\n## Loyalty Programme\nStamp card — every 10th drink is free; digital version available in the app.\nStamps accumulate across all Lumière Coffee locations.',
    'published',
    'catering-loyalty',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. CMS pages — Helix Analytics (4 published pages)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'b2000000-0000-0000-0000-000000000001',
    'b2000000-0000-0000-0000-000000000000',
    'Pricing & SLA',
    E'# Pricing & SLA\n\n## Plans\n\n| Plan | Monthly | Seats |\n|------|---------|-------|\n| Starter | $299 | up to 5 seats |\n| Growth | $799 | up to 20 seats |\n| Enterprise | Custom | Unlimited |\n\n## Enterprise SLA\n99.9% uptime SLA with 4-hour response time for P1 incidents.\nDedicated customer success manager included.',
    'published',
    'pricing-sla',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'b2000000-0000-0000-0000-000000000002',
    'b2000000-0000-0000-0000-000000000000',
    'Integrations & Data Residency',
    E'# Integrations & Data Residency\n\nHelix Analytics integrates natively with Snowflake, BigQuery, Redshift, and Databricks.\nAdditional connectors: Salesforce, HubSpot, Google Sheets, and REST API push.\n\n## Data Residency\nData residency options available in US, EU, and APAC regions on the enterprise plan.\nAll data is encrypted at rest (AES-256) and in transit (TLS 1.3).',
    'published',
    'integrations',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'b2000000-0000-0000-0000-000000000003',
    'b2000000-0000-0000-0000-000000000000',
    'API Reference',
    E'# API Reference\n\n## Authentication\nPass a Bearer token in the Authorization header; tokens expire after 24 hours.\nGenerate tokens from Settings → API Keys. Rotate immediately if compromised.\n\n## Rate Limits\n1,000 requests per minute per tenant. Burst up to 2,000 for 10-second windows.\nRate limit headers: X-RateLimit-Remaining, X-RateLimit-Reset.\n\n## Versioning\nCurrent stable version: v2. v1 is deprecated and will be removed 2027-01-01.',
    'published',
    'api-reference',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug, published_at)
VALUES (
    'b2000000-0000-0000-0000-000000000004',
    'b2000000-0000-0000-0000-000000000000',
    'Dashboards & Exports',
    E'# Dashboards & Exports\n\n## Dashboard Builder\nDrag-and-drop dashboard builder with saved views and scheduled exports.\nUp to 50 widgets per dashboard; real-time refresh available on Growth and above.\n\n## Export Formats\nCSV, PDF, and live embed via iFrame or public link.\nScheduled email delivery supports daily, weekly, or monthly cadences.',
    'published',
    'dashboards',
    now()
)
ON CONFLICT (tenant_id, slug) DO UPDATE
    SET body = EXCLUDED.body, state = 'published', published_at = COALESCE(cms_pages.published_at, now()), updated_at = now();

COMMIT;
