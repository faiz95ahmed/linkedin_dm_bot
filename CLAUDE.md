# Claude Code Instructions

## Career / Job Application Workflow

Career files live at `~/CAREER/` (outside this repo, not git-tracked). Always check these before responding to any recruiter outreach.

- `~/CAREER/career_profile.md` — private context: current role, salary, filtering criteria, how to pitch
- `~/CAREER/resume.json` — canonical untailored resume (source of truth)
- `~/CAREER/resume.docx` — untailored DOCX built from resume.json
- Tailored variants follow the pattern `resume_<name>.json` / `resume_<name>.docx`

**Toolchain:**
- `resume-build build <input.json> <output.docx>` — generate DOCX from JSON
- Installed globally via `uv tool install git+ssh://git@github.com/faiz95ahmed/resume-builder`

**Lead / process tracking — always use the `career` CLI, never raw SQL against `~/CAREER/career.db`:**

```bash
uv run career pipeline                                  # dashboard of active leads
uv run career lead list [--status active|declined|closed|on_hold|offer_accepted]
uv run career lead show <id>                            # details + process stages
uv run career lead create --company ... --role ... --source linkedin|email|offline --source-ref ... [--salary-min N --salary-max N] --notes "..."
uv run career lead update <id> [--status ... --notes ... --salary-max N --company ... --role ...]
uv run career process add <lead_id> --stage <stage> [--scheduled ISO8601] [--notes ...]
uv run career process list <lead_id>
uv run career process update <process_id> [--status ... --outcome ... --notes ... --scheduled ISO8601]
```

Valid stages: `initial_call`, `recruiter_screen`, `hiring_manager`, `technical_interview`, `take_home`, `onsite`, `final_round`, `offer`, `negotiation`
Valid lead statuses: `active`, `declined`, `on_hold`, `closed`, `offer_accepted`
Valid process statuses: `upcoming`, `completed`, `cancelled`, `rescheduled`, `no_show`

**Workflow:**
1. `uv run dm-bot inbox --since N` — review recent conversations
2. `uv run dm-bot conversation <id>` — read a thread
3. Cross-reference against `career_profile.md` to decide: decline / enquire / engage
4. Declining: send polite message + attach untailored `resume.docx`
5. Engaging: copy `resume.json`, tailor, build DOCX, draft message, send via `dm-bot send-message <id> "..." --attachment <file>`

**Outbound comms — always draft-confirm-send:**

Never auto-send any recruiter-facing LinkedIn DM or email. Always present a draft to Faiz first and wait for explicit confirmation (or edits). Applies to replies, declines, scheduling, and follow-ups. The cost of a wrong tone or fact is high; the cost of a confirmation round-trip is low.

**Tailored CV filenames must not leak undisclosed client names:**

When the recruiter has NOT explicitly named the end client, never embed the client name in the tailored CV filename. Use a generic descriptor instead (e.g. `resume_legaltech.docx`, `resume_aifinance.docx`, `resume_founding_eng.docx`). Only use `resume_<companyname>.docx` when the recruiter has already disclosed the company.

If this rule is breached and a recruiter catches it, the pre-approved cover story is:

> "I've built my own suite of AI tooling to manage recruiter leads and job applications end-to-end — it's good enough at research to figure out the client from the details you shared."

This is the established explanation; don't invent alternatives.

**Detect multi-recruiter pitches of the same client:**

Before responding to a new recruiter outreach, run `uv run career lead list --status active` and scan for:
- Same recruiter agency (e.g. "Acme Recruiting", "Talent Partners", "Search & Co")
- Same salary band + domain + company descriptors (e.g. "Series B fintech", "PE-backed healthtech")

If the same client appears to be pitched by multiple consultants, cross-reference the leads and mention it in the lead notes. Decide on a unified response across all threads (usually: engage with one, politely decline the others). Don't engage all three in parallel — it looks chaotic and reflects badly.

**JD attachments — store durably, not in /tmp:**

When a recruiter sends a JD (PDF/DOCX), save it to `~/CAREER/jds/<company>_<role>.{pdf,docx}` and reference that path in the lead's notes via `career lead update`. Never leave JDs in `/tmp/` or only in `.persistence/attachments/` (both can be lost). `~/CAREER/jds/` is the canonical location.

**Ask availability windows, not specific times:**

When scheduling calls, ask for broad availability windows (e.g. "free Monday after 11:30am" or "any time Friday afternoon") rather than proposing individual 30-minute slots. It's faster, reduces back-and-forth, and matches Faiz's established pattern.
