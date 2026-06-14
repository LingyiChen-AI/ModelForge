from modelforge_common import apikey

def test_generate_and_hash():
    plaintext, prefix = apikey.generate_key()
    assert plaintext.startswith("mf_") and prefix == plaintext[:11]
    _, p2 = apikey.generate_key()
    assert prefix != p2  # distinct keys
    h = apikey.hash_key(plaintext)
    assert h != plaintext and len(h) == 64 and apikey.hash_key(plaintext) == h  # deterministic

def test_key_authorized():
    assert apikey.key_authorized(["inference"], None, "inference") is True
    assert apikey.key_authorized(["inference"], None, "badcase:report") is False   # scope mismatch
    assert apikey.key_authorized(["inference"], "2026-01-01", "inference") is False  # revoked
    assert apikey.key_authorized('["inference"]', None, "inference") is True         # JSON-string scopes (sqlite)
    assert apikey.key_authorized(None, None, "inference") is False
    assert apikey.key_authorized("not-json", None, "inference") is False
