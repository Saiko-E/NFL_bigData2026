"""Expected source schemas (verified against the real files) as Polars dtypes.

All raw files use the literal string "NA" for missing values.
"""
import polars as pl

I, S, F = pl.Int64, pl.String, pl.Float64

GAMES = {
    "gameId": I, "season": I, "week": I, "gameDate": S, "gameTimeEastern": S,
    "homeTeamAbbr": S, "visitorTeamAbbr": S,
}

PLAYS = {
    "gameId": I, "playId": I, "playDescription": S, "quarter": I, "down": I, "yardsToGo": I,
    "possessionTeam": S, "defensiveTeam": S, "yardlineSide": S, "yardlineNumber": I,
    "gameClock": S, "preSnapHomeScore": I, "preSnapVisitorScore": I, "passResult": S,
    "penaltyYards": I, "prePenaltyPlayResult": I, "playResult": I,
    "foulName1": S, "foulNFLId1": I, "foulName2": S, "foulNFLId2": I, "foulName3": S,
    "foulNFLId3": I, "absoluteYardlineNumber": I, "offenseFormation": S, "personnelO": S,
    "defendersInBox": I, "personnelD": S, "dropBackType": S, "pff_playAction": I,
    "pff_passCoverage": S, "pff_passCoverageType": S,
}

PLAYERS = {
    "nflId": I, "height": S, "weight": I, "birthDate": S, "collegeName": S,
    "officialPosition": S, "displayName": S,
}

PFF = {
    "gameId": I, "playId": I, "nflId": I, "pff_role": S, "pff_positionLinedUp": S,
    "pff_hit": I, "pff_hurry": I, "pff_sack": I, "pff_beatenByDefender": I,
    "pff_hitAllowed": I, "pff_hurryAllowed": I, "pff_sackAllowed": I,
    "pff_nflIdBlockedPlayer": I, "pff_blockType": S, "pff_backFieldBlock": I,
}
PFF_BINARY = [
    "pff_hit", "pff_hurry", "pff_sack", "pff_beatenByDefender", "pff_hitAllowed",
    "pff_hurryAllowed", "pff_sackAllowed", "pff_backFieldBlock",
]

TRACKING = {
    "gameId": I, "playId": I, "nflId": I, "frameId": I, "time": S, "jerseyNumber": I,
    "team": S, "playDirection": S, "x": F, "y": F, "s": F, "a": F, "dis": F, "o": F,
    "dir": F, "event": S,
}

SOURCES = {
    "games": ("games.csv", GAMES),
    "plays": ("plays.csv", PLAYS),
    "players": ("players.csv", PLAYERS),
    "pff": ("pffScoutingData.csv", PFF),
}
