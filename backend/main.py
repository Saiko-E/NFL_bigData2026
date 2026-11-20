"""Phase 2 read-only NFL analytics API.

Run from the repository root with:
    .venv/bin/uvicorn backend.main:app --reload
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import PROJECT_ROOT, DataUnavailable, connection, page, row, rows

PageLimit = Annotated[int, Query(ge=1, le=500)]
PageOffset = Annotated[int, Query(ge=0)]
TrackingLimit = Annotated[int, Query(ge=1, le=10_000)]

app = FastAPI(
    title="NFL UNAM Analytics API",
    version="2.0.0",
    description="Read-only API over the processed NFL Big Data Bowl Parquet catalog.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(DataUnavailable)
def unavailable_handler(_: Request, exc: DataUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc), "code": "data_unavailable"})


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health() -> dict:
    with connection() as con:
        tables = sorted(item[0] for item in con.execute("SHOW TABLES").fetchall())
    required = {"games", "plays", "players", "tracking"}
    ready = required.issubset(tables)
    return {"status": "ok" if ready else "degraded", "dataReady": ready, "tables": tables}


@app.get("/api/overview", tags=["analytics"])
def overview() -> dict:
    with connection("games", "plays", "players", "tracking", "play_summary", "player_summary", "team_summary") as con:
        result = row(con, """
            SELECT
              (SELECT count(*) FROM games) AS games,
              (SELECT count(*) FROM plays) AS plays,
              (SELECT count(*) FROM players) AS players,
              (SELECT count(DISTINCT team) FROM team_summary) AS teams,
              (SELECT count(*) FROM tracking) AS trackingRows,
              (SELECT count(DISTINCT week) FROM games) AS weeks,
              (SELECT round(avg(time_to_throw_s), 3) FROM play_summary) AS avgTimeToThrowSeconds,
              (SELECT count(*) FROM plays WHERE isSack) AS sacks
        """)
    return result or {}


@app.get("/api/games", tags=["catalog"])
def games(
    week: Annotated[int | None, Query(ge=1, le=22)] = None,
    season: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    team: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> dict:
    clauses, params = [], []
    if week is not None:
        clauses.append("g.week = ?"); params.append(week)
    if season is not None:
        clauses.append("g.season = ?"); params.append(season)
    if team:
        clauses.append("(g.homeTeamAbbr = ? OR g.visitorTeamAbbr = ?)"); params.extend([team.upper()] * 2)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""SELECT g.*, s.n_plays, s.n_tracked_plays, s.n_sack, s.n_pressure_plays,
                     s.avg_time_to_throw_s
              FROM games g LEFT JOIN game_summary s USING (gameId) {where}"""
    with connection("games", "game_summary") as con:
        return page(con, sql, params, order_by="g.gameDate, g.gameId", limit=limit, offset=offset)


