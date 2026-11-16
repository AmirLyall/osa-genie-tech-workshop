# Databricks notebook source
# MAGIC %md
# MAGIC # NC OSA Genie Workshop (technical): load the benchmark questions
# MAGIC
# MAGIC Adds the workshop's 10 worst-practice benchmark questions, each with a reference SQL answer, to **your own** Genie Agent.
# MAGIC
# MAGIC **How to run:** paste your agent's URL or ID into `agent`, check `catalog` and `schema` point at the workshop tables, then **Run all**.
# MAGIC It takes a few seconds. Re-running is safe: questions already in the agent are skipped, and nothing else in the agent changes.
# MAGIC
# MAGIC You need **Can Manage** or **Can Edit** on the agent. You get Can Manage automatically on agents you create.

# COMMAND ----------

dbutils.widgets.text("agent", "", "Your agent URL or ID (required)")
dbutils.widgets.text("catalog", "", "Catalog of the workshop tables (required)")
dbutils.widgets.text("schema", "osa_pcard_review", "Schema of the workshop tables")

import re
AGENT = dbutils.widgets.get("agent").strip()
CATALOG = dbutils.widgets.get("catalog").strip()
SCHEMA = dbutils.widgets.get("schema").strip() or "osa_pcard_review"
if not AGENT or not CATALOG:
    raise ValueError("Fill in the 'agent' and 'catalog' widgets, then Run all again.")
# Accept a full URL such as .../genie/rooms/<id>?o=123 or just the ID.
match = re.search(r"([0-9a-f]{32})", AGENT)
if not match:
    raise ValueError("Couldn't find an agent ID in the 'agent' widget. Paste the agent's URL from your browser.")
SPACE_ID = match.group(1)
S = f"`{CATALOG}`.`{SCHEMA}`"
print(f"Agent  : {SPACE_ID}\nTables : {CATALOG}.{SCHEMA}")

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

import json, uuid
from databricks.sdk import WorkspaceClient

api = WorkspaceClient().api_client

def lines(text):  # the Genie API stores long text as a list of newline-terminated lines
    parts = text.strip("\n").split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]

space = api.do("GET", f"/api/2.0/genie/spaces/{SPACE_ID}", query={"include_serialized_space": "true"})
config = json.loads(space["serialized_space"])
print(f"Agent  : {space.get('title')}")

benchmarks = config.setdefault("benchmarks", {}).setdefault("questions", [])
existing = {"".join(b.get("question", [])).strip().lower() for b in benchmarks}
added = 0
for question, sql in BENCHMARKS:
    if question.lower() in existing:
        continue
    benchmarks.append({
        # stable ID per agent and question, so re-runs never create duplicates
        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"osa-genie-tech/{SPACE_ID}/{question}").hex,
        "question": [question],
        "answer": [{"format": "SQL", "content": lines(sql)}],
    })
    added += 1
benchmarks.sort(key=lambda b: b["id"])

if added:
    # Send the whole configuration back unchanged except for the new benchmarks.
    api.do("PATCH", f"/api/2.0/genie/spaces/{SPACE_ID}", body={"serialized_space": json.dumps(config)})
print(f"Added {added} benchmark question(s). The agent now has {len(benchmarks)}.")
print("Open your agent, click Benchmarks, and click Run benchmarks.")
