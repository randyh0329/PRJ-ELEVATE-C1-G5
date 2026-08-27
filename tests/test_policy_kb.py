from src.policy_kb.retriever import policy_kb


def test_retrieval_bereavement():
    res = policy_kb.query("How many days of bereavement leave do I get for immediate family?")
    assert res["grounded"] is True
    assert len(res["citations"]) > 0
    assert any("POL-HR-LEAVE-2026" in c.documentTitle or "Leave" in c.documentTitle for c in res["citations"])
    assert any("Bereavement" in c.section for c in res["citations"])
    assert any("5 consecutive" in p for p in res["passages"])


def test_retrieval_home_office_monitor():
    res = policy_kb.query("Can remote employees order an external monitor?")
    assert res["grounded"] is True
    assert any("Remote" in c.documentTitle for c in res["citations"])
    assert any("27-inch 4K" in p for p in res["passages"])


def test_retrieval_headphone_expense():
    res = policy_kb.query("What is the expense limit for noise-canceling headphones?")
    assert res["grounded"] is True
    assert any("Expense" in c.documentTitle for c in res["citations"])
    assert any("$200" in p for p in res["passages"])


def test_retrieval_london_relocation():
    res = policy_kb.query("What is the relocation allowance for moving to the London office?")
    assert res["grounded"] is True
    assert any("Relocation" in c.documentTitle for c in res["citations"])
    assert any("$5,000" in p for p in res["passages"])


def test_retrieval_ungrounded_fallback():
    res = policy_kb.query("What is the quantum mechanics stock prediction for tomorrow?")
    assert res["grounded"] is False
    assert res["groundedness_score"] == 0.0
    assert "https://hr.corp.internal" in res["fallback_message"]
