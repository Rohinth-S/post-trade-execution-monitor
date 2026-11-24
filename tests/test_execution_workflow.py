from datetime import timedelta

from fastapi.testclient import TestClient
import pytest

from post_trade.api import create_app
from post_trade.execution import build_execution_report
from post_trade.fixtures import demo_batch


def test_replay_cutoff_and_execution_attribution():
    batch = demo_batch()
    early = build_execution_report(batch, as_of=batch.orders[0].sent_at + timedelta(milliseconds=500))
    assert len(early["orders"]) == 1 and early["orders"][0]["state"] == "partial"
    report = build_execution_report(batch)
    order = report["orders"][0]
    assert order["state"] == "filled" and order["vwap_usd"] == pytest.approx(2003.8)
    assert order["execution_pnl_usd"] == pytest.approx(-6.5)
    assert report["orders"][1]["slippage_bps"] < 0
    assert report["orders"][3]["execution_pnl_usd"] == pytest.approx(-8.7)
    assert report["summary"]["states"] == {"filled": 2, "partial": 1, "failed": 1, "missing": 1, "overfilled": 1}
    assert report["by_symbol"]["ETH"]["position_qty"] == pytest.approx(0.6)


def test_api_is_idempotent_and_rolls_back_batch_on_conflict(tmp_path):
    batch = demo_batch()
    payload = batch.model_dump(mode="json")
    with TestClient(create_app(tmp_path / "orders.db")) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/v1/events", json=payload).json()["inserted_fills"] == 6
        assert client.post("/v1/events", json=payload).json()["idempotent_retries"] == 12
        duplicate = {**payload["orders"][0], "quantity": 4}
        extra = {**payload["orders"][0], "order_id": "new-order"}
        assert client.post("/v1/events", json={"orders": [extra, duplicate]}).status_code == 409
        result = client.get("/v1/report", params={"slippage_bps": 1})
        assert result.status_code == 200
        assert result.json()["summary"]["orders"] == 6
        assert result.json()["limits"]["slippage_bps"] == 1
        assert client.get("/v1/report", params={"as_of": "2026-04-24T12:00:00"}).status_code == 422

    with TestClient(create_app(tmp_path / "orders.db")) as client:
        cutoff = batch.orders[0].sent_at + timedelta(milliseconds=500)
        result = client.get("/v1/report", params={"as_of": cutoff.isoformat()}).json()
        assert result["orders"][0]["filled_qty"] == 0.4


def test_wrong_venue_is_orphan_and_costs_remain_visible():
    batch = demo_batch()
    receipt = batch.fills[0].model_copy(update={"venue": "foreign-exchange"})
    batch.fills.append(receipt)
    report = build_execution_report(batch)
    assert report["orders"][0]["filled_qty"] == 1
    assert report["alerts"][-1]["type"] == "orphan"
    assert report["unlinked_cost_usd"] == pytest.approx(1.45)
