# Client Onboarding Workflow: Case Study

A small, working prototype of the intake-to-approval flow for a startup onboarding to benefits, payroll, and compliance. It uses synthetic data only.

## Problem

When a startup onboards, the back office has to work out which documents each worker needs, chase missing items, catch wrong or duplicate uploads, and avoid sending clients anything unreviewed. Much of this is repetitive, and the risky parts (compliance, sensitive data, client messages) need a person in the loop.

## What it does

1. **Builds a checklist per worker.** Employees need offer letter, W-4, I-9, direct deposit, and any state withholding form. Contractors need W-9 and a contractor agreement. Benefits enrollment is added only if the company has a plan.
2. **Classifies submissions.** Flags duplicates and documents that aren't on the worker's checklist (wrong form).
3. **Sets status.** Each worker is `complete`, `missing`, or `needs_review`.
4. **Decides the next action.** Reminders are rate-limited and capped. Overdue workers, repeated non-response, and any `needs_review` case escalate to a human.
5. **Drafts client messages, never sends them.** Every draft has `approved: False`. The n8n workflow routes drafts to an approval queue, not to a sending node.

## Design decisions

- **Rules are explicit and testable.** The checklist logic is plain code with 17 unit tests, not a prompt. A model can help write the rules, but the rules are what gets reviewed.
- **Escalate when unsure.** Unknown states, headcount above 50, and submissions for people not on the roster all go to a human instead of being guessed.
- **Approval is structural.** The approval step is part of the data model and the workflow, not a reminder in a comment.
- **Synthetic data only.** No real names, companies, or documents are used anywhere.

## Failure cases I tested

| Case | Expected behavior | Result |
|---|---|---|
| Employee uploads a W-9 instead of a W-4 | Flag as unexpected, route to review | Passes |
| Same W-4 uploaded twice | Flag as duplicate | Passes |
| Contractor treated as employee | Contractor gets W-9, not I-9 or W-4 | Passes |
| Benefits plan not offered | Enrollment form not requested | Passes |
| State not in the rules table | Company-level escalation | Passes |
| Headcount over 50 | Company-level escalation | Passes |
| Document for an unknown worker | Company-level flag | Passes |
| Reminder sent less than 3 days ago | No duplicate reminder | Passes |
| Third reminder with no response | Escalate, do not remind again | Passes |
| Worker past 30 days | Escalate | Passes |

Two bugs turned up while writing the tests. Both were in the tests, not the engine: one test forgot a required contractor document, and another passed the wrong argument. I fixed them and noted them here because the lesson applies to AI-generated tests too: a failing test isn't always a failing feature.

## n8n routing runs

The n8n workflow was run against sample payloads. Each run shows which branch the intake took.

| Scenario | Payload | Route | Result |
|---|---|---|---|
| Missing documents | Alex (employee) submitted only OFFER_LETTER, Sam (contractor) submitted nothing | Approval Queue (reminders) | Reminder targets: Alex is missing W-4, I-9, DIRECT_DEPOSIT, STATE_WITHHOLDING, BENEFITS_ENROLLMENT. Sam is missing CONTRACTOR_AGREEMENT. |
| Clean intake | "Clean Co" in CA, 2 workers, all 8 required documents | Ready Path | `ready: true`, no flags |
| Partial intake | "Partial Co" in TX, Alex submitted OFFER_LETTER and W-4, Sam submitted W-9 | Approval Queue (reminders) | Reminder targets: Alex is missing I-9 and DIRECT_DEPOSIT. Sam is missing CONTRACTOR_AGREEMENT. |
| Headcount and unknown worker | Headcount 60, submission from "Ghost" who is not on the roster | Human Review Queue | Both problems flagged |
| Precedence: wrong form and missing documents | "Conflict Co" in CA, Alex submitted a W-9 instead of a W-4 and has other documents missing | Human Review Queue, reminder queue skipped | Run in n8n (execution 13). Alex is `needs_review` with `unexpected:W-9`, so `needs_human_review` is true and `has_missing` is false. |

All five rows were run in n8n. To reproduce the JS checks outside n8n, run `node n8n/test_evaluate_intake.js` from the repo root. It requires Node 18 or later.


## Known gaps before real use

- **State rules are placeholders.** `STATE_RULES` lists example states with generic form names. Each state's withholding and benefits requirements must be checked against official state sources.
- **Federal form assumptions need checking.** The I-9 and W-4 requirements (who needs them, when they're due, and how they're retained) need verification against USCIS and IRS guidance. Contractor paperwork should also be checked, since misclassifying a worker is a serious compliance risk in its own right.
- **Document classification is mocked.** The prototype trusts a declared `doc_type`. A real system would need OCR or a classifier, and it would need to handle low-confidence results by escalating.
- **No storage, auth, or audit log.** A production system needs encrypted storage, access controls, and a record of every approval and sent message.
- **Reminder timing is a guess.** The 3-day interval and 30-day window are illustrative and should be set with clients.
- **The n8n JS duplicates the Python rules.** Keeping two copies in sync is a maintenance risk. The next step would be to call a single service from n8n.

## What I'd add next

- A RAG layer over mock policy documents so the workflow can answer "what do I still need to submit?" with citations, and say "I don't know" when the sources don't cover the question.
- A status view for the founders showing each company's checklist and flags.
- Tests for the n8n workflow itself, not only the Python logic.

## How AI was used

I used Claude to draft the rules engine, the test scaffolding, the n8n workflow JSON, and this write-up. I decided which documents apply to which worker types, where human approval is required, and which failures to escalate. I reviewed each generated file, ran the test suite, and fixed two failing tests. The model made two kinds of mistake: it wrote tests that assumed the wrong behavior, and it stated compliance details that I then marked for verification instead of treating as settled. Everything in the compliance section should be checked against official sources.

## Run it

```bash
python3 -m unittest test_onboarding -v
```

Requires Python 3.9 or later. No third-party packages.

To import the n8n workflow, open n8n, choose Import from File, and select `n8n/onboarding_workflow.json`. Connect Slack or Notion to the two queue nodes when you're ready. Keep the approval step between any draft and an outgoing message.
