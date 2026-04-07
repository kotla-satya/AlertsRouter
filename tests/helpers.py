from httpx import Response


def assert_validation_error(resp: Response, *, field: str | None = None) -> None:
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert isinstance(body["error"], list)
    assert len(body["error"]) > 0
    if field:
        locs = [".".join(str(p) for p in e["loc"]) for e in body["error"]]
        assert any(field in loc for loc in locs), (
            f"expected field '{field}' in errors, got {locs}"
        )
