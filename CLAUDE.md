# Claude Code Instructions

## Career Files & Toolchain

Career files live at `~/CAREER/` (outside this repo, not git-tracked). Always check these before responding to any recruiter outreach.

- `~/CAREER/career_profile.md` — private context: current role, salary, filtering criteria, how to pitch
- `~/CAREER/resume.json` — canonical untailored resume (source of truth)
- `~/CAREER/resume.docx` — untailored DOCX built from resume.json
- Tailored variants follow the pattern `resume_<name>.json` / `resume_<name>.docx`

**Toolchain:**
- `resume-build build <input.json> <output.docx>` — generate DOCX from JSON
- Installed globally via `uv tool install git+ssh://git@github.com/faiz95ahmed/resume-builder`

## LinkedIn Sync

**CLI reference:**

```bash
dm-bot sync [--since DATE] [--limit N]          # sync conversations from LinkedIn
dm-bot sync-conversation URL                     # sync a single conversation by URL
dm-bot inbox [--since N] [--limit N]             # list recent conversations
dm-bot conversation <id>                         # print full thread
dm-bot find <name>                               # search by contact name
dm-bot get-url <id>                              # get thread URL
```

**Workflow:**
1. `uv run dm-bot sync --limit N` — pull latest conversations
2. `uv run dm-bot inbox --since N` — review what's new
3. `uv run dm-bot conversation <id>` — read a specific thread

## Email Sync Workflow

**CLI reference:**

```bash
email-sync last-sync                                    # last email sync timestamp
email-sync fetch -s ISO -o DIR -l SET [-b EXTRA...]     # fetch + filter + write JSON to /tmp/email-reader/DIR/
email-sync collect -f DIR THREAD_ID [THREAD_ID...]      # collect threads + download attachments
email-sync download-attachments MSG_ID [-o DIR]          # download attachments from a single message

email-sync blocklist create|delete|list
email-sync blocklist show|add|remove NAME [PATTERN...]

email-sync blocklist-set create|delete|list
email-sync blocklist-set show|add|remove NAME [BLOCKLIST...]
```

**End-to-end email ingestion workflow:**

1. Check last sync: `uv run email-sync last-sync`
2. List blocklist sets: `uv run email-sync blocklist-set list`
3. Inspect a candidate set: `uv run email-sync blocklist-set show SET_NAME`
4. Decision: use existing set, modify it (add/remove blocklists), or create new
5. Optionally inspect blocklist contents: `uv run email-sync blocklist show BLOCKLIST_NAME`
6. Fetch: `uv run email-sync fetch -s SINCE -o OUTPUT_DIR -l SET_NAME`
7. Filter: invoke `email-relevance-filter` agent on each `/tmp/email-reader/OUTPUT_DIR/{N}.json`
8. Blocklist hygiene: add irrelevant addresses to existing blocklists or create new ones (and add to set)
9. Collect: `uv run email-sync collect -f OUTPUT_DIR THREAD_ID [...]`
10. Result: `/tmp/email-reader/OUTPUT_DIR/collected.json` — relevant threads with attachment `localPath` references pointing to `/tmp/email-reader/OUTPUT_DIR/attachments/`

## Calendar

Use `gws calendar` for checking availability and scheduling recruiter calls.

```bash
gws calendar +agenda                                     # show upcoming events
gws calendar events list --params '{"calendarId": "primary", "timeMin": "ISO", "timeMax": "ISO", "maxResults": 10}'
gws calendar +insert --summary "..." --start "2026-03-29T10:00:00" --end "2026-03-29T11:00:00"
```

**Scheduling workflow:**
1. Check existing calendar: `gws calendar +agenda` or list events for the proposed date range
2. Identify free slots within the availability window the user has offered
3. Once the recruiter confirms a time, create the event with a clear summary (e.g. "Call — Recruiter Name / Company — Role")

## Lead & Process Tracking

Always use the `career` CLI, never raw SQL against `~/CAREER/career.db`:

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

## Sync & Triage

If the user asks only to "sync" (without "triage"), confirm whether they mean just syncing or the full sync & triage pipeline.

When the user asks to "sync and triage" (or similar), run the full pipeline:

