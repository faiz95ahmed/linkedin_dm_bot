"""CLI entry point for career lead tracking."""

from datetime import datetime, timezone
from typing import Optional

# Local timezone for display
_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


def _utc_to_local(dt: datetime) -> datetime:
    """Convert naive UTC datetime to local datetime for display."""
    return dt.replace(tzinfo=timezone.utc).astimezone(_LOCAL_TZ).replace(tzinfo=None)

import typer

from career_mgr.storage import (
    CareerDatabaseManager,
    LeadNotFoundError,
    LeadRepository,
    ProcessRepository,
)

app = typer.Typer(
    name="career",
    help="Career lead and interview process tracker",
    add_completion=False,
)
lead_app = typer.Typer(help="Manage leads")
process_app = typer.Typer(help="Manage interview process stages")
app.add_typer(lead_app, name="lead")
app.add_typer(process_app, name="process")


def _get_repos() -> tuple[CareerDatabaseManager, LeadRepository, ProcessRepository]:
    db = CareerDatabaseManager()
    db.initialize_schema()
    return db, LeadRepository(db), ProcessRepository(db)


def _resolve_lead(leads_repo: LeadRepository, slug: str, db: CareerDatabaseManager):
    """Look up a lead by slug, or exit with an error."""
    lead = leads_repo.get_by_slug(slug)
    if lead is None:
        typer.echo(f"Lead '{slug}' not found.", err=True)
        db.close()
        raise typer.Exit(code=1)
    return lead


def _resolve_process(
    leads_repo: LeadRepository,
    process_repo: ProcessRepository,
    ref: str,
    db: CareerDatabaseManager,
):
    """Resolve a '{lead-slug}.{str_id}' reference to (lead, process), or exit."""
    if "." not in ref:
        typer.echo(
            f"Invalid process ref '{ref}'. Use the form '<lead-slug>.<str_id>' "
            "(see `career lead show <slug>`).",
            err=True,
        )
        db.close()
        raise typer.Exit(code=1)
    slug, _, str_id = ref.rpartition(".")
    lead = _resolve_lead(leads_repo, slug, db)
    proc = process_repo.get_by_lead_and_str_id(lead.id, str_id)  # type: ignore[arg-type]
    if proc is None:
        typer.echo(f"No stage '{str_id}' on lead '{slug}'.", err=True)
        db.close()
        raise typer.Exit(code=1)
    return lead, proc


# =============================================================================
# Lead commands
# =============================================================================


