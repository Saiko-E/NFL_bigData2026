"""SYNTHETIC test dataset generator. Not real NFL data: used only by the tests, written to tmp dirs.

Layout: 3 plays in 2 games. Game 2021000001 (week 1): play 1 offense AAA moving right (LOS x=40),
play 2 offense BBB moving left (LOS x=80). Game 2021000002 (week 2): play 1 offense AAA moving right.
Each play has 12 frames, snap at frame 3 (plus an earlier autoevent_ballsnap at frame 2), throw at frame 8.
"""
from __future__ import annotations

import csv
from pathlib import Path

G1, G2 = 2021000001, 2021000002
OFF_POS = ["QB", "RB", "WR", "WR", "WR", "TE", "T", "G", "C", "G", "T"]
DEF_POS = ["DE", "DT", "DT", "DE", "OLB", "MLB", "OLB", "CB", "CB", "FS", "SS"]
# id ranges per (team, side)
IDS = {("AAA", "off"): range(1, 12), ("AAA", "def"): range(12, 23), ("BBB", "off"): range(23, 34),
       ("BBB", "def"): range(34, 45), ("CCC", "def"): range(45, 56)}
SNAP, THROW, NFRAMES = 3, 8, 12

PLAYS = [  # gameId, playId, offense, defense, direction, los_raw, passResult
    (G1, 1, "AAA", "BBB", "right", 40, "C"),
    (G1, 2, "BBB", "AAA", "left", 80, "S"),
    (G2, 1, "AAA", "CCC", "right", 40, "I"),
]
GAMES = [(G1, 1, "09/09/2021", "AAA", "BBB"), (G2, 2, "09/16/2021", "AAA", "CCC")]

TRACK_HDR = ["gameId", "playId", "nflId", "frameId", "time", "jerseyNumber", "team", "playDirection",
             "x", "y", "s", "a", "dis", "o", "dir", "event"]
PLAY_HDR = ["gameId", "playId", "playDescription", "quarter", "down", "yardsToGo", "possessionTeam",
            "defensiveTeam", "yardlineSide", "yardlineNumber", "gameClock", "preSnapHomeScore",
            "preSnapVisitorScore", "passResult", "penaltyYards", "prePenaltyPlayResult", "playResult",
            "foulName1", "foulNFLId1", "foulName2", "foulNFLId2", "foulName3", "foulNFLId3",
            "absoluteYardlineNumber", "offenseFormation", "personnelO", "defendersInBox", "personnelD",
            "dropBackType", "pff_playAction", "pff_passCoverage", "pff_passCoverageType"]
PFF_HDR = ["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp", "pff_hit", "pff_hurry",
           "pff_sack", "pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed",
           "pff_nflIdBlockedPlayer", "pff_blockType", "pff_backFieldBlock"]


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        wr = csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC)
        wr.writerow(header)
        for r in rows:
            wr.writerow(["NA" if v is None else v for v in r])


def tracking_rows(game: int, play: int, off: str, deff: str, direction: str, los: float) -> list[list]:
    sgn = 1 if direction == "right" else -1  # downfield direction in raw x
    off_ids, def_ids = list(IDS[(off, "off")]), list(IDS[(deff, "def")])
    ents = [(i, off, "off", k) for k, i in enumerate(off_ids)] + [(i, deff, "def", k) for k, i in enumerate(def_ids)]

    def pos(kind: str, k: int, f: int) -> tuple[float, float, float]:
        """x, y and a direction (deg) for entity at frame f."""
        post = max(0, f - SNAP)
        if kind == "off":
            back = 5.0 if k == 0 else 1.0
            base = los - sgn * back
            step = 0.3 * min(post, 6) if k == 0 else 0.0
            x = base - sgn * step
            move = (270 if sgn == 1 else 90) if (k == 0 and post) else 90
        else:
            base = los + sgn * (1.0 if k < 4 else 5.0 + k * 0.1)
            step = 0.25 * min(post, 6) if k < 4 else 0.0
            x = base - sgn * step
            move = (270 if sgn == 1 else 90) if (k < 4 and post) else 90
        return x, 20.0 + 2.0 * k + (0.0 if kind == "off" else 1.0), move

    def ball_x(f: int, qbx: float) -> float:
        if f <= SNAP:
            return float(los)
        if f <= 6:
            return los + (qbx - los) * ((f - SNAP) / 3)
        if f <= THROW:
            return qbx
        return qbx + sgn * 3.0 * (f - THROW)

    rows, prev = [], {}
    for f in range(1, NFRAMES + 1):
        t = f"2021-09-10T00:26:{31 + (f - 1) // 10:02d}Z"
        ev = "ball_snap" if f == SNAP else "autoevent_ballsnap" if f == SNAP - 1 else \
            "pass_forward" if f == THROW else "None"
        qbx = pos("off", 0, f)[0]
        bx = ball_x(f, qbx)
        entities = [(None, "football", None, bx, 24.0, None)]
        for nid, team, kind, k in ents:
            x, y, d = pos(kind, k, f)
            entities.append((nid, team, 10 + k, x, y, d))
        for nid, team, jersey, x, y, d in entities:
            key = nid or "ball"
            px, py = prev.get(key, (x, y))
            dis = round(((x - px) ** 2 + (y - py) ** 2) ** 0.5, 2)
            prev[key] = (x, y)
            rows.append([game, play, nid, f, t, jersey, team, direction, round(x, 2), round(y, 2),
                         round(dis * 10, 2), 0.0, dis, None if nid is None else 90.0, d, ev])
    return rows


