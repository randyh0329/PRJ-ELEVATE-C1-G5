import json
from pathlib import Path

golden_items = []

# 1. Policy Queries (UC-1.1: 40 prompts)
policy_topics = [
    ("bereavement", "How many days of bereavement leave do I get for immediate family?", ["5 consecutive", "paid"], ["POL-HR-LEAVE-2026"]),
    ("bereavement", "What is the bereavement policy for extended family members?", ["3", "paid"], ["POL-HR-LEAVE-2026"]),
    ("vacation_policy", "How many hours of vacation can I carry over to next year?", ["40", "carry-over"], ["POL-HR-LEAVE-2026"]),
    ("sick_leave", "How many sick days accrue each month?", ["8 hours", "month"], ["POL-HR-LEAVE-2026"]),
    ("remote_monitor", "Can I order an external monitor as a remote employee?", ["27-inch 4K", "monitor"], ["POL-HR-REMOTE-2026"]),
    ("headphones", "What is the expense limit for noise-canceling headphones?", ["$200", "two years"], ["POL-FIN-EXPENSE-2026"]),
    ("meals_per_diem", "What is the daily meal per diem for domestic travel?", ["$75", "domestic"], ["POL-FIN-EXPENSE-2026"]),
    ("international_meals", "What is the meal allowance for international business travel?", ["$100", "international"], ["POL-FIN-EXPENSE-2026"]),
    ("relocation_london", "What is the relocation allowance when transferring to London?", ["$5,000", "London"], ["POL-HR-RELOC-2026"]),
    ("code_of_conduct", "What is our company anti-harassment and equal opportunity policy?", ["prohibited", "harassment"], ["POL-HR-CONDUCT-2026"]),
]

for i in range(40):
    topic, query_base, req_kws, docs = policy_topics[i % len(policy_topics)]
    var_query = f"{query_base} (variation {i+1})" if i >= len(policy_topics) else query_base
    golden_items.append({
        "id": f"GOLDEN-POL-{i+1:03d}",
        "category": "UC-1.1_POLICY_RETRIEVAL",
        "prompt": var_query,
        "expected_agent": "pol-1.4.0",
        "expected_tools": ["agent_search.query"],
        "required_keywords": req_kws,
        "forbidden_keywords": ["404 Not Found", "undefined"]
    })

# 2. WorkWeek HCM (UC-1.2: 35 prompts)
hcm_templates = [
    ("What is my remaining vacation balance?", "get_balances", ["vacation", "remaining"]),
    ("How much sick leave do I have left?", "get_balances", ["sick", "remaining"]),
    ("Show my employee profile and manager", "get_profile", ["Alex Morgan", "Dana Scully"]),
    ("What is my registered home address in WorkWeek?", "get_profile", ["742 Evergreen Terrace"]),
    ("Update my address to 500 Enterprise Way, San Jose, CA", "update_contact", ["updated", "homeAddress"]),
    ("Update my phone number to +15559876543", "update_contact", ["updated", "phoneNumber"]),
    ("Take 2 days off for vacation starting next Monday", "submit_leave", ["LV-", "PENDING_APPROVAL"]),
]

for i in range(35):
    query_base, act, req_kws = hcm_templates[i % len(hcm_templates)]
    var_query = f"{query_base} #{i+1}" if i >= len(hcm_templates) else query_base
    golden_items.append({
        "id": f"GOLDEN-HCM-{i+1:03d}",
        "category": "UC-1.2_HCM_SELF_SERVICE",
        "prompt": var_query,
        "expected_agent": "hcm-1.4.0",
        "expected_tools": [f"ww.{act}"],
        "required_keywords": req_kws,
        "forbidden_keywords": []
    })

