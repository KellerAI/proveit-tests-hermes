from proveit_tests.findings import Finding, Severity
from proveit_tests.receipts.ledger import Ledger, build_receipt, sha256


def test_sha256_stable():
    assert sha256("abc") == sha256("abc")
    assert sha256("abc") != sha256("abd")


def test_receipt_digest_deterministic(tmp_path):
    findings = [
        Finding(kind="assert-true", message="x", severity=Severity.CRITICAL, path="t.py", line=1)
    ]
    a = build_receipt(findings, session_id="s1", mode="observe")
    b = build_receipt(findings, session_id="s1", mode="observe")
    assert a.digest == b.digest
    assert a.open_count == 1


def test_ledger_persist(tmp_path):
    led = Ledger(tmp_path)
    findings = [
        Finding(kind="skip-or-xfail", message="skipped", severity=Severity.CRITICAL, path="t.py")
    ]
    r = led.record(findings, session_id="s", mode="observe")
    led2 = Ledger(tmp_path)
    assert led2.latest() is not None
    assert led2.latest().digest == r.digest
    assert "ProveIt ledger" in led2.summary_text()
