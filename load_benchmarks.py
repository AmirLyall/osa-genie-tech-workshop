# Databricks notebook source
# MAGIC %md
# MAGIC # NC OSA Genie Workshop (technical): load the benchmark questions
# MAGIC
# MAGIC Adds the workshop's 10 poorly worded benchmark questions, each with a reference SQL answer, to **your own** Genie Agent.
# MAGIC
# MAGIC **How to run:** paste your agent's URL into the **Agent URL or ID** box at the top of the notebook, then **Run all**. It takes a few seconds.
# MAGIC The notebook reads which catalog and schema your agent's tables are in, and points every reference answer at those same tables.
# MAGIC
# MAGIC Re-running is safe. Workshop questions already in the agent are updated to match your tables, and nothing else in the agent changes.
# MAGIC You need **Can Manage** or **Can Edit** on the agent. You get Can Manage automatically on agents you create.

# COMMAND ----------

# Paste your agent's URL in the box at the top of the notebook, or between the quotes here.
# A value in the box wins; this is used when the box is empty.
DEFAULT_AGENT = ""  # your agent's URL or ID

# Argument order is name, default value, label.
dbutils.widgets.text("agent", DEFAULT_AGENT, "Agent URL or ID")

import re
# Fall back to the default, because a box that already exists keeps its old value when the cell is edited and re-run.
AGENT = dbutils.widgets.get("agent").strip() or DEFAULT_AGENT.strip()
if not AGENT:
    raise ValueError("Paste your agent's URL into the 'Agent URL or ID' box at the top of the notebook (or DEFAULT_AGENT in this cell), then Run all again.")
# Accept a full URL such as .../genie/rooms/<id>?o=123 or just the ID.
match = re.search(r"([0-9a-f]{32})", AGENT)
if not match:
    raise ValueError("Couldn't find an agent ID. Paste the agent's URL from your browser address bar.")
SPACE_ID = match.group(1)

# COMMAND ----------

import json, uuid
from databricks.sdk import WorkspaceClient

api = WorkspaceClient().api_client
space = api.do("GET", f"/api/2.0/genie/spaces/{SPACE_ID}", query={"include_serialized_space": "true"})
config = json.loads(space["serialized_space"])

# Find the workshop tables in the agent, so the reference answers query the same tables the agent uses.
tables = [t["identifier"] for t in config.get("data_sources", {}).get("tables", [])]
found = [t.rsplit(".", 1)[0] for t in tables if t.rsplit(".", 1)[-1].strip("`") == "transactions"]
if not found:
    raise ValueError("This agent has no 'transactions' table. Add the six workshop tables to the agent first, then Run all again.")
CATALOG, SCHEMA = [p.strip("`") for p in found[0].split(".", 1)]
S = f"`{CATALOG}`.`{SCHEMA}`"
print(f"Agent  : {space.get('title')} ({SPACE_ID})\nTables : {CATALOG}.{SCHEMA}")

# COMMAND ----------

