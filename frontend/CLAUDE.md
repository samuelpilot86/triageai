@AGENTS.md

## Project context

- **Frontend remote:** `github` → GitHub/Vercel (deploy). Never use `origin` for frontend pushes — `origin` points to HF Spaces (backend).
- **Backend remote:** `origin` → HuggingFace Spaces. Push backend with `git push origin main`.
- **Shared component:** `AppFooter` in `components/AppFooter.tsx` — used by both `app/page.tsx` and `app/about/page.tsx`. Any footer change goes there only.
- **Contact API:** `app/api/contact/route.ts` uses Resend (`RESEND_API_KEY` env var). Never expose email addresses in frontend code.
- **SSE streaming:** backend yields typed events (`status`, `sifted`, `categorization`, `clustered`, `report`, `user_stories`, `done`, `error`). Frontend handles them in `lib/useAnalysis.ts` → `handleEvents`.
- **Timing history:** stored in `timings.json` on HF Space, served via `GET /api/timings?step=<step>`. Steps: `sift`, `categorization`, `clustering`, `report`, `stella`.

## Constraints

- Free-tier quotas are a hard architectural constraint — always consider RPD/TPD impact when changing model routing.
- Sift and Iris are parallelized (chunks of 25 and 30 respectively) — timing estimates use `min(n, CHUNK_SIZE)`, not `n`.
- `SIFT_CHUNK_SIZE=25` and `GROQ_CHUNK_SIZE=30` are mirrored in `agent.py` (backend) and `lib/useAnalysis.ts` (frontend) — keep in sync.
