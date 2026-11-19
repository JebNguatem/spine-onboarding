# Client Onboarding Workflow (Prototype)

A small prototype of the intake-to-approval flow for a startup onboarding to benefits, payroll, and compliance. It checks what each worker needs, flags problems a person should review, and keeps every client message behind human approval.

**All companies, names, and documents are synthetic.** Nothing here sends email or touches real data.

- **Live demo:** https://jebnguatem.github.io/spine-onboarding/demo/ *(enable GitHub Pages first; see below)*
- **Case study:** [CASE_STUDY.md](CASE_STUDY.md) covers design decisions, failure cases, known gaps, and how AI was used.

> **Compliance caveat:** The state rules and form lists are placeholders for demonstration. They are not verified legal guidance. Federal forms (W-4, I-9, W-9) and each state's withholding and benefits requirements must be checked against official sources before any real use.

## What's here

| Path | Contents |
|---|---|
| `onboarding.py` | Rules engine: checklists, submission checks, status, reminders, drafts |
| `test_onboarding.py` | 17 unit tests for the Python engine |
| `n8n/onboarding_workflow.json` | n8n workflow with three routes: human review, approval queue, ready path |
| `n8n/evaluate_intake.js` | Evaluation logic used by the n8n Code node |
| `n8n/test_evaluate_intake.js` | Routing tests for the JS logic, runnable without n8n |
| `data/synthetic_companies.json` | Fake companies and submissions, including edge cases |
| `data/sample_webhook_payload.json` | Sample request for testing the n8n webhook |
| `data/precedence_payload.json` | Worker with a wrong form and missing documents; should go to human review |
| `demo/index.html` | Single-file browser demo. No install needed |

## Run it

**Python tests** (standard library only, Python 3.9+):

```bash
python3 -m unittest test_onboarding -v
```

**Routing tests** (Node 18+):

```bash
node n8n/test_evaluate_intake.js
```

**Demo:** open `demo/index.html` in a browser, then click **Load synthetic example**.

**n8n workflow:**

1. In n8n, choose Workflows → Import from File and select `n8n/onboarding_workflow.json`.
2. Activate the workflow.
3. POST `data/sample_webhook_payload.json` to the webhook path `/onboarding-intake`.

## Routing

| Intake | Route |
|---|---|
| Wrong form, duplicate, unknown worker, unknown state, or headcount over 50 | Human Review Queue |
| Clean, with documents still missing | Approval Queue (reminders). Drafts only, never sent automatically |
| Clean and complete | Ready Path |

Worker problems take precedence over missing documents. An intake with a wrong form goes to human review even if other documents are also missing.

## Verification status

- Python engine: 17 tests pass.
- Routing logic: 6 cases pass with `test_evaluate_intake.js`.
- n8n workflow: all five routing scenarios, including the precedence case (wrong form plus missing documents), were run in n8n. See the table in `CASE_STUDY.md`.

## Known gaps

- The n8n JavaScript duplicates the Python rules and must be kept in sync.
- Human review, approval, and ready queues are placeholders. Connect Slack, email, or Notion before real use, and keep an approval step before any outgoing message.
- Document classification trusts the declared document type. Real intake needs OCR or a classifier.
- No storage, authentication, or audit log.

## Enable the demo on GitHub Pages

Settings → Pages → Deploy from a branch → `main` → `/ (root)`. The demo will be at the URL above.
