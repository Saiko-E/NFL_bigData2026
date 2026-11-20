"""API integration tests. Real-data assertions skip when processed Parquet is absent."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/processed/dim/games.parquet").exists()
client = TestClient(app)
real_data = pytest.mark.skipif(not HAS_DATA, reason="processed NFL data is not available")


def test_health_routes_and_localhost_cors() -> None:
    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    cors = client.options(
        "/api/games",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"
    if (ROOT / "dashboard/dist/index.html").exists():
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "text/html" in dashboard.headers["content-type"]


def test_missing_data_is_reported_without_crashing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NFL_DATA_DIR", str(tmp_path))
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["dataReady"] is False
    assert health.json()["mode"] == "static-demo"
    unavailable = client.get("/api/overview")
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "data_unavailable"


@real_data
def test_overview_is_backed_by_real_catalog() -> None:
    response = client.get("/api/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["games"] > 0
    assert body["plays"] > body["games"]
    assert body["trackingRows"] > body["plays"]
    assert body["avgTimeToThrowSeconds"] is not None


@real_data
def test_catalog_filters_and_pagination() -> None:
    games = client.get("/api/games", params={"week": 1, "team": "TB", "limit": 2}).json()
    assert games["total"] > 0 and len(games["items"]) <= 2
    assert all(game["week"] == 1 for game in games["items"])

    teams = client.get("/api/teams", params={"search": "TB"}).json()
    assert any(team["team"] == "TB" for team in teams["items"])

    players = client.get("/api/players", params={"search": "Brady", "position": "QB"}).json()
    assert players["total"] >= 1
    assert any(player["displayName"] == "Tom Brady" for player in players["items"])

    plays = client.get(
        "/api/plays", params={"gameId": 2021090900, "formation": "SHOTGUN", "limit": 3}
    ).json()
    assert plays["total"] > 0 and len(plays["items"]) <= 3
    assert all(play["gameId"] == 2021090900 for play in plays["items"])


@real_data
def test_tracking_matchups_and_stats_are_json_safe() -> None:
    tracking = client.get(
        "/api/plays/2021090900/97/tracking", params={"frameStart": 6, "frameEnd": 6}
    )
    assert tracking.status_code == 200
    tracking_body = tracking.json()
    assert tracking_body["total"] == 23
    assert all(item["frameId"] == 6 for item in tracking_body["items"])
    assert all("x_std" in item and "y_std" in item and "dir_std" in item for item in tracking_body["items"])
    assert isinstance(tracking_body["items"][0]["time"], str)

    matchups = client.get("/api/plays/2021090900/97/matchups")
    assert matchups.status_code == 200
    assert matchups.json()["total"] > 0

    player = client.get("/api/players/25511/stats")
    assert player.status_code == 200
    assert player.json()["displayName"] == "Tom Brady"

    team = client.get("/api/teams/TB/stats")
    assert team.status_code == 200
    assert {split["side"] for split in team.json()["splits"]} == {"offense", "defense"}


@real_data
def test_optional_analytics_and_validation_errors() -> None:
    tactics = client.get("/api/analytics/tactics", params={"dimension": "coverage", "minPlays": 20})
    assert tactics.status_code == 200
    assert tactics.json()["dimension"] == "coverage"
    assert tactics.json()["items"]

    comparison = client.get("/api/players/compare", params={"nflIds": "25511,35466"})
    assert comparison.status_code == 200
    assert comparison.json()["total"] >= 1

    assert client.get("/api/games", params={"week": 0}).status_code == 422
    assert client.get("/api/plays/2021090900/97/tracking", params={"frameStart": 5, "frameEnd": 2}).status_code == 422
    assert client.get("/api/players/999999999/stats").status_code == 404
    assert client.get("/api/plays/1/1/tracking").status_code == 404