@app.get("/api/teams", tags=["catalog"])
def teams(
    search: Annotated[str | None, Query(min_length=1, max_length=3)] = None,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> dict:
    sql = """SELECT team,
               max(n_games) FILTER (side = 'offense') AS offensiveGames,
               max(n_games) FILTER (side = 'defense') AS defensiveGames,
               max(n_plays) FILTER (side = 'offense') AS offensivePlays,
               max(n_plays) FILTER (side = 'defense') AS defensivePlays,
               max(avg_play_result) FILTER (side = 'offense') AS avgOffensivePlayResult,
               max(avg_play_result) FILTER (side = 'defense') AS avgAllowedPlayResult,
               max(n_pressure_plays) FILTER (side = 'defense') AS defensivePressurePlays
             FROM team_summary"""
    params: list[object] = []
    if search:
        sql += " WHERE team LIKE ?"; params.append(f"%{search.upper()}%")
    sql += " GROUP BY team"
    with connection("team_summary") as con:
        return page(con, sql, params, order_by="team", limit=limit, offset=offset)


@app.get("/api/players", tags=["catalog"])
def players(
    search: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    position: Annotated[str | None, Query(min_length=1, max_length=4)] = None,
    team: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> dict:
    clauses, params = [], []
    if search:
        clauses.append("lower(p.displayName) LIKE lower(?)"); params.append(f"%{search}%")
    if position:
        clauses.append("(p.officialPosition = ? OR p.positionGroup = ?)"); params.extend([position.upper()] * 2)
    if team:
        clauses.append("(',' || coalesce(s.teams, '') || ',') LIKE ?"); params.append(f"%,{team.upper()},%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""SELECT p.*, s.teams, s.n_plays, s.n_games, s.top_speed_yps,
                     s.hits, s.hurries, s.sacks
              FROM players p LEFT JOIN player_summary s USING (nflId) {where}"""
    with connection("players", "player_summary") as con:
        return page(con, sql, params, order_by="p.displayName, p.nflId", limit=limit, offset=offset)


@app.get("/api/plays", tags=["catalog"])
def plays(
    game_id: Annotated[int | None, Query(alias="gameId", ge=1)] = None,
    week: Annotated[int | None, Query(ge=1, le=22)] = None,
    team: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    formation: Annotated[str | None, Query(min_length=1, max_length=30)] = None,
    pass_result: Annotated[str | None, Query(alias="passResult", max_length=3)] = None,
    has_pressure: Annotated[bool | None, Query(alias="hasPressure")] = None,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> dict:
    clauses, params = [], []
    if game_id is not None:
        clauses.append("gameId = ?"); params.append(game_id)
    if week is not None:
        clauses.append("week = ?"); params.append(week)
    if team:
        clauses.append("(possessionTeam = ? OR defensiveTeam = ?)"); params.extend([team.upper()] * 2)
    if formation:
        clauses.append("offenseFormation = ?"); params.append(formation.upper())
    if pass_result:
        clauses.append("passResult = ?"); params.append(pass_result.upper())
    if has_pressure is not None:
        clauses.append("has_pressure = ?"); params.append(has_pressure)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM play_summary {where}"
    with connection("play_summary") as con:
        return page(con, sql, params, order_by="gameId, playId", limit=limit, offset=offset)


@app.get("/api/plays/{game_id}/{play_id}/tracking", tags=["tracking"])
def play_tracking(
    game_id: int,
    play_id: int,
    frame_start: Annotated[int | None, Query(alias="frameStart", ge=1)] = None,
    frame_end: Annotated[int | None, Query(alias="frameEnd", ge=1)] = None,
    nfl_id: Annotated[int | None, Query(alias="nflId", ge=1)] = None,
    side: Literal["offense", "defense", "ball"] | None = None,
    limit: TrackingLimit = 5000,
    offset: PageOffset = 0,
) -> dict:
    if frame_start is not None and frame_end is not None and frame_end < frame_start:
        raise HTTPException(status_code=422, detail="frameEnd must be greater than or equal to frameStart")
    clauses = ["t.gameId = ?", "t.playId = ?"]
    params: list[object] = [game_id, play_id]
    if frame_start is not None:
        clauses.append("t.frameId >= ?"); params.append(frame_start)
    if frame_end is not None:
        clauses.append("t.frameId <= ?"); params.append(frame_end)
    if nfl_id is not None:
        clauses.append("t.nflId = ?"); params.append(nfl_id)
    if side:
        clauses.append("t.side = ?"); params.append(side)
    sql = f"""SELECT t.*, p.displayName, p.officialPosition
              FROM tracking t LEFT JOIN players p USING (nflId)
              WHERE {' AND '.join(clauses)}"""
    with connection("tracking", "players") as con:
        result = page(con, sql, params, order_by="t.frameId, t.nflId NULLS LAST", limit=limit, offset=offset)
    if result["total"] == 0:
        raise HTTPException(status_code=404, detail="Tracking play not found")
    return result


@app.get("/api/players/compare", tags=["analytics"])
def compare_players(
    nfl_ids: Annotated[str, Query(alias="nflIds", min_length=3, description="Comma-separated NFL IDs")],
) -> dict:
    try:
        ids = list(dict.fromkeys(int(value.strip()) for value in nfl_ids.split(",") if value.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="nflIds must contain integers") from exc
    if not 2 <= len(ids) <= 10 or any(value <= 0 for value in ids):
        raise HTTPException(status_code=422, detail="Provide 2 to 10 positive, unique nflIds")
    placeholders = ", ".join("?" for _ in ids)
    with connection("player_summary") as con:
        result = rows(con, f"SELECT * FROM player_summary WHERE nflId IN ({placeholders}) ORDER BY displayName", ids)
    if not result:
        raise HTTPException(status_code=404, detail="Players not found")
    return {"players": result, "requested": ids, "total": len(result)}


@app.get("/api/players/{nfl_id}/stats", tags=["analytics"])
def player_stats(nfl_id: int) -> dict:
    with connection("player_summary") as con:
        result = row(con, "SELECT * FROM player_summary WHERE nflId = ?", [nfl_id])
    if result is None:
        raise HTTPException(status_code=404, detail="Player statistics not found")
    return result


@app.get("/api/teams/{team}/stats", tags=["analytics"])
def team_stats(team: str) -> dict:
    if not 2 <= len(team) <= 3 or not team.isalpha():
        raise HTTPException(status_code=422, detail="team must be a 2-3 letter abbreviation")
    with connection("team_summary") as con:
        result = rows(con, "SELECT * FROM team_summary WHERE team = ? ORDER BY side", [team.upper()])
    if not result:
        raise HTTPException(status_code=404, detail="Team statistics not found")
    return {"team": team.upper(), "splits": result}


@app.get("/api/plays/{game_id}/{play_id}/matchups", tags=["analytics"])
def play_matchups(game_id: int, play_id: int) -> dict:
    sql = """SELECT b.nflId AS blockerNflId, bp.displayName AS blockerName,
                    b.pff_positionLinedUp AS blockerPosition,
                    b.pff_nflIdBlockedPlayer AS rusherNflId, rp.displayName AS rusherName,
                    r.pff_positionLinedUp AS rusherPosition, b.pff_blockType AS blockType,
                    b.pff_backFieldBlock AS backFieldBlock, b.pff_beatenByDefender AS beaten,
                    b.pff_hitAllowed AS hitAllowed, b.pff_hurryAllowed AS hurryAllowed,
                    b.pff_sackAllowed AS sackAllowed, r.pff_hit AS hit,
                    r.pff_hurry AS hurry, r.pff_sack AS sack
             FROM pff b
             LEFT JOIN pff r ON r.gameId = b.gameId AND r.playId = b.playId
                            AND r.nflId = b.pff_nflIdBlockedPlayer
             LEFT JOIN players bp ON bp.nflId = b.nflId
             LEFT JOIN players rp ON rp.nflId = b.pff_nflIdBlockedPlayer
             WHERE b.gameId = ? AND b.playId = ? AND b.pff_role = 'Pass Block'
             ORDER BY b.nflId, b.pff_nflIdBlockedPlayer"""
    with connection("pff", "players") as con:
        result = rows(con, sql, [game_id, play_id])
        exists = con.execute("SELECT count(*) FROM pff WHERE gameId = ? AND playId = ?", [game_id, play_id]).fetchone()[0]
    if not exists:
        raise HTTPException(status_code=404, detail="Play not found")
    return {"gameId": game_id, "playId": play_id, "matchups": result, "total": len(result)}


@app.get("/api/analytics/tactics", tags=["analytics"])
def tactics(
    dimension: Literal["formation", "coverage", "dropback"] = "formation",
    team: Annotated[str | None, Query(min_length=2, max_length=3)] = None,
    week: Annotated[int | None, Query(ge=1, le=22)] = None,
    min_plays: Annotated[int, Query(alias="minPlays", ge=1, le=1000)] = 10,
    limit: PageLimit = 100,
    offset: PageOffset = 0,
) -> dict:
    dimensions = {"formation": "offenseFormation", "coverage": "pff_passCoverage", "dropback": "dropBackType"}
    column = dimensions[dimension]
    clauses = [f"{column} IS NOT NULL"]
    params: list[object] = []
    if team:
        clauses.append("possessionTeam = ?"); params.append(team.upper())
    if week is not None:
        clauses.append("week = ?"); params.append(week)
    sql = f"""SELECT {column} AS tactic, count(*) AS nPlays,
                     avg(playResult) AS avgPlayResult,
                     avg(CASE WHEN passResult = 'C' THEN 1.0 ELSE 0.0 END) AS completionRate,
                     avg(CASE WHEN has_pressure THEN 1.0 ELSE 0.0 END) AS pressureRate,
                     avg(time_to_throw_s) AS avgTimeToThrowSeconds
              FROM play_summary WHERE {' AND '.join(clauses)} GROUP BY {column} HAVING count(*) >= ?"""
    params.append(min_plays)
    with connection("play_summary") as con:
        result = page(con, sql, params, order_by="nPlays DESC, tactic", limit=limit, offset=offset)
    result["dimension"] = dimension
    return result


# When a production dashboard build exists, serve it after all API routes.
# Development still uses Vite on port 5173 with its /api proxy.
_dashboard_dist = PROJECT_ROOT / "dashboard" / "dist"
if _dashboard_dist.exists():
    app.mount("/", StaticFiles(directory=_dashboard_dist, html=True), name="dashboard")