@lead_app.command("create")
def lead_create(
    company: str = typer.Option(..., help="Company name"),
    role: str = typer.Option(..., help="Role title"),
    slug: str = typer.Option(..., help="Unique short handle for referencing this lead (e.g. 'tomoro')"),
    source: Optional[str] = typer.Option(None, help="Source: linkedin, email, offline"),
    source_ref: Optional[str] = typer.Option(None, help="Source reference (e.g. conversation ID)"),
    salary_min: Optional[int] = typer.Option(None, help="Min salary in thousands"),
    salary_max: Optional[int] = typer.Option(None, help="Max salary in thousands"),
    salary_currency: str = typer.Option("GBP", help="Salary currency"),
    notes: Optional[str] = typer.Option(None, help="Notes"),
    status: str = typer.Option("active", help="Status: active, declined, on_hold, closed, offer_accepted"),
) -> None:
    """Create a new lead."""
    from career_mgr.storage import Lead

    db, leads, _ = _get_repos()
    if leads.get_by_slug(slug) is not None:
        typer.echo(f"Slug '{slug}' is already in use. Choose another.", err=True)
        db.close()
        raise typer.Exit(code=1)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lead = leads.create(
        Lead(
            company=company,
            role_title=role,
            slug=slug,
            source=source,  # type: ignore[arg-type]
            source_ref=source_ref,
            status=status,  # type: ignore[arg-type]
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
    )
    typer.echo(f"Created lead {lead.slug}: {lead.company} — {lead.role_title}")
    db.close()


@lead_app.command("list")
def lead_list(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
) -> None:
    """List leads."""
    db, leads_repo, _ = _get_repos()
    if status:
        items = leads_repo.list_by_status(status)  # type: ignore[arg-type]
    else:
        items = leads_repo.list_all()

    if not items:
        typer.echo("No leads found.")
        db.close()
        return

    for lead in items:
        salary = ""
        if lead.salary_min or lead.salary_max:
            lo = f"{lead.salary_min}k" if lead.salary_min else "?"
            hi = f"{lead.salary_max}k" if lead.salary_max else "?"
            salary = f"  {lead.salary_currency} {lo}–{hi}"
        src = f"  [{lead.source}]" if lead.source else ""
        typer.echo(
            f"{lead.slug}  {lead.company} — {lead.role_title}  "
            f"({lead.status}){salary}{src}"
        )
    db.close()


@lead_app.command("update")
def lead_update(
    slug: str = typer.Argument(..., help="Lead slug"),
    status: Optional[str] = typer.Option(None, help="New status"),
    notes: Optional[str] = typer.Option(None, help="Notes (replaces existing)"),
    salary_min: Optional[int] = typer.Option(None, help="Min salary in thousands"),
    salary_max: Optional[int] = typer.Option(None, help="Max salary in thousands"),
    company: Optional[str] = typer.Option(None, help="Company name"),
    role: Optional[str] = typer.Option(None, help="Role title"),
) -> None:
    """Update a lead."""
    db, leads_repo, _ = _get_repos()
    lead = _resolve_lead(leads_repo, slug, db)
    fields: dict[str, object] = {}
    if status is not None:
        fields["status"] = status
    if notes is not None:
        fields["notes"] = notes
    if salary_min is not None:
        fields["salary_min"] = salary_min
    if salary_max is not None:
        fields["salary_max"] = salary_max
    if company is not None:
        fields["company"] = company
    if role is not None:
        fields["role_title"] = role

    if not fields:
        typer.echo("Nothing to update.")
        db.close()
        return

    try:
        updated = leads_repo.update(lead.id, **fields)  # type: ignore[arg-type]
        typer.echo(
            f"Updated lead {updated.slug}: {updated.company} — "
            f"{updated.role_title} ({updated.status})"
        )
    except LeadNotFoundError:
        typer.echo(f"Lead '{slug}' not found.", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@lead_app.command("show")
def lead_show(
    slug: str = typer.Argument(..., help="Lead slug"),
) -> None:
    """Show details of a single lead."""
    db, leads_repo, process_repo = _get_repos()
    lead = _resolve_lead(leads_repo, slug, db)

    typer.echo(f"{lead.slug}  {lead.company} — {lead.role_title}")
    typer.echo(f"Status: {lead.status}")
    if lead.source:
        ref = f" (ref: {lead.source_ref})" if lead.source_ref else ""
        typer.echo(f"Source: {lead.source}{ref}")
    if lead.salary_min or lead.salary_max:
        lo = f"{lead.salary_min}k" if lead.salary_min else "?"
        hi = f"{lead.salary_max}k" if lead.salary_max else "?"
        typer.echo(f"Salary: {lead.salary_currency} {lo}–{hi}")
    if lead.notes:
        typer.echo(f"Notes: {lead.notes}")
    typer.echo(f"Created: {_utc_to_local(lead.created_at):%Y-%m-%d %H:%M}")
    typer.echo(f"Updated: {_utc_to_local(lead.updated_at):%Y-%m-%d %H:%M}")

    stages = process_repo.get_stages_for_lead(lead.id)  # type: ignore[arg-type]
    if stages:
        typer.echo("\nProcess:")
        for s in stages:
            sched = f"  @ {_utc_to_local(s.scheduled_at):%Y-%m-%d %H:%M}" if s.scheduled_at else ""
            outcome = f"  -> {s.outcome}" if s.outcome else ""
            ref = f"{lead.slug}.{s.str_id}"
            typer.echo(f"  {s.sequence}. [{ref}] {s.stage} ({s.status}){sched}{outcome}")
    db.close()


# =============================================================================
# Process commands
# =============================================================================


@process_app.command("add")
def process_add(
    slug: str = typer.Argument(..., help="Lead slug"),
    stage: str = typer.Option(..., help="Stage name"),
    scheduled: Optional[str] = typer.Option(None, help="Scheduled datetime (ISO format)"),
    notes: Optional[str] = typer.Option(None, help="Notes"),
) -> None:
    """Add a process stage to a lead."""
    from career_mgr.storage import Process

    db, leads_repo, process_repo = _get_repos()
    lead = _resolve_lead(leads_repo, slug, db)

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seq = process_repo.next_sequence(lead.id)  # type: ignore[arg-type]
    scheduled_at = datetime.fromisoformat(scheduled) if scheduled else None

    proc = process_repo.create(
        Process(
            lead_id=lead.id,  # type: ignore[arg-type]
            sequence=seq,
            stage=stage,  # type: ignore[arg-type]
            scheduled_at=scheduled_at,
            notes=notes,
            created_at=now,
            updated_at=now,
        )
    )
    sched_str = f" @ {proc.scheduled_at:%Y-%m-%d %H:%M}" if proc.scheduled_at else ""
    typer.echo(
        f"Added stage {lead.slug}.{proc.str_id} (#{proc.sequence}): "
        f"{proc.stage}{sched_str}"
    )
    db.close()


@process_app.command("list")
def process_list(
    slug: str = typer.Argument(..., help="Lead slug"),
) -> None:
    """List process stages for a lead."""
    db, leads_repo, process_repo = _get_repos()
    lead = _resolve_lead(leads_repo, slug, db)

    typer.echo(f"{lead.company} — {lead.role_title}")
    stages = process_repo.get_stages_for_lead(lead.id)  # type: ignore[arg-type]
    if not stages:
        typer.echo("  No stages recorded.")
        db.close()
        return

    for s in stages:
        sched = f"  @ {s.scheduled_at:%Y-%m-%d %H:%M}" if s.scheduled_at else ""
        outcome = f"  -> {s.outcome}" if s.outcome else ""
        notes = f"  ({s.notes})" if s.notes else ""
        ref = f"{lead.slug}.{s.str_id}"
        typer.echo(f"  {s.sequence}. [{ref}] {s.stage} ({s.status}){sched}{outcome}{notes}")
    db.close()


@process_app.command("update")
def process_update(
    ref: str = typer.Argument(..., help="Process ref: <lead-slug>.<str_id>"),
    status: Optional[str] = typer.Option(None, help="New status"),
    outcome: Optional[str] = typer.Option(None, help="Outcome text"),
    notes: Optional[str] = typer.Option(None, help="Notes"),
    scheduled: Optional[str] = typer.Option(None, help="Reschedule (ISO datetime)"),
) -> None:
    """Update a process stage."""
    from career_mgr.storage import ProcessNotFoundError

    db, leads_repo, process_repo = _get_repos()
    lead, proc = _resolve_process(leads_repo, process_repo, ref, db)
    fields: dict[str, object] = {}
    if status is not None:
        fields["status"] = status
    if outcome is not None:
        fields["outcome"] = outcome
    if notes is not None:
        fields["notes"] = notes
    if scheduled is not None:
        fields["scheduled_at"] = datetime.fromisoformat(scheduled)

    if not fields:
        typer.echo("Nothing to update.")
        db.close()
        return

    try:
        updated = process_repo.update(proc.id, **fields)  # type: ignore[arg-type]
        typer.echo(
            f"Updated stage {lead.slug}.{updated.str_id} (#{updated.sequence}): "
            f"{updated.stage} ({updated.status})"
        )
    except ProcessNotFoundError:
        typer.echo(f"Process '{ref}' not found.", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


# =============================================================================
# Pipeline dashboard
# =============================================================================


@app.command("pipeline")
def pipeline() -> None:
    """Dashboard: all active leads with latest/next stage."""
    db, leads_repo, process_repo = _get_repos()
    active = leads_repo.list_by_status("active")
    if not active:
        typer.echo("No active leads.")
        db.close()
        return

    for lead in active:
        salary = ""
        if lead.salary_min or lead.salary_max:
            lo = f"{lead.salary_min}k" if lead.salary_min else "?"
            hi = f"{lead.salary_max}k" if lead.salary_max else "?"
            salary = f"  {lead.salary_currency} {lo}–{hi}"

        stages = process_repo.get_stages_for_lead(lead.id)  # type: ignore[arg-type]
        if stages:
            latest = stages[-1]
            stage_info = f"  [{latest.stage} — {latest.status}]"
            if latest.scheduled_at:
                stage_info += f" @ {latest.scheduled_at:%Y-%m-%d %H:%M}"
        else:
            stage_info = "  [no stages]"

        typer.echo(f"{lead.slug}  {lead.company} — {lead.role_title}{salary}{stage_info}")
    db.close()


def main() -> None:
    app()
