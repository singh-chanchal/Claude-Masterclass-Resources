from tests.conftest import signup

URL = "/api/auth/change-password"


def login(client, password, email="jane@example.com"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_change_password_persists(client, auth):
    r = client.post(URL, headers=auth, json={"current_password": "password123", "new_password": "newpass456"})
    assert r.status_code == 204, r.text
    assert login(client, "password123").status_code == 401
    assert login(client, "newpass456").status_code == 200
    # Stateless JWTs: the token used for the change keeps working.
    assert client.get("/api/auth/me", headers=auth).status_code == 200


def test_wrong_current_password_is_400_and_unchanged(client, auth):
    r = client.post(URL, headers=auth, json={"current_password": "wrong-pass", "new_password": "newpass456"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Current password is incorrect."
    assert login(client, "password123").status_code == 200


def test_new_password_length_rule(client, auth):
    for bad in ("short", "x" * 73):
        r = client.post(URL, headers=auth, json={"current_password": "password123", "new_password": bad})
        assert r.status_code == 422
    assert login(client, "password123").status_code == 200


def test_requires_auth(client):
    r = client.post(URL, json={"current_password": "password123", "new_password": "newpass456"})
    assert r.status_code == 401


def test_only_changes_own_password(client, auth):
    signup(client, email="bob@example.com", name="Bob")
    client.post(URL, headers=auth, json={"current_password": "password123", "new_password": "newpass456"})
    assert login(client, "password123", email="bob@example.com").status_code == 200