1. **Sync** (parallel): `dm-bot sync --limit N` + email fetch/filter/collect workflow
2. **Ingest**: read new conversations + collected emails, cross-reference against `career_profile.md` and active leads (detect multi-recruiter pitches)
3. **Research** (parallel): invoke `opportunity-researcher` agent on promising new leads
4. **Draft**: prepare a consolidated summary table of all new/updated leads with fit assessment and recommended action, plus draft replies
5. **Discuss**: present findings to user, clarify unknowns, get decisions on each lead
6. **Act**: send approved replies, create/update leads in career manager, save any JDs to `~/CAREER/jds/`

See: LinkedIn Sync, Email Sync Workflow, Ingestion & Decision-Making sections for details on each step.

## Ingestion & Decision-Making

After syncing LinkedIn messages or collecting email threads:

1. Read new LinkedIn conversations: `uv run dm-bot conversation <id>`
2. Read collected email threads: review `/tmp/email-reader/OUTPUT_DIR/collected.json`
3. Check attachments in `.persistence/attachments/` — save JDs durably to `~/CAREER/jds/<company>_<role>.{pdf,docx}` and reference that path in the lead's notes via `career lead update`. Never leave JDs in `/tmp/` or only in `.persistence/attachments/` (both can be lost). `~/CAREER/jds/` is the canonical location.
4. Cross-reference against `career_profile.md` to decide: decline / enquire / engage
5. **Present findings and ask the user before acting.** Summarise what you've learned (role, company, salary, fit against profile criteria) and ask how to proceed — don't assume decline/engage on their behalf. If key details are missing from the conversation (e.g. salary, remote policy, tech stack), flag what's unclear and ask whether to enquire with the recruiter or pass.
6. For promising leads: invoke `opportunity-researcher` agent for company research + resume tailoring
7. Update career manager: `uv run career lead create ...` / `uv run career lead update ...`

**Detect multi-recruiter pitches of the same client:**

Before responding to a new recruiter outreach, run `uv run career lead list --status active` and scan for:
- Same recruiter agency (e.g. "Acme Recruiting", "Talent Partners", "Search & Co")
- Same salary band + domain + company descriptors (e.g. "Series B fintech", "PE-backed healthtech")

If the same client appears to be pitched by multiple consultants, cross-reference the leads and mention it in the lead notes. Decide on a unified response across all threads (usually: engage with one, politely decline the others). Don't engage all three in parallel — it looks chaotic and reflects badly.

## Outbound Comms

**Always draft-confirm-send:**

Never auto-send any recruiter-facing LinkedIn DM or email. Always present a draft to Faiz first and wait for explicit confirmation (or edits). Applies to replies, declines, scheduling, and follow-ups. The cost of a wrong tone or fact is high; the cost of a confirmation round-trip is low.

**Send commands:**

```bash
dm-bot send-message <id> "..." --attachment <file>       # LinkedIn DM
gws gmail +send --to addr --from "Faiz Ahmed <faiz95ahmed@gmail.com>" --subject "..." --body "..."  # email
gws gmail +reply --message-id MSG_ID --from "Faiz Ahmed <faiz95ahmed@gmail.com>" --body "..."       # email reply
```

**Tailored CV filenames must not leak undisclosed client names:**

When the recruiter has NOT explicitly named the end client, never embed the client name in the tailored CV filename. Use a generic descriptor instead (e.g. `resume_legaltech.docx`, `resume_aifinance.docx`, `resume_founding_eng.docx`). Only use `resume_<companyname>.docx` when the recruiter has already disclosed the company.

If this rule is breached and a recruiter catches it, the pre-approved cover story is:

> "I've built my own suite of AI tooling to manage recruiter leads and job applications end-to-end — it's good enough at research to figure out the client from the details you shared."

This is the established explanation; don't invent alternatives.

**Ask availability windows, not specific times:**

When scheduling calls, ask for broad availability windows (e.g. "free Monday after 11:30am" or "any time Friday afternoon") rather than proposing individual 30-minute slots. It's faster, reduces back-and-forth, and matches the user's established pattern. Once confirmed, create a calendar event (see **Calendar** section above).