# 3. ServiceImmediately ITSM (UC-1.3: 35 prompts)
itsm_templates = [
    ("Check the status of incident INC123456", "get_incident", ["INC123456", "In Progress"]),
    ("What is the latest update on ticket INC123456?", "get_incident", ["INC123456"]),
    ("Open a ticket: Laptop screen flickers when connected to external display", "create_incident", ["INC", "logged"]),
    ("Create support ticket for broken VPN client gateway connection", "create_incident", ["INC"]),
    ("Add comment to INC123456: Still seeing intermittent disconnects", "post_comment", ["Comment", "INC123456"]),
]

for i in range(35):
    query_base, act, req_kws = itsm_templates[i % len(itsm_templates)]
    var_query = f"{query_base} [req {i+1}]" if i >= len(itsm_templates) else query_base
    golden_items.append({
        "id": f"GOLDEN-ITSM-{i+1:03d}",
        "category": "UC-1.3_ITSM_OPERATIONS",
        "prompt": var_query,
        "expected_agent": "itsm-1.4.0",
        "expected_tools": [f"si.{act}"],
        "required_keywords": req_kws,
        "forbidden_keywords": []
    })

# 4. Multi-System Sagas (UC-2.1 - UC-2.3: 25 prompts)
saga_templates = [
    ("I need to order a new monitor for my remote home office", "saga-1.4.0", ["Equipment Request", "27-inch 4K", "INC"]),
    ("Please order an external screen for my remote work desk", "saga-1.4.0", ["Equipment Request", "INC"]),
    ("I need to setup medical leave for upcoming surgery", "saga-1.4.0", ["Medical Leave", "LV-", "INC"]),
    ("Filing for short-term disability medical leave next month", "saga-1.4.0", ["Medical Leave", "LV-"]),
    ("I am relocating to the London office, please update address to 221B Baker Street", "saga-1.4.0", ["Relocation", "221B Baker Street", "INC"]),
]

for i in range(25):
    query_base, act, req_kws = saga_templates[i % len(saga_templates)]
    var_query = f"{query_base} ({i+1})" if i >= len(saga_templates) else query_base
    golden_items.append({
        "id": f"GOLDEN-SAGA-{i+1:03d}",
        "category": "UC-2.X_CROSS_SYSTEM_SAGA",
        "prompt": var_query,
        "expected_agent": "saga-1.4.0",
        "expected_tools": ["ww.*", "si.*"],
        "required_keywords": req_kws,
        "forbidden_keywords": []
    })

# 5. Negative & Trust Cases (15 prompts)
negative_templates = [
    ("Write a python script to calculate prime numbers", "sup-1.4.0", ["outside what I can assist with"]),
    ("Write a creative poem about artificial intelligence", "sup-1.4.0", ["outside what I can assist with"]),
    ("What is the current stock price of Apple?", "sup-1.4.0", ["outside what I can assist with"]),
    ("privacy", "gateway", ["GDPR Art. 12-14", "30 days"]),
    ("what do you know about me", "gateway", ["GDPR Art. 15", "EMP-44210"]),
    ("forget me", "gateway", ["GDPR Art. 17", "REC-RTBF-"]),
    ("stop storing my conversations", "gateway", ["GDPR Art. 7(3)", "ephemeral mode"]),
    ("I need to speak to a human representative", "gateway", ["specialist", "ESC-"]),
]

for i in range(15):
    query_base, act, req_kws = negative_templates[i % len(negative_templates)]
    golden_items.append({
        "id": f"GOLDEN-TRUST-{i+1:03d}",
        "category": "TRUST_AND_CONTAINMENT",
        "prompt": query_base,
        "expected_agent": act,
        "expected_tools": [],
        "required_keywords": req_kws,
        "forbidden_keywords": ["Traceback", "Exception"]
    })

output_file = Path(__file__).resolve().parent / "golden" / "v1.jsonl"
output_file.parent.mkdir(parents=True, exist_ok=True)
with open(output_file, "w") as f:
    for item in golden_items:
        f.write(json.dumps(item) + "\n")

print(f"Generated {len(golden_items)} golden test cases in {output_file}")
