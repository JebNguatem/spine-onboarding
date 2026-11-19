// Run with: node n8n/test_evaluate_intake.js
// Checks the Evaluate Intake logic against the routing cases. Requires Node 18+.
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "evaluate_intake.js"), "utf8");
const run = payload => new Function("$json", src)(payload)[0].json;

const base = {
  name: "Test Co", state: "CA", headcount: 30, has_benefits_plan: true,
  employees: [
    { name: "Ada", worker_type: "employee" },
    { name: "Cy", worker_type: "contractor" }
  ]
};
const adaFull = ["OFFER_LETTER", "W-4", "I-9", "DIRECT_DEPOSIT", "STATE_WITHHOLDING", "BENEFITS_ENROLLMENT"];
const subs = (list) => list.map(([worker_name, doc_type]) => ({ worker_name, doc_type }));

const cases = [
  {
    label: "all documents, clean -> Ready Path",
    payload: { company: base, submissions: subs([
      ...adaFull.map(d => ["Ada", d]), ["Cy", "W-9"], ["Cy", "CONTRACTOR_AGREEMENT"]
    ]) },
    expect: r => r.ready === true
  },
  {
    label: "missing documents only -> Approval Queue",
    payload: { company: base, submissions: subs([["Ada", "W-4"], ["Cy", "W-9"]]) },
    expect: r => r.has_missing === true && r.needs_human_review === false && r.ready === false
  },
  {
    label: "wrong form AND missing documents -> Human Review (precedence)",
    payload: { company: base, submissions: subs([["Ada", "W-9"]]) },
    expect: r => r.needs_human_review === true
  },
  {
    label: "headcount over 50 -> Human Review",
    payload: { company: { ...base, headcount: 60 }, submissions: subs([["Ada", "W-4"]]) },
    expect: r => r.needs_human_review === true && r.flags.some(f => f.includes("exceeds"))
  },
  {
    label: "submission from unknown worker -> Human Review",
    payload: { company: base, submissions: subs([["Ghost", "W-4"]]) },
    expect: r => r.needs_human_review === true && r.flags.some(f => f.includes("Ghost"))
  },
  {
    label: "duplicate document -> Human Review",
    payload: { company: base, submissions: subs([["Ada", "W-4"], ["Ada", "W-4"]]) },
    expect: r => r.needs_human_review === true
  }
];

let failed = 0;
for (const c of cases) {
  const ok = c.expect(run({ body: c.payload }));
  console.log(`${ok ? "PASS" : "FAIL"}  ${c.label}`);
  if (!ok) failed++;
}
console.log(failed ? `\n${failed} failed` : "\nall passed");
process.exit(failed ? 1 : 0);
