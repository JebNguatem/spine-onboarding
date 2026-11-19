"""Run with: python -m unittest test_onboarding -v   (standard library only)"""

import unittest
from datetime import date

from onboarding import (
    Company,
    Employee,
    Reminder,
    Submission,
    draft_reminder,
    evaluate,
    next_action,
    required_docs,
)


def make_company(**overrides):
    base = dict(
        name="Test Co",
        state="CA",
        headcount=30,
        has_benefits_plan=True,
        kickoff_date=date(2026, 11, 1),
        employees=[
            Employee("Emp One", "employee", date(2026, 11, 3)),
            Employee("Con One", "contractor", date(2026, 11, 3)),
        ],
    )
    base.update(overrides)
    return Company(**base)


def sub(worker, doc, day=date(2026, 11, 4)):
    return Submission(worker, doc, f"{doc}.pdf", day)


class ChecklistTests(unittest.TestCase):
    def test_employee_gets_withholding_i9_and_benefits(self):
        docs = required_docs(make_company(), make_company().employees[0])
        self.assertIn("I-9", docs)
        self.assertIn("W-4", docs)
        self.assertIn("BENEFITS_ENROLLMENT", docs)

    def test_contractor_gets_w9_not_i9(self):
        c = make_company()
        docs = required_docs(c, c.employees[1])
        self.assertIn("W-9", docs)
        self.assertNotIn("I-9", docs)
        self.assertNotIn("W-4", docs)

    def test_no_benefits_plan_drops_enrollment_form(self):
        c = make_company(has_benefits_plan=False)
        self.assertNotIn("BENEFITS_ENROLLMENT", required_docs(c, c.employees[0]))


class IntakeTests(unittest.TestCase):
    def test_wrong_form_is_flagged_for_review(self):
        c = make_company()
        statuses, _ = evaluate(c, [sub("Emp One", "W-9")])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        self.assertEqual(emp.state, "needs_review")
        self.assertIn("unexpected:W-9", emp.problems)

    def test_duplicate_upload_is_flagged(self):
        c = make_company()
        statuses, _ = evaluate(c, [sub("Emp One", "W-4"), sub("Emp One", "W-4")])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        self.assertIn("duplicate:W-4", emp.problems)

    def test_submission_for_unknown_worker_is_company_flag(self):
        c = make_company()
        _, flags = evaluate(c, [sub("Nobody Here", "W-4")])
        self.assertTrue(any("unknown workers" in f for f in flags))

    def test_missing_items_are_listed(self):
        c = make_company()
        statuses, _ = evaluate(c, [sub("Emp One", "W-4")])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        self.assertEqual(emp.state, "missing")
        self.assertIn("I-9", emp.missing)
        self.assertNotIn("W-4", emp.missing)

    def test_complete_worker_has_no_missing_items(self):
        c = make_company()
        subs = [sub("Con One", "W-9"), sub("Con One", "CONTRACTOR_AGREEMENT")]
        statuses, _ = evaluate(c, subs)
        con = next(s for s in statuses if s.worker_name == "Con One")
        self.assertEqual(con.state, "complete")


class CompanyFlagTests(unittest.TestCase):
    def test_unknown_state_escalates(self):
        c = make_company(state="ZZ")
        _, flags = evaluate(c, [])
        self.assertTrue(any("no configured rules" in f for f in flags))

    def test_large_headcount_escalates(self):
        c = make_company(headcount=120)
        _, flags = evaluate(c, [])
        self.assertTrue(any("exceeds auto limit" in f for f in flags))


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.c = make_company()
        self.today = date(2026, 11, 10)

    def test_complete_worker_needs_no_action(self):
        status = type("S", (), {"state": "complete", "worker_name": "Con One"})
        self.assertEqual(next_action(self.c, status, Reminder("Con One"), self.today), "none")

    def test_needs_review_escalates_instead_of_reminding(self):
        statuses, _ = evaluate(self.c, [sub("Emp One", "W-9")])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        self.assertEqual(next_action(self.c, emp, Reminder("Emp One"), self.today), "escalate")

    def test_missing_worker_gets_reminder(self):
        statuses, _ = evaluate(self.c, [])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        self.assertEqual(next_action(self.c, emp, Reminder("Emp One"), self.today), "remind")

    def test_reminders_are_rate_limited(self):
        statuses, _ = evaluate(self.c, [])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        recent = Reminder("Emp One", count=1, last_sent=date(2026, 11, 9))
        self.assertEqual(next_action(self.c, emp, recent, self.today), "none")

    def test_too_many_reminders_escalates(self):
        statuses, _ = evaluate(self.c, [])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        exhausted = Reminder("Emp One", count=3, last_sent=date(2026, 10, 1))
        self.assertEqual(next_action(self.c, emp, exhausted, self.today), "escalate")

    def test_overdue_worker_escalates(self):
        statuses, _ = evaluate(self.c, [])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        late = date(2026, 12, 20)
        self.assertEqual(next_action(self.c, emp, Reminder("Emp One"), late), "escalate")

    def test_reminder_drafts_are_never_pre_approved(self):
        statuses, _ = evaluate(self.c, [])
        emp = next(s for s in statuses if s.worker_name == "Emp One")
        draft = draft_reminder(self.c, emp)
        self.assertFalse(draft["approved"])
        self.assertIn("I-9", draft["body"])


if __name__ == "__main__":
    unittest.main()
