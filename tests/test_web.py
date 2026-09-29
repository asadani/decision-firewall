import re

from fastapi.testclient import TestClient

from decision_firewall.contracts import Payment, Proposal
from decision_firewall.providers import FixtureProvider
from decision_firewall.web import create_app


def setup_client(tmp_path):
    app = create_app(tmp_path, tmp_path / "runs")
    fw = app.state.firewall
    fw.payments.seed(
        Payment(
            payment_id="p",
            customer_id="c",
            amount_minor=250000,
            destination="card",
            duplicate_verified=True,
        )
    )
    p = Proposal(
        payment_id="p",
        customer_id="c",
        message="Refund the duplicate",
        requested_reason="duplicate",
        amount_minor=250000,
        destination="card",
    )
    rid = fw.submit(p, FixtureProvider().assess(p.message))
    fw.evaluate(rid)
    return TestClient(app), fw, rid


def test_review_browser_flow_and_duplicate(tmp_path):
    client, fw, rid = setup_client(tmp_path)
    page = client.get(f"/requests/{rid}")
    assert page.status_code == 200
    csrf = re.search('name="csrf" value="([^"]+)"', page.text).group(1)
    data = {"csrf": csrf, "revision": 1, "decision": "approve", "reason": "Verified duplicate"}
    saved = client.post(
        f"/requests/{rid}/review", data=data, headers={"origin": "http://testserver"}
    )
    assert saved.status_code == 200 and "Review saved" in saved.text
    assert fw.detail(rid)["status"] == "ALLOW_WITH_CONSTRAINTS"
    assert (
        client.post(
            f"/requests/{rid}/review", data=data, headers={"origin": "http://testserver"}
        ).status_code
        == 409
    )


def test_security_validation_and_states(tmp_path):
    client, _fw, rid = setup_client(tmp_path)
    page = client.get(f"/requests/{rid}")
    csrf = re.search('name="csrf" value="([^"]+)"', page.text).group(1)
    data = {"csrf": csrf, "revision": 1, "decision": "approve", "reason": "ok"}
    assert client.post(f"/requests/{rid}/review", data=data).status_code == 403
    assert (
        client.post(
            f"/requests/{rid}/review", data=data, headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/requests/{rid}/review", data=data, headers={"origin": "http://testserver"}
        ).status_code
        == 422
    )
    data.update(reason="valid reason", revision=99)
    stale = client.post(
        f"/requests/{rid}/review", data=data, headers={"origin": "http://testserver"}
    )
    assert stale.status_code == 409 and "valid reason" in stale.text
    assert client.get("/", headers={"host": "evil.invalid"}).status_code == 400
    assert "No matching requests" in client.get("/?q=nomatches").text
    assert "No evaluation runs yet" in client.get("/runs").text
    assert client.get("/missing").status_code == 404
    assert "Content-Security-Policy" in page.headers


def test_html_escape(tmp_path):
    client, fw, rid = setup_client(tmp_path)
    with fw.store.transaction() as db:
        import json

        row = db.execute("SELECT proposal FROM requests WHERE id=?", (rid,)).fetchone()
        p = json.loads(row[0])
        p["message"] = "<script>alert(1)</script>"
        db.execute("UPDATE requests SET proposal=? WHERE id=?", (json.dumps(p), rid))
    assert "<script>alert(1)</script>" not in client.get(f"/requests/{rid}").text


def test_csrf_requires_existing_session(tmp_path):
    client, fw, rid = setup_client(tmp_path)
    response = client.post(
        f"/requests/{rid}/review",
        data={"csrf": "missing", "revision": 1, "decision": "approve", "reason": "Approved"},
        headers={"origin": "http://testserver"},
    )
    assert response.status_code == 403
    assert fw.detail(rid)["status"] == "REQUIRE_REVIEW"
