"""Dimension tables: games, plays, players, pff. Validates keys and referential integrity."""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .config import EXPECTED_SEASON, EXPECTED_WEEKS, PASS_RESULTS, PFF_ROLES, Paths
from .io import read_csv_typed, write_parquet_atomic
from .quality import QualityLog
from .schemas import PFF_BINARY, SOURCES

POSITION_GROUP = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "T": "OL", "G": "OL", "C": "OL", "DE": "DL", "DT": "DL", "NT": "DL",
    "OLB": "LB", "ILB": "LB", "MLB": "LB", "LB": "LB",
    "CB": "DB", "FS": "DB", "SS": "DB", "DB": "DB",
}


@dataclass
class Dims:
    games: pl.DataFrame
    plays: pl.DataFrame
    players: pl.DataFrame
    pff: pl.DataFrame
    log: QualityLog


def _dup_check(df: pl.DataFrame, keys: list[str], name: str, log: QualityLog) -> None:
    dups = df.group_by(keys).len().filter(pl.col("len") > 1)
    log.check(f"{name}.duplicate_keys", dups.height, severity="error", detail=f"key={keys}",
              total=df.height)


def _null_summary(df: pl.DataFrame, name: str, log: QualityLog) -> dict[str, int]:
    nulls = {c: int(n) for c, n in zip(df.columns, df.null_count().row(0)) if n}
    log.check(f"{name}.columns_with_nulls", len(nulls), severity="info",
              detail=", ".join(f"{k}={v}" for k, v in nulls.items()), total=df.height)
    return nulls


def build_games(raw: pl.DataFrame, log: QualityLog) -> pl.DataFrame:
    _dup_check(raw, ["gameId"], "games", log)
    df = raw.unique(subset=["gameId"], keep="first", maintain_order=True).with_columns(
        pl.col("gameDate").str.to_date("%m/%d/%Y", strict=False).alias("gameDate"),
        pl.col("gameTimeEastern").str.to_time("%H:%M:%S", strict=False).alias("gameTimeEastern"),
    )
    log.check("games.unparsed_date", df["gameDate"].is_null().sum(), severity="error")
    out_scope = df.filter((pl.col("season") != EXPECTED_SEASON)
                          | ~pl.col("week").is_in(list(EXPECTED_WEEKS)))
    log.check("games.outside_expected_scope", out_scope.height, severity="warn",
              detail=f"expected season {EXPECTED_SEASON} weeks {EXPECTED_WEEKS[0]}-{EXPECTED_WEEKS[-1]}")
    same = df.filter(pl.col("homeTeamAbbr") == pl.col("visitorTeamAbbr"))
    log.check("games.home_equals_visitor", same.height, severity="error")
    _null_summary(df, "games", log)
    return df.sort("gameId")


def build_players(raw: pl.DataFrame, log: QualityLog) -> pl.DataFrame:
    _dup_check(raw, ["nflId"], "players", log)
    df = raw.unique(subset=["nflId"], keep="first", maintain_order=True)
    ft_in = pl.col("height").str.extract_groups(r"^(\d+)-(\d+)$")
    df = df.with_columns(
        (ft_in.struct.field("1").cast(pl.Int64, strict=False) * 12
         + ft_in.struct.field("2").cast(pl.Int64, strict=False)).alias("heightInches"),
        # Two formats exist in the source: YYYY-MM-DD and MM/DD/YYYY.
        pl.coalesce(
            pl.col("birthDate").str.to_date("%Y-%m-%d", strict=False),
            pl.col("birthDate").str.to_date("%m/%d/%Y", strict=False),
        ).alias("birthDate"),
        pl.col("officialPosition").replace_strict(POSITION_GROUP, default=None).alias("positionGroup"),
    )
    log.check("players.unparsed_height", df.filter(pl.col("heightInches").is_null()).height)
    log.check("players.unparsed_birthDate",
              raw.filter(pl.col("birthDate").is_not_null()).height
              - df["birthDate"].is_not_null().sum(), detail="non-null source value not parseable")
    log.check("players.unmapped_position", df.filter(pl.col("positionGroup").is_null()).height,
              detail="officialPosition not in POSITION_GROUP")
    _null_summary(df, "players", log)
    return df.sort("nflId")


