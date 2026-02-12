from app.main import create_app


def _get_health_route(app):
    for route in app.routes:
        if getattr(route, "path", None) == "/health" and "GET" in getattr(
            route, "methods", set()
        ):
            return route
    raise AssertionError("Health route not registered")


def test_health_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("BRAINDRIVE_LIBRARY_PATH", str(tmp_path))
    app = create_app()

    route = _get_health_route(app)

    assert route.status_code == 200
    assert route.endpoint() == {"status": "ok"}
