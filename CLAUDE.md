# Project Rules

## Database Rules
- Shared Supabase — ALL table names prefixed with "deviceatlas_"
- Use `dbTable(name)` and `supabase` from `src/lib/supabase.ts` (provided by @mzon7/zon-incubator-sdk) for all table references
- Create/alter tables via Management API (env vars $SUPABASE_PROJECT_REF and $SUPABASE_MGMT_TOKEN are ALREADY SET — just use them directly):
  ```
  curl -s -X POST "https://api.supabase.com/v1/projects/$SUPABASE_PROJECT_REF/database/query" \
    -H "Authorization: Bearer $SUPABASE_MGMT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "..."}'
  ```
- To CHECK if tables exist:
  ```
  curl -s -X POST "https://api.supabase.com/v1/projects/$SUPABASE_PROJECT_REF/database/query" \
    -H "Authorization: Bearer $SUPABASE_MGMT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query": "SELECT tablename FROM pg_tables WHERE schemaname='"'"'public'"'"' AND tablename LIKE '"'"'deviceatlas_%'"'"';"}'
  ```
- Enable RLS on every new table
- ALWAYS add a SELECT policy whenever you add any other policy — never add INSERT/UPDATE/DELETE without SELECT or data will silently disappear on refresh
- Server-side API routes MUST use the service-role/admin Supabase client, NOT the anon client — this bypasses RLS and avoids policy gaps
- Client-side (browser) code may use the anon client — ensure matching RLS policies exist for every operation

## Auth Rules
- Auth components are provided by @mzon7/zon-incubator-sdk/auth: AuthProvider, useAuth, ProtectedRoute, AuthCallback
- Email confirmation is DISABLED (auto-confirm) — signUp() returns a session immediately, no email verification needed
- The /auth/callback route uses the AuthCallback component for OAuth/magic-link flows
- Do NOT show "check your email" messages after signup — users are signed in instantly

## AI API Rules
- Only use AI/LLM APIs for which API keys are available in .env.local
- Use OpenAI (GPT) via $OPENAI_API_KEY or xAI (Grok) via $GROK_API_KEY
- Do NOT use Anthropic SDK or any other AI provider — no ANTHROPIC_API_KEY is available
- Default to Grok (xAI) unless the user specifies GPT

## Architecture: Frontend/Backend Separation
- NEVER call external APIs (AI, payment, etc.) directly from browser/client code
- All external API calls MUST go through server-side routes (Supabase Edge Functions)
- Use `callEdgeFunction()` from @mzon7/zon-incubator-sdk to call edge functions
- API keys must NEVER be exposed client-side (no VITE_ prefix for secrets)
- For long-running operations (AI calls, processing): write a task row to DB, process server-side, client polls for results
- DB writes that must not be lost should go through API routes, not direct client Supabase calls

## SDK Usage
- This project uses `@mzon7/zon-incubator-sdk` — import from it, do NOT rewrite these utilities:
  - `import { createProjectClient, dbTable, validateEnv, callEdgeFunction } from '@mzon7/zon-incubator-sdk'`
  - `import { AuthProvider, useAuth, ProtectedRoute, AuthCallback } from '@mzon7/zon-incubator-sdk/auth'`
- The Supabase client and dbTable helper are already configured in `src/lib/supabase.ts`

## Project Context

## DeviceAtlas — Project Context (for Claude)

### Domain & data model (Supabase Postgres)
- **devices**
  - `id uuid PK`, `name`, `manufacturer`, `category`, `is_active bool`, `created_at`, `updated_at`
- **disease_states**
  - `id uuid PK`, `name`, `description`, `created_at`, `updated_at`
- **approvals**
  - `id uuid PK`
  - `device_id uuid FK -> devices.id`
  - `disease_state_id uuid FK -> disease_states.id`
  - `country enum {CA, US}`
  - `status enum {Approved, Pending, Retired, ...}`
  - `approval_date date?`, `retired_date date?`, `source_ref text?`
  - `is_active bool (explicit or derived)`, `created_at`, `updated_at`
- **approval_changes** (dashboard changelog)
  - `id`, `approval_id FK -> approvals.id`, `change_type {added|updated|retired}`, `changed_at`, `changed_by (user id/email)`, `diff jsonb`
- **audit_logs** (admin actions)
  - `id`, `actor_id`, `actor_email`, `entity_type {device|approval|import}`, `entity_id`, `action {create|update|deactivate|retire|import}`, `diff jsonb`, `created_at`
- **roles** (if not using auth claims)
  - `user_id`, `role {Admin|Editor|Viewer}`

Relationships: devices 1—* approvals; disease_states 1—* approvals; approvals 1—* approval_changes.

### Query/search assumptions
- Trigram GIN on `devices.name`, `disease_states.name`; btree on `devices.is_active`.
- approvals indexes: `(country,status)`, `(device_id)`, `(disease_state_id)`, `(updated_at)`.
- MVP queries join directly (materialized view optional later).

### State & data access patterns
- **React Query** for all server state (lists, search, detail, admin).
- **URL search params are source of truth** for Search filters/sort/pagination via `useSearchParamsState`.
- Local state only for form inputs + CSV preview.

### Admin gating & mutations
- Public pages: Supabase client `select` with filters/joins.
- Admin writes + CSV import: **edge functions** via `callEdgeFunction` to centralize validation, role checks, audit log writes, bulk upserts.
- RLS: public read-only; role-gated writes.

### Integrations
- **Sentry**: frontend init; edge functions log with request correlation id.

## Design & Branding
- A [DESIGN DIRECTIVE] block is injected into your prompt with the project's brand colors, fonts, and style.
- You MUST use the specified primary/secondary colors, border radius, font style, and density in ALL UI components.
- Do NOT use default Tailwind/shadcn theme colors (blue-500, gray-200, etc.) — always apply the brand palette.
- If a design-tokens.css or tailwind theme config exists, use those values. If not, apply colors inline or via CSS variables.
- Match the specified personality (e.g. "playful", "professional", "minimal") in your UI choices — spacing, copy tone, animation level.