def build_plays(raw: pl.DataFrame, games: pl.DataFrame, log: QualityLog) -> pl.DataFrame:
    _dup_check(raw, ["gameId", "playId"], "plays", log)
    df = raw.unique(subset=["gameId", "playId"], keep="first", maintain_order=True)
    orphans = df.join(games.select("gameId"), on="gameId", how="anti")
    log.check("plays.fk_gameId_missing_in_games", orphans.height, severity="error", total=df.height)
    df = df.join(games.select("gameId", "week", "homeTeamAbbr", "visitorTeamAbbr"),
                 on="gameId", how="inner")
    bad_pr = df.filter(pl.col("passResult").is_not_null() & ~pl.col("passResult").is_in(PASS_RESULTS))
    log.check("plays.unknown_passResult", bad_pr.height, detail=f"expected {PASS_RESULTS}")
    log.check("plays.passResult_null", df["passResult"].is_null().sum(), detail="no pass result recorded")
    def in_game(c: str) -> pl.Expr:
        return (pl.col(c) == pl.col("homeTeamAbbr")) | (pl.col(c) == pl.col("visitorTeamAbbr"))

    bad_team = df.filter(~in_game("possessionTeam") | ~in_game("defensiveTeam")
                         | (pl.col("possessionTeam") == pl.col("defensiveTeam")))
    log.check("plays.teams_not_in_game", bad_team.height, severity="error",
              detail="possession/defensive team not matching the game's teams")
    clock = pl.col("gameClock").str.extract_groups(r"^(\d+):(\d+)")
    df = df.with_columns(
        (clock.struct.field("1").cast(pl.Int64, strict=False) * 60
         + clock.struct.field("2").cast(pl.Int64, strict=False)).alias("gameClockSeconds"),
        (pl.col("passResult") == "S").alias("isSack"),
        pl.col("offenseFormation").is_null().alias("formationMissing"),
        pl.when(pl.col("possessionTeam") == pl.col("homeTeamAbbr"))
          .then(pl.col("preSnapHomeScore") - pl.col("preSnapVisitorScore"))
          .otherwise(pl.col("preSnapVisitorScore") - pl.col("preSnapHomeScore")).alias("scoreDiffOffense"),
    ).drop("homeTeamAbbr", "visitorTeamAbbr")
    _null_summary(df, "plays", log)
    return df.sort("gameId", "playId")


def build_pff(raw: pl.DataFrame, plays: pl.DataFrame, players: pl.DataFrame,
              log: QualityLog) -> pl.DataFrame:
    _dup_check(raw, ["gameId", "playId", "nflId"], "pff", log)
    df = raw.unique(subset=["gameId", "playId", "nflId"], keep="first", maintain_order=True)
    log.check("pff.fk_play_missing", df.join(plays.select("gameId", "playId"), on=["gameId", "playId"],
                                              how="anti").height, severity="error", total=df.height)
    log.check("pff.fk_player_missing", df.join(players.select("nflId"), on="nflId", how="anti").height,
              severity="error", total=df.height)
    bad_role = df.filter(~pl.col("pff_role").is_in(PFF_ROLES))
    log.check("pff.unknown_role", bad_role.height, detail=f"expected {PFF_ROLES}")
    blocked = df.filter(pl.col("pff_nflIdBlockedPlayer").is_not_null())
    fk_blocked = blocked.join(df.select("gameId", "playId", pl.col("nflId").alias("pff_nflIdBlockedPlayer")),
                              on=["gameId", "playId", "pff_nflIdBlockedPlayer"], how="anti")
    log.check("pff.blocked_player_not_in_play", fk_blocked.height,
              detail="pff_nflIdBlockedPlayer has no PFF row in same play", total=blocked.height)
    per_play = df.group_by("gameId", "playId").agg(
        (pl.col("pff_role") == "Pass").sum().alias("n_pass"), pl.len().alias("n"))
    log.check("pff.plays_without_single_pass_role", per_play.filter(pl.col("n_pass") != 1).height,
              severity="error", total=per_play.height)
    log.check("pff.plays_without_22_rows", per_play.filter(pl.col("n") != 22).height, severity="info",
              total=per_play.height, detail="rows per play differ from 22")
    log.check("pff.plays_missing_in_pff",
              plays.select("gameId", "playId").join(per_play.select("gameId", "playId"),
                                                    on=["gameId", "playId"], how="anti").height,
              total=plays.height)
    nonbin = sum(df.filter(pl.col(c).is_not_null() & ~pl.col(c).is_in([0, 1])).height for c in PFF_BINARY)
    log.check("pff.non_binary_flags", nonbin, severity="error")
    df = df.with_columns([pl.col(c).cast(pl.Boolean) for c in PFF_BINARY])
    _null_summary(df, "pff", log)
    return df.sort("gameId", "playId", "nflId")


def build_dims(paths: Paths, write: bool = True) -> Dims:
    """Read the four small CSVs, validate, and (optionally) write dim/*.parquet."""
    log = QualityLog("dims")
    raw: dict[str, pl.DataFrame] = {}
    for name, (fname, schema) in SOURCES.items():
        raw[name] = read_csv_typed(paths.raw / fname, schema, log, name)
        log.check(f"{name}.rows_read", 0, severity="info", detail=f"{raw[name].height} rows",
                  total=raw[name].height)
    games = build_games(raw["games"], log)
    players = build_players(raw["players"], log)
    plays = build_plays(raw["plays"], games, log)
    pff = build_pff(raw["pff"], plays, players, log)
    if write:
        for name, df in [("games", games), ("plays", plays), ("players", players), ("pff", pff)]:
            write_parquet_atomic(df, paths.dim / f"{name}.parquet")
    return Dims(games, plays, players, pff, log)
