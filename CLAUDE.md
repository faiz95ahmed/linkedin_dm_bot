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

**Workflow:**
1. `uv run dm-bot inbox --since N` — review recent conversations
2. `uv run dm-bot conversation <id>` — read a thread
3. Cross-reference against `career_profile.md` to decide: decline / enquire / engage
4. Declining: send polite message + attach untailored `resume.docx`
5. Engaging: copy `resume.json`, tailor, build DOCX, draft message, send via `dm-bot send-message <id> "..." --attachment <file>`
