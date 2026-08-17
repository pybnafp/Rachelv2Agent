def test_first_user_is_admin(client, db):
    r = client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 201 and r.json()["role"] == "admin"


def test_second_user_is_user(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    r = client.post("/api/auth/register", json={"username": "bob", "password": "secret2"})
    assert r.json()["role"] == "user"


def test_duplicate_username_409(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert client.post("/api/auth/register", json={"username": "alice", "password": "x2"}).status_code == 409


def test_login_wrong_password_401(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert client.post("/api/auth/login", json={"username": "alice", "password": "bad"}).status_code == 401


def test_me_requires_token(client, db):
    assert client.get("/api/auth/me").status_code == 401


def test_me_roundtrip(client, db):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    tok = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"}).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["username"] == "alice"
