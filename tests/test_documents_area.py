"""Documents area: categories, uploader, search and history."""
import base64

from tests.test_flow import TODAY, app, c, entry, login, mkuser, world   # noqa: F401


def up(c, h, pid, name, kind, desc=None, who="pm1"):
    return c.post(f"/projects/{pid}/documents", headers=h[who], json={"kind": kind, "filename": name, "content_b64": base64.b64encode(b"hello " + name.encode()).decode(), "description": desc})


def test_documents_search_history(c, world):
    h, pid = world["h"], world["pid"]
    a = up(c, h, pid, "tender-book.txt", "tender_book", "Original book from the client")
    assert a.status_code == 201, a.text
    assert up(c, h, pid, "minutes-kickoff.txt", "minutes").status_code == 201
    assert up(c, h, pid, "x.txt", "nonsense").status_code == 422
    lst = c.get(f"/projects/{pid}/documents", headers=h["pm1"]).json()
    assert {d["filename"] for d in lst} >= {"tender-book.txt", "minutes-kickoff.txt"} and lst[0]["uploader"]
    assert [d["filename"] for d in c.get(f"/projects/{pid}/documents?q=kickoff", headers=h["pm1"]).json()] == ["minutes-kickoff.txt"]
    assert [d["filename"] for d in c.get(f"/projects/{pid}/documents?q=client", headers=h["pm1"]).json()] == ["tender-book.txt"]
    assert [d["filename"] for d in c.get(f"/projects/{pid}/documents?kind=minutes", headers=h["pm1"]).json()] == ["minutes-kickoff.txt"]
    did = a.json()["id"]
    assert c.post(f"/projects/{pid}/documents/{did}/versions", headers=h["pm1"], json={"filename": "tender-book-v2.txt", "content_b64": base64.b64encode(b"v2").decode(), "note": "addendum"}).status_code == 201
    assert c.get(f"/projects/{pid}/documents/{did}/content", headers=h["pm1"]).status_code == 200
    hist = c.get(f"/projects/{pid}/documents/{did}/history", headers=h["pm1"]).json()
    assert [x["action"] for x in hist] == ["document.uploaded", "document.new_version", "document.downloaded"] and all(x["by"] for x in hist)
