-- Demo analytics seed — realistic conversations, messages, leads, and escalations
-- for Lumière Coffee and Helix Analytics.
--
-- Idempotent: all rows use fixed UUIDs with ON CONFLICT (id) DO NOTHING.
-- Runs via migration_database_url (superuser role — bypasses RLS).
-- Requires seed_demo_tenants.sql to have run first (tenant + widget rows must exist).
--
-- Tenant IDs (from seed_demo_tenants.sql):
--   Lumière Coffee : a1000000-0000-0000-0000-000000000000
--   Helix Analytics: b2000000-0000-0000-0000-000000000000
-- Widget IDs:
--   Lumière : a1000000-0000-0000-0001-000000000000
--   Helix   : b2000000-0000-0000-0001-000000000000

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Extra CMS pages (draft + unpublished) so the state chart is interesting
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug)
VALUES (
    'a1000000-0000-0000-0000-000000000010',
    'a1000000-0000-0000-0000-000000000000',
    'Autumn Seasonal Menu (Draft)',
    E'# Autumn Seasonal Menu\n\nComing soon: our pumpkin spice blend and maple latte.\nAvailable from 1 October.',
    'draft',
    'autumn-menu-draft'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug)
VALUES (
    'a1000000-0000-0000-0000-000000000011',
    'a1000000-0000-0000-0000-000000000000',
    'Summer Specials 2024',
    E'# Summer Specials 2024\n\nOur cold brew and iced latte range from Summer 2024.\n(Offer has ended.)',
    'unpublished',
    'summer-specials-2024'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug)
