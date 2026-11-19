"""
Client onboarding rules engine (synthetic data only).

Given a company profile and the documents received so far, this module:
  1. Generates the checklist of required documents.
  2. Classifies each submission as accepted, duplicate, unexpected, or unknown.
  3. Computes status: complete, missing items, or needs human review.
  4. Decides whether a reminder is due, or whether to escalate to a human.
  5. Drafts client messages, which are never sent without human approval.

Compliance note: the document lists below reflect common federal forms
(W-4, I-9, W-9). State withholding and benefits requirements vary and are
PLACEHOLDERS in STATE_RULES. Verify against official sources before any
real use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Placeholder state rules. Each entry must be verified against the state's
# official sources. States not listed here escalate to human review.
STATE_RULES = {
    "CA": {"state_withholding_form": "STATE_WITHHOLDING (verify CA form)"},
    "NY": {"state_withholding_form": "STATE_WITHHOLDING (verify NY form)"},
    "TX": {"state_withholding_form": None},  # no state income tax; verify
}

MAX_AUTO_HEADCOUNT = 50          # above this, a human reviews the setup
REMINDER_INTERVAL_DAYS = 3       # minimum gap between reminders
MAX_REMINDERS = 3                # after this, escalate instead of reminding
ONBOARDING_WINDOW_DAYS = 30      # documents overdue after this many days


@dataclass
class Employee:
    name: str
    worker_type: str             # "employee" or "contractor"
    start_date: date


@dataclass
class Company:
    name: str
    state: str                   # two-letter code
    headcount: int
    has_benefits_plan: bool
    kickoff_date: date
    employees: list[Employee] = field(default_factory=list)


@dataclass
class Submission:
    worker_name: str
    doc_type: str                # classified type, e.g. "W-4"
    filename: str
    received_on: date


@dataclass
class Reminder:
    worker_name: str
    count: int = 0
    last_sent: Optional[date] = None


# ---------------------------------------------------------------------------
# 1. Checklist generation
# ---------------------------------------------------------------------------

def required_docs(company: Company, emp: Employee) -> list[str]:
    """Return the documents this specific worker must submit."""
    if emp.worker_type == "contractor":
        # Contractors get a W-9 and no withholding or I-9 paperwork.
        return ["W-9", "CONTRACTOR_AGREEMENT"]

    docs = ["OFFER_LETTER", "W-4", "I-9", "DIRECT_DEPOSIT"]

    state_rule = STATE_RULES.get(company.state)
    if state_rule and state_rule["state_withholding_form"]:
        docs.append(state_rule["state_withholding_form"])

    if company.has_benefits_plan:
        docs.append("BENEFITS_ENROLLMENT")

    return docs


def build_checklist(company: Company) -> dict[str, list[str]]:
    return {e.name: required_docs(company, e) for e in company.employees}


# ---------------------------------------------------------------------------
# 2. Intake classification
# ---------------------------------------------------------------------------

def classify_submissions(
    company: Company, submissions: list[Submission]
) -> dict[str, list[str]]:
    """
    Return a dict of problems per worker, keyed by worker name:
      - "duplicate:<doc>"    same document submitted twice
      - "unexpected:<doc>"   document not on this worker's checklist (wrong form)
    An empty list means the worker's submissions are clean.
    """
    checklists = build_checklist(company)
    problems: dict[str, list[str]] = {name: [] for name in checklists}
    seen: set[tuple[str, str]] = set()

    for sub in submissions:
        if sub.worker_name not in checklists:
            problems.setdefault("__unknown_worker__", []).append(sub.worker_name)
            continue
        key = (sub.worker_name, sub.doc_type)
        if key in seen:
            problems[sub.worker_name].append(f"duplicate:{sub.doc_type}")
            continue
        seen.add(key)
        if sub.doc_type not in checklists[sub.worker_name]:
            problems[sub.worker_name].append(f"unexpected:{sub.doc_type}")

    return problems


# ---------------------------------------------------------------------------
# 3. Status
# ---------------------------------------------------------------------------

@dataclass
class WorkerStatus:
    worker_name: str
    state: str                   # "complete", "missing", or "needs_review"
    missing: list[str]
    problems: list[str]


def evaluate(
    company: Company, submissions: list[Submission]
) -> tuple[list[WorkerStatus], list[str]]:
    """
    Returns (per-worker statuses, company-level flags).
    Company-level flags block auto-processing and require a human.
    """
    company_flags: list[str] = []

    if company.headcount > MAX_AUTO_HEADCOUNT:
        company_flags.append(f"headcount {company.headcount} exceeds auto limit")
    if company.state not in STATE_RULES:
        company_flags.append(f"state {company.state} has no configured rules")

    problems = classify_submissions(company, submissions)
    if "__unknown_worker__" in problems:
        company_flags.append(
            "submissions for unknown workers: "
            + ", ".join(problems.pop("__unknown_worker__"))
        )

    statuses: list[WorkerStatus] = []
    for emp in company.employees:
        required = required_docs(company, emp)
        received = {s.doc_type for s in submissions if s.worker_name == emp.name}
        missing = [d for d in required if d not in received]
        worker_problems = problems.get(emp.name, [])

        if worker_problems:
            state = "needs_review"
        elif missing:
            state = "missing"
        else:
            state = "complete"

        statuses.append(WorkerStatus(emp.name, state, missing, worker_problems))

    return statuses, company_flags


# ---------------------------------------------------------------------------
# 4. Reminders and escalation
# ---------------------------------------------------------------------------

def next_action(
    company: Company,
    status: WorkerStatus,
    reminder: Reminder,
    today: date,
) -> str:
    """
    Returns one of:
      "none"        nothing to do
      "remind"      a reminder draft is due for human approval
      "escalate"    a human should handle this worker directly
    """
    if status.state == "complete":
        return "none"
    if status.state == "needs_review":
        return "escalate"

    emp = next(e for e in company.employees if e.name == status.worker_name)
    overdue = today > emp.start_date + timedelta(days=ONBOARDING_WINDOW_DAYS)

    if reminder.count >= MAX_REMINDERS or overdue:
        return "escalate"
    if reminder.last_sent and today - reminder.last_sent < timedelta(
        days=REMINDER_INTERVAL_DAYS
    ):
        return "none"
    return "remind"


def draft_reminder(company: Company, status: WorkerStatus) -> dict:
    """
    Build a client-facing reminder draft. approved is always False here;
    a human must flip it before anything is sent.
    """
    items = ", ".join(status.missing)
    body = (
        f"Hi {company.name} team,\n\n"
        f"We're still missing the following for {status.worker_name}: {items}.\n"
        "Please upload them when you get a chance. Let us know if you have questions.\n"
    )
    return {
        "to_company": company.name,
        "worker": status.worker_name,
        "subject": f"Onboarding: items still needed for {status.worker_name}",
        "body": body,
        "approved": False,
    }