def pff_rows(game: int, play: int, off: str, deff: str) -> list[list]:
    off_ids, def_ids = list(IDS[(off, "off")]), list(IDS[(deff, "def")])
    rows = []
    for k, i in enumerate(off_ids):
        if k == 0:
            rows.append([game, play, i, "Pass", "QB"] + [None] * 10)
        elif k in (2, 3, 4):
            rows.append([game, play, i, "Pass Route", OFF_POS[k]] + [None] * 10)
        else:
            blocked = def_ids[k - 6] if k >= 6 and k - 6 < 4 else None
            hurry_allowed = 1 if k == 6 else 0
            rows.append([game, play, i, "Pass Block", OFF_POS[k], None, None, None, 0, 0, hurry_allowed,
                         0, blocked, "PP" if blocked else None, 0])
    for k, i in enumerate(def_ids):
        if k < 4:
            rows.append([game, play, i, "Pass Rush", DEF_POS[k], 0, 1 if k == 0 else 0, 0] + [None] * 7)
        else:
            rows.append([game, play, i, "Coverage", DEF_POS[k]] + [None] * 10)
    return rows


def build_dataset(data_dir: Path) -> Path:
    """Write a complete synthetic raw dataset under data_dir/raw. Returns data_dir."""
    raw = data_dir / "raw"
    _w(raw / "games.csv", ["gameId", "season", "week", "gameDate", "gameTimeEastern", "homeTeamAbbr",
                           "visitorTeamAbbr"], [[g, 2021, w, d, "13:00:00", h, v] for g, w, d, h, v in GAMES])
    players = []
    for (team, side), ids in IDS.items():
        pos = OFF_POS if side == "off" else DEF_POS
        for k, i in enumerate(ids):
            players.append([i, "6-2", 200 + k, "1990-01-02" if i % 2 else "01/02/1991", "Synthetic U",
                            pos[k], f"Player {i}"])
    _w(raw / "players.csv", ["nflId", "height", "weight", "birthDate", "collegeName", "officialPosition",
                             "displayName"], players)
    plays, pff = [], []
    for g, p, off, deff, direction, los, res in PLAYS:
        plays.append([g, p, "synthetic play", 1, 1, 10, off, deff, off, 40, "13:33", 0, 0, res, None, 5, 5,
                      None, None, None, None, None, None, los, "SHOTGUN", "1 RB, 1 TE, 3 WR", 6,
                      "4 DL, 2 LB, 5 DB", "TRADITIONAL", 0, "Cover-3", "Zone"])
        pff += pff_rows(g, p, off, deff)
        _w(raw / "tracking" / f"tracking_{g}.csv", TRACK_HDR, [])  # placeholder, rewritten below
    _w(raw / "plays.csv", PLAY_HDR, plays)
    _w(raw / "pffScoutingData.csv", PFF_HDR, pff)
    for g in (G1, G2):
        rows = []
        for gg, p, off, deff, direction, los, _ in PLAYS:
            if gg == g:
                rows += tracking_rows(g, p, off, deff, direction, los)
        _w(raw / "tracking" / f"tracking_{g}.csv", TRACK_HDR, rows)
    return data_dir