VALUES (
    'b2000000-0000-0000-0000-000000000010',
    'b2000000-0000-0000-0000-000000000000',
    'GDPR Data Processing Addendum (Draft)',
    E'# DPA Draft\n\nThis document is under legal review and not yet published.',
    'draft',
    'dpa-draft'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO cms_pages (id, tenant_id, title, body, state, slug)
VALUES (
    'b2000000-0000-0000-0000-000000000011',
    'b2000000-0000-0000-0000-000000000000',
    'v1 API Docs (Deprecated)',
    E'# v1 API Reference (Deprecated)\n\nThis version was retired 2024-06-01. Please use v2.',
    'unpublished',
    'api-v1-deprecated'
) ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Conversations — Lumière Coffee (15 conversations over ~10 days)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0001-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-01', now()-'10 days'::interval, now()-'10 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0002-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-02', now()-'9 days'::interval, now()-'9 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0003-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-03', now()-'8 days'::interval, now()-'8 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0004-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-04', now()-'8 days'::interval+'2 hours'::interval, now()-'8 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at, escalated_at, escalation_reason)
VALUES ('a1000000-0001-0000-0005-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-05', now()-'7 days'::interval, now()-'7 days'::interval, now()-'7 days'::interval+'5 minutes'::interval, 'visitor_request')
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0006-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-06', now()-'7 days'::interval+'3 hours'::interval, now()-'7 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0007-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-07', now()-'5 days'::interval, now()-'5 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0008-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-08', now()-'5 days'::interval+'4 hours'::interval, now()-'5 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at, escalated_at, escalation_reason)
VALUES ('a1000000-0001-0000-0009-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-09', now()-'4 days'::interval, now()-'4 days'::interval, now()-'4 days'::interval+'3 minutes'::interval, 'visitor_request')
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0010-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-10', now()-'3 days'::interval, now()-'3 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0011-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-11', now()-'3 days'::interval+'5 hours'::interval, now()-'3 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0012-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-12', now()-'2 days'::interval, now()-'2 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at, escalated_at, escalation_reason)
VALUES ('a1000000-0001-0000-0013-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-13', now()-'1 day'::interval, now()-'1 day'::interval, now()-'1 day'::interval+'2 minutes'::interval, 'llm_unavailable')
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0014-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-14', now()-'1 day'::interval+'2 hours'::interval, now()-'1 day'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('a1000000-0001-0000-0015-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0000-0000-0001-000000000000','vsess-lum-15', now()-'3 hours'::interval, now()-'1 hour'::interval)
ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Conversations — Helix Analytics (12 conversations over ~10 days)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0001-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-01', now()-'10 days'::interval, now()-'10 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0002-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-02', now()-'8 days'::interval, now()-'8 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0003-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-03', now()-'7 days'::interval, now()-'7 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at, escalated_at, escalation_reason)
VALUES ('b2000000-0001-0000-0004-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-04', now()-'6 days'::interval, now()-'6 days'::interval, now()-'6 days'::interval+'4 minutes'::interval, 'visitor_request')
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0005-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-05', now()-'5 days'::interval, now()-'5 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0006-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-06', now()-'4 days'::interval, now()-'4 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0007-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-07', now()-'3 days'::interval, now()-'3 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at, escalated_at, escalation_reason)
VALUES ('b2000000-0001-0000-0008-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-08', now()-'2 days'::interval, now()-'2 days'::interval, now()-'2 days'::interval+'6 minutes'::interval, 'tool_loop_cap')
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0009-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-09', now()-'2 days'::interval+'3 hours'::interval, now()-'2 days'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0010-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-10', now()-'1 day'::interval, now()-'1 day'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0011-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-11', now()-'4 hours'::interval, now()-'2 hours'::interval)
ON CONFLICT (id) DO NOTHING;
INSERT INTO conversations (id, tenant_id, widget_id, visitor_session, started_at, last_turn_at)
VALUES ('b2000000-0001-0000-0012-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0000-0000-0001-000000000000','vsess-hel-12', now()-'1 hour'::interval, now()-'30 minutes'::interval)
ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Messages — Lumière Coffee (router_label drives "conversations by intent")
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0001-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0001-000000000000','visitor','faq','What are your opening hours?', now()-'10 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0001-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0001-000000000000','agent',NULL,'We are open Mon–Fri 7am–8pm, Saturday 8am–9pm, Sunday 9am–6pm.', now()-'10 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0002-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0002-000000000000','visitor','faq','Do you have oat milk options?', now()-'9 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0002-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0002-000000000000','agent',NULL,'Yes, oat, almond, and soy milk are all available as alternatives.', now()-'9 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0003-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0003-000000000000','visitor','faq','How do I make a reservation for 6 people?', now()-'8 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0003-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0003-000000000000','agent',NULL,'You can book online for groups of 4 or more via our reservations page.', now()-'8 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0004-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0004-000000000000','visitor','lead_intent','I need catering for a corporate event next month. Can someone contact me?', now()-'8 days'::interval+'2 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0004-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0004-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'8 days'::interval+'2 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0005-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0005-000000000000','visitor','escalate','I want to speak to a manager about my experience last week.', now()-'7 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0005-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0005-000000000000','agent',NULL,'You''ve been connected with our team. Someone will follow up shortly.', now()-'7 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0006-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0006-000000000000','visitor','faq','Is there free Wi-Fi at the café?', now()-'7 days'::interval+'3 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0006-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0006-000000000000','agent',NULL,'Yes, free Wi-Fi is available throughout the café.', now()-'7 days'::interval+'3 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0007-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0007-000000000000','visitor','faq','How does the loyalty stamp card work?', now()-'5 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0007-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0007-000000000000','agent',NULL,'Every 10th drink is free. A digital version is available in the app.', now()-'5 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0008-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0008-000000000000','visitor','lead_intent','I''m interested in buying wholesale coffee beans for my office. Who should I talk to?', now()-'5 days'::interval+'4 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0008-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0008-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'5 days'::interval+'4 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0009-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0009-000000000000','visitor','escalate','I need to talk to a human right now about my catering order.', now()-'4 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0009-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0009-000000000000','agent',NULL,'You''ve been connected with our team. Someone will follow up shortly.', now()-'4 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0010-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0010-000000000000','visitor','faq','What parking is available near you?', now()-'3 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0010-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0010-000000000000','agent',NULL,'There is a multi-storey car park adjacent with 2-hour validation.', now()-'3 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0011-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0011-000000000000','visitor','lead_intent','We want to arrange a weekly breakfast delivery for our team of 20. Can you help?', now()-'3 days'::interval+'5 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0011-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0011-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'3 days'::interval+'5 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0012-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0012-000000000000','visitor','ambiguous','Tell me more about your seasonal roast', now()-'2 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0012-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0012-000000000000','agent',NULL,'Our seasonal rotating roast changes quarterly — ask the barista for today''s origin.', now()-'2 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0013-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0013-000000000000','visitor','faq','Are you open on public holidays?', now()-'1 day'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0013-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0013-000000000000','agent',NULL,'Service was temporarily unavailable. Please try again shortly.', now()-'1 day'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0014-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0014-000000000000','visitor','lead_intent','I''d like to organise a coffee tasting event for a team of 15. Can we talk?', now()-'1 day'::interval+'2 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0014-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0014-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'1 day'::interval+'2 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0015-000000000001','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0015-000000000000','visitor','faq','What''s the price of a flat white?', now()-'3 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('a1000000-0002-0000-0015-000000000002','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0015-000000000000','agent',NULL,'Drink pricing is listed on our in-store menu. Visit us at 42 Rue de la Paix.', now()-'3 hours'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Messages — Helix Analytics
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0001-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0001-000000000000','visitor','faq','What integrations do you support?', now()-'10 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0001-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0001-000000000000','agent',NULL,'We integrate natively with Snowflake, BigQuery, Redshift, and Databricks.', now()-'10 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0002-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0002-000000000000','visitor','faq','What is the Growth plan pricing?', now()-'8 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0002-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0002-000000000000','agent',NULL,'Growth plan is $799/month for up to 20 seats.', now()-'8 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0003-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0003-000000000000','visitor','lead_intent','We need enterprise pricing for 200 seats across 3 regions. Who should I contact?', now()-'7 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0003-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0003-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'7 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0004-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0004-000000000000','visitor','escalate','I need to speak with your compliance team about our data residency requirements.', now()-'6 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0004-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0004-000000000000','agent',NULL,'You''ve been connected with our team. Someone will follow up shortly.', now()-'6 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0005-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0005-000000000000','visitor','faq','How do I rotate my API key?', now()-'5 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0005-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0005-000000000000','agent',NULL,'Go to Settings → API Keys and click Rotate. Rotate immediately if compromised.', now()-'5 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0006-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0006-000000000000','visitor','lead_intent','Interested in upgrading from Starter to Growth. Can I get a demo call?', now()-'4 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0006-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0006-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'4 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0007-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0007-000000000000','visitor','faq','Does the API support OAuth2?', now()-'3 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0007-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0007-000000000000','agent',NULL,'Authentication uses Bearer tokens. OAuth2 is on our roadmap for Enterprise.', now()-'3 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0008-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0008-000000000000','visitor','ambiguous','I''m trying to use the dashboard export but the scheduled export keeps failing', now()-'2 days'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0008-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0008-000000000000','agent',NULL,'Service was temporarily unavailable. A team member will follow up.', now()-'2 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0009-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0009-000000000000','visitor','faq','What is your uptime SLA?', now()-'2 days'::interval+'3 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0009-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0009-000000000000','agent',NULL,'We offer 99.9% uptime SLA with 4-hour P1 response on Enterprise.', now()-'2 days'::interval+'3 hours 1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0010-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0010-000000000000','visitor','lead_intent','We want to migrate from Looker to Helix. Is there a migration service?', now()-'1 day'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0010-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0010-000000000000','agent',NULL,'Thanks! We''ve noted your interest and will be in touch.', now()-'1 day'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0011-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0011-000000000000','visitor','faq','Can I embed dashboards in my own web app?', now()-'4 hours'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0011-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0011-000000000000','agent',NULL,'Yes, live embed via iFrame or public link is supported on Growth and above.', now()-'4 hours'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0012-000000000001','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0012-000000000000','visitor','faq','What data regions are available?', now()-'1 hour'::interval) ON CONFLICT (id) DO NOTHING;
INSERT INTO messages (id, tenant_id, conversation_id, role, router_label, content, created_at)
VALUES ('b2000000-0002-0000-0012-000000000002','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0012-000000000000','agent',NULL,'US, EU, and APAC regions are available on Enterprise plans.', now()-'1 hour'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Leads — Lumière Coffee
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('a1000000-0003-0000-0001-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0004-000000000000','Sarah Chen','sarah.chen@brightworks.com','Corporate catering for 40-person event', now()-'8 days'::interval+'2 hours 2 minutes'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('a1000000-0003-0000-0002-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0008-000000000000','James Okafor','j.okafor@novanet.io','Wholesale coffee beans — monthly office supply', now()-'5 days'::interval+'4 hours 2 minutes'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('a1000000-0003-0000-0003-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0011-000000000000','Emma Larsson','emma@verdant-studio.com','Weekly team breakfast delivery for 20 people', now()-'3 days'::interval+'5 hours 2 minutes'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('a1000000-0003-0000-0004-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0014-000000000000','Michael Torres','m.torres@apexcorp.com','Coffee tasting experience for team of 15', now()-'1 day'::interval+'2 hours 2 minutes'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('a1000000-0003-0000-0005-000000000000','a1000000-0000-0000-0000-000000000000','a1000000-0001-0000-0015-000000000000','Lisa Park','+44 7700 900123','Catering inquiry for charity gala dinner', now()-'2 hours'::interval) ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. Leads — Helix Analytics
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('b2000000-0003-0000-0001-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0003-000000000000','David Kim','d.kim@dataflow.ai','Enterprise plan for 200 seats, 3 regions', now()-'7 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('b2000000-0003-0000-0002-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0006-000000000000','Rachel Moore','rachel.moore@syncgroup.com','Upgrade Starter → Growth, demo call requested', now()-'4 days'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('b2000000-0003-0000-0003-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0010-000000000000','Alex Johnson','alex.j@oriondata.io','Looker to Helix migration, managed service', now()-'1 day'::interval+'1 minute'::interval) ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent, created_at)
VALUES ('b2000000-0003-0000-0004-000000000000','b2000000-0000-0000-0000-000000000000','b2000000-0001-0000-0012-000000000000','Priya Nair','priya.n@meridian.tech','Real-time dashboards + API embed for SaaS product', now()-'45 minutes'::interval) ON CONFLICT (id) DO NOTHING;

COMMIT;
