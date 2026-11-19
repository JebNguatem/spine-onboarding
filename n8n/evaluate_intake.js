// Intake evaluation for the n8n Code node. Mirrors onboarding.py. Keep in sync.
// Input: { body: { company: {...}, submissions: [...] } } from the webhook.
// Output: one item with flags, per-worker status, and routing booleans.

const payload = $json.body ?? $json;
const company = payload.company;
const submissions = payload.submissions || [];

const STATE_RULES = { CA: "STATE_WITHHOLDING", NY: "STATE_WITHHOLDING", TX: null };
const MAX_AUTO_HEADCOUNT = 50;
const hasRule = s => Object.prototype.hasOwnProperty.call(STATE_RULES, s);

function requiredDocs(emp) {
  if (emp.worker_type === "contractor") return ["W-9", "CONTRACTOR_AGREEMENT"];
  const docs = ["OFFER_LETTER", "W-4", "I-9", "DIRECT_DEPOSIT"];
  if (hasRule(company.state) && STATE_RULES[company.state]) docs.push(STATE_RULES[company.state]);
  if (company.has_benefits_plan) docs.push("BENEFITS_ENROLLMENT");
  return docs;
}

const flags = [];
if (company.headcount > MAX_AUTO_HEADCOUNT) {
  flags.push(`Headcount ${company.headcount} exceeds the auto-processing limit of ${MAX_AUTO_HEADCOUNT}.`);
}
if (!hasRule(company.state)) {
  flags.push(`State "${company.state}" has no configured rules.`);
}

const employees = company.employees || [];
const names = new Set(employees.map(e => e.name));
const seen = new Set();
const problems = Object.fromEntries(employees.map(e => [e.name, []]));
const unknown = [];

for (const s of submissions) {
  if (!names.has(s.worker_name)) { unknown.push(s.worker_name); continue; }
  const key = s.worker_name + "|" + s.doc_type;
  if (seen.has(key)) { problems[s.worker_name].push("duplicate:" + s.doc_type); continue; }
  seen.add(key);
  const emp = employees.find(e => e.name === s.worker_name);
  if (!requiredDocs(emp).includes(s.doc_type)) problems[s.worker_name].push("unexpected:" + s.doc_type);
}
if (unknown.length) {
  flags.push("Submissions for workers not on the roster: " + [...new Set(unknown)].join(", ") + ".");
}

const workers = employees.map(emp => {
  const required = requiredDocs(emp);
  const received = new Set(submissions.filter(s => s.worker_name === emp.name).map(s => s.doc_type));
  const missing = required.filter(d => !received.has(d));
  const probs = problems[emp.name];
  const state = probs.length ? "needs_review" : missing.length ? "missing" : "complete";
  return { name: emp.name, state, missing, problems: probs };
});

const needsHumanReview = flags.length > 0 || workers.some(w => w.state === "needs_review");
const reminderTargets = workers.filter(w => w.state === "missing");

return [{
  json: {
    company: company.name,
    flags,
    workers,
    needs_human_review: needsHumanReview,
    has_missing: reminderTargets.length > 0,
    reminder_targets: reminderTargets.map(w => ({ worker: w.name, missing: w.missing })),
    ready: !needsHumanReview && reminderTargets.length === 0
  }
}];
