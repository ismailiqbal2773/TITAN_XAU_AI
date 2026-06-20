"""Tests for Observability + API + Main"""
import pytest
import asyncio
from titan.observability import MetricsRegistry, AlertManager, setup_logging
from titan.api.server import create_app, ControlRequest


class TestMetricsRegistry:
    def test_export_returns_string(self):
        reg = MetricsRegistry()
        output = reg.export()
        assert isinstance(output, str)
        assert "titan_" in output

    def test_system_status_gauge(self):
        reg = MetricsRegistry()
        reg.system_status.set(0)  # GREEN
        output = reg.export()
        assert "titan_system_status" in output

    def test_weighting_gauge_with_labels(self):
        reg = MetricsRegistry()
        reg.weighting_weights.labels(model_id="xgboost").set(0.35)
        output = reg.export()
        assert "xgboost" in output

    def test_uptime_updates(self):
        reg = MetricsRegistry()
        reg.update_uptime()
        output = reg.export()
        assert "titan_uptime_seconds" in output


class TestAlertManager:
    @pytest.mark.asyncio
    async def test_send_alert_p1(self):
        am = AlertManager()
        await am.send_alert("P1", "Test Alert", "Critical issue")
        assert am.alert_count == 1

    @pytest.mark.asyncio
    async def test_send_multiple_alerts(self):
        am = AlertManager()
        await am.send_alert("P1", "Alert 1", "msg1")
        await am.send_alert("P2", "Alert 2", "msg2")
        await am.send_alert("P3", "Alert 3", "msg3")
        assert am.alert_count == 3
        assert len(am.recent_alerts) == 3

    @pytest.mark.asyncio
    async def test_alerts_degrade_without_webhooks(self):
        """Alerts should work even without webhook URLs."""
        am = AlertManager(pagerduty_webhook="", slack_webhook="")
        await am.send_alert("P1", "Test", "No webhooks configured")
        assert am.alert_count == 1  # Logged, not crashed


class TestSetupLogging:
    def test_setup_logging_no_crash(self):
        setup_logging(level="INFO", json_output=False)
        setup_logging(level="DEBUG", json_output=True)


class TestAPI:
    @pytest.fixture
    def app(self):
        return create_app()

    def test_health_endpoint(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data

    def test_health_live(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_metrics_endpoint(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_status_endpoint(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "ceo_status" in data
        assert "timestamp" in data

    def test_weights_endpoint(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/weights")
        assert response.status_code == 200

    def test_positions_endpoint(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.get("/api/positions")
        assert response.status_code == 200

    def test_control_unknown_action(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post("/api/control", json={"action": "unknown"})
        assert response.status_code == 400

    def test_control_halt(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        response = client.post("/api/control", json={"action": "halt"})
        assert response.status_code == 200


class TestMainOrchestrator:
    def test_import(self):
        """Main module should be importable."""
        from titan.main import TitanSystem
        assert TitanSystem is not None

    def test_config_loading(self, tmp_path):
        """Config should load from YAML."""
        import yaml
        config = {
            "system": {"name": "TITAN", "log_level": "INFO"},
            "database": {"sqlite_path": str(tmp_path / "test.db")},
        }
        config_path = tmp_path / "titan.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        from titan.main import TitanSystem
        system = TitanSystem(str(config_path))
        assert system._config["system"]["name"] == "TITAN"