BENCHMARKS = [
("How much did we spend last quarter?",
f"""SELECT ROUND(SUM(amount), 2) AS total_spend
FROM {S}.transactions
WHERE fiscal_year = 2026 AND fiscal_quarter = 'Q4'"""),
("Which agencies have bad receipt compliance?",
f"""SELECT a.agency_code, a.agency_name,
       ROUND(100 * AVG(CASE WHEN t.receipt_attached THEN 1 ELSE 0 END), 1) AS receipt_compliance_pct
FROM {S}.transactions t JOIN {S}.agencies a ON t.agency_code = a.agency_code
WHERE t.fiscal_year = 2026
GROUP BY a.agency_code, a.agency_name
HAVING ROUND(100 * AVG(CASE WHEN t.receipt_attached THEN 1 ELSE 0 END), 1) < 90
ORDER BY receipt_compliance_pct ASC"""),
("What's our receipt rate?",
f"""SELECT ROUND(100 * AVG(CASE WHEN receipt_attached THEN 1 ELSE 0 END), 1) AS receipt_compliance_pct
FROM {S}.transactions
WHERE fiscal_year = 2026"""),
("How many statements were late?",
f"""SELECT COUNT(*) AS late_statements
FROM {S}.monthly_statements
WHERE (reconciled AND days_to_reconcile > 30)
   OR (NOT reconciled AND DATEDIFF(DATE'2026-06-30', statement_date) > 30)"""),
("How many split purchases were there?",
f"""SELECT COUNT(*) AS split_purchase_groups FROM (
  SELECT t.card_id
  FROM {S}.transactions t JOIN {S}.cardholders c ON t.card_id = c.card_id
  GROUP BY t.card_id, t.merchant_name, t.transaction_date, c.single_purchase_limit
  HAVING COUNT(*) >= 2 AND MAX(t.amount) <= c.single_purchase_limit AND SUM(t.amount) > c.single_purchase_limit
)"""),
("Who kept spending after they left?",
f"""SELECT c.card_id, c.cardholder_name, c.agency_code, c.termination_date,
       COUNT(*) AS purchases_after_termination, ROUND(SUM(t.amount), 2) AS total_after_termination
FROM {S}.transactions t JOIN {S}.cardholders c ON t.card_id = c.card_id
WHERE c.termination_date IS NOT NULL AND t.transaction_date > c.termination_date
GROUP BY c.card_id, c.cardholder_name, c.agency_code, c.termination_date
ORDER BY total_after_termination DESC"""),
("Total spend by department FY26",
f"""SELECT a.agency_name, ROUND(SUM(t.amount), 2) AS total_spend
FROM {S}.transactions t JOIN {S}.agencies a ON t.agency_code = a.agency_code
WHERE t.fiscal_year = 2026
GROUP BY a.agency_name
ORDER BY total_spend DESC"""),
("Which cards are dormant?",
f"""SELECT COUNT(*) AS dormant_cards
FROM {S}.cardholders c
WHERE c.card_status = 'Active'
  AND NOT EXISTS (SELECT 1 FROM {S}.transactions t
                  WHERE t.card_id = c.card_id AND t.transaction_date > DATE'2026-04-01')"""),
("Who are our big spenders?",
f"""SELECT c.card_id, c.cardholder_name, c.agency_code, ROUND(SUM(t.amount), 2) AS fy2026_spend
FROM {S}.transactions t JOIN {S}.cardholders c ON t.card_id = c.card_id
WHERE t.fiscal_year = 2026
GROUP BY c.card_id, c.cardholder_name, c.agency_code
ORDER BY fy2026_spend DESC
LIMIT 10"""),
("Purchases at places we don't allow this year",
f"""SELECT COUNT(*) AS blocked_purchases, ROUND(SUM(t.amount), 2) AS blocked_dollars
FROM {S}.transactions t JOIN {S}.merchant_categories m ON t.mcc = m.mcc
WHERE m.is_blocked AND t.fiscal_year = 2026"""),
]

# COMMAND ----------

def lines(text):  # the Genie API stores long text as a list of newline-terminated lines
    parts = text.strip("\n").split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]

benchmarks = config.setdefault("benchmarks", {}).setdefault("questions", [])
by_question = {"".join(b.get("question", [])).strip().lower(): b for b in benchmarks}
added = updated = 0
for question, sql in BENCHMARKS:
    answer = [{"format": "SQL", "content": lines(sql)}]
    current = by_question.get(question.lower())
    if current:
        # Already loaded: refresh the reference answer so it points at this agent's tables.
        if current.get("answer") != answer:
            current["answer"] = answer
            updated += 1
        continue
    benchmarks.append({
        # stable ID per agent and question, so re-runs never create duplicates
        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"osa-genie-tech/{SPACE_ID}/{question}").hex,
        "question": [question],
        "answer": answer,
    })
    added += 1
benchmarks.sort(key=lambda b: b["id"])

if added or updated:
    # Send the whole configuration back unchanged except for the workshop benchmarks.
    api.do("PATCH", f"/api/2.0/genie/spaces/{SPACE_ID}", body={"serialized_space": json.dumps(config)})
print(f"Added {added} and updated {updated} benchmark question(s). The agent now has {len(benchmarks)}.")
print("Open your agent, click Benchmark at the top, open the Questions tab, and click Run all benchmarks.")
