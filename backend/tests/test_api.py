from datetime import date, datetime, timedelta

from tests.conftest import JD, RESUME, signup


# ---- auth ----
def test_signup_login_me(client):
    signup(client, "a@example.com")
    r = client.post("/api/auth/login", json={"email": "A@example.com", "password": "password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "a@example.com"


def test_duplicate_email_and_bad_login(client):
    signup(client, "a@example.com")
    r = client.post("/api/auth/signup", json={"name": "X", "email": "a@example.com", "password": "password123"})
    assert r.status_code == 400
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_requires_auth(client):
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_password_is_hashed(client):
    signup(client, "a@example.com")
    from app.models import User
    db = client.session_factory()
    user = db.query(User).one()
    assert user.password_hash.startswith("$2") and "password123" not in user.password_hash


# ---- resumes ----
def test_one_active_resume(client, auth):
    r1 = client.post("/api/resumes/text", json={"content": RESUME}, headers=auth).json()
    r2 = client.post("/api/resumes/text", json={"content": RESUME + " Also Go."}, headers=auth).json()
    assert client.get("/api/resumes/active", headers=auth).json()["id"] == r2["id"]
    client.post(f"/api/resumes/{r1['id']}/activate", headers=auth)
    resumes = client.get("/api/resumes", headers=auth).json()
    assert [r["id"] for r in resumes if r["is_active"]] == [r1["id"]]


def test_upload_rejects_non_pdf(client, auth):
    r = client.post("/api/resumes/upload", files={"file": ("cv.txt", b"hello", "text/plain")}, headers=auth)
    assert r.status_code == 400


# ---- AI match ----
def test_match_requires_resume(client, auth):
    r = client.post("/api/matches", json={"job_description": JD}, headers=auth)
    assert r.status_code == 400


def test_match_and_save_as_wishlist(client, auth):
    client.post("/api/resumes/text", json={"content": RESUME}, headers=auth)
    m = client.post("/api/matches", json={"job_description": JD}, headers=auth)
    assert m.status_code == 201, m.text
    m = m.json()
    assert 0 <= m["fit_score"] <= 100
    assert "Kubernetes" in m["missing_skills"]
    assert len(m["suggested_bullets"]) == 3

    a = client.post(f"/api/matches/{m['id']}/save", json={"company": "Acme", "role": "Backend Engineer"}, headers=auth)
    assert a.status_code == 201
    assert a.json()["stage"] == "WISHLIST" and a.json()["match_id"] == m["id"]
    again = client.post(f"/api/matches/{m['id']}/save", json={"company": "Acme", "role": "BE"}, headers=auth)
    assert again.status_code == 400
    history = client.get("/api/matches", headers=auth).json()
    assert history[0]["application_id"] == a.json()["id"]


def test_ai_error_maps_to_502(client, auth):
    from app.ai.client import AIError
    from app.deps import get_ai

    class Broken:
        def match_resume(self, *_):
            raise AIError("The AI service is busy right now.")

    client.app.dependency_overrides[get_ai] = Broken
    client.post("/api/resumes/text", json={"content": RESUME}, headers=auth)
    r = client.post("/api/matches", json={"job_description": JD}, headers=auth)
    assert r.status_code == 502 and "busy" in r.json()["detail"]


# ---- pipeline ----
def _new_app(client, auth, **kw):
    body = {"company": "Acme", "role": "Engineer", **kw}
    r = client.post("/api/applications", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def test_stage_change_sets_applied_date(client, auth):
    a = _new_app(client, auth)
    assert a["stage"] == "WISHLIST" and a["applied_date"] is None
    r = client.patch(f"/api/applications/{a['id']}/stage", json={"stage": "APPLIED"}, headers=auth).json()
    assert r["stage"] == "APPLIED" and r["applied_date"] == date.today().isoformat()
    bad = client.patch(f"/api/applications/{a['id']}/stage", json={"stage": "NOPE"}, headers=auth)
    assert bad.status_code == 422


def test_update_fields(client, auth):
    a = _new_app(client, auth)
    r = client.patch(f"/api/applications/{a['id']}", json={"notes": "Referral from Sam", "job_url": ""}, headers=auth)
    assert r.json()["notes"] == "Referral from Sam" and r.json()["job_url"] is None


def test_interview_moves_to_interview_and_cascade_delete(client, auth):
    a = _new_app(client, auth, stage="APPLIED")
    when = (datetime.now() + timedelta(hours=2)).isoformat()
    i = client.post(f"/api/applications/{a['id']}/interviews", json={"scheduled_at": when, "round": "HR"}, headers=auth)
    assert i.status_code == 201
    full = client.get(f"/api/applications/{a['id']}", headers=auth).json()
    assert full["stage"] == "INTERVIEW" and len(full["interviews"]) == 1

    assert client.delete(f"/api/applications/{a['id']}", headers=auth).status_code == 204
    from app.models import Interview
    assert client.session_factory().query(Interview).count() == 0


def test_users_cannot_see_each_others_data(client, auth):
    a = _new_app(client, auth)
    other = signup(client, "bob@example.com", "Bob")
    assert client.get("/api/applications", headers=other).json() == []
    assert client.get(f"/api/applications/{a['id']}", headers=other).status_code == 404
    assert client.patch(f"/api/applications/{a['id']}/stage", json={"stage": "OFFER"}, headers=other).status_code == 404
    assert client.delete(f"/api/applications/{a['id']}", headers=other).status_code == 404


# ---- dashboard ----
def test_dashboard_metrics(client, auth):
    _new_app(client, auth)                                   # wishlist, not sent
    applied = _new_app(client, auth, stage="APPLIED")        # sent, no reply
    _new_app(client, auth, stage="OFFER")                    # sent, replied
    rej = _new_app(client, auth, stage="APPLIED")
    client.patch(f"/api/applications/{rej['id']}/stage", json={"stage": "REJECTED"}, headers=auth)  # sent, replied
    soon = datetime.now() + timedelta(minutes=30)
    client.post(f"/api/applications/{applied['id']}/interviews",
                json={"scheduled_at": soon.isoformat(), "round": "Technical"}, headers=auth)

    d = client.get("/api/dashboard", headers=auth).json()
    assert d["total_applications"] == 4
    assert d["by_stage"] == {"WISHLIST": 1, "APPLIED": 0, "INTERVIEW": 1, "OFFER": 1, "REJECTED": 1}
    assert d["applications_sent"] == 3
    assert d["applications_with_response"] == 3
    assert d["response_rate"] == 100.0
    assert d["upcoming_interviews"][0]["round"] == "Technical"


def test_dashboard_empty(client, auth):
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["total_applications"] == 0 and d["response_rate"] is None


def test_week_bounds():
    from app.services.dashboard_service import week_bounds
    assert week_bounds(date(2026, 11, 14)) == (date(2026, 11, 9), date(2026, 11, 15))
