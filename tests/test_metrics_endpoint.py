def test_metrics_endpoint_returns_200(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_content_type_is_prometheus_format(client):
    resp = client.get("/metrics")
    content_type = resp.headers.get("Content-Type", "")
    assert "text/plain" in content_type
    assert "version=" in content_type


def test_metrics_body_contains_default_series(client):
    resp = client.get("/metrics")
    body = resp.get_data(as_text=True)
    assert "flask_exporter_info" in body
