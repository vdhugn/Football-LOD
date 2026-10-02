from scope import Scope, select_scope


def test_games_filtered_by_competition_and_season(ctx):
    s = ctx.scope
    assert s.game_ids == {"100", "200"}          # 101 is season 2022, excluded
    assert s.game_kind == {"100": "club", "200": "national"}


def test_clubs_and_national_teams(ctx):
    s = ctx.scope
    assert {"11", "148"} <= s.club_ids
    assert "999" in s.club_ids                    # from an in-scope player's transfer
    assert "777" not in s.club_ids                # valuation of an out-of-scope player
    assert s.national_ids == {"3299", "9999"}
    assert s.club_names["148"] == "Tottenham Hotspur"
    assert s.club_names["999"] == "Hale End"      # "Unknown" valuation name never wins
    assert s.national_names["9999"] == "Serbia and Montenegro"


def test_players(ctx):
    assert ctx.scope.player_ids == {"10", "20"}   # 30: only in excluded game / other club


def test_save_and_load_round_trip(ctx, tmp_path):
    p = tmp_path / "scope.json"
    ctx.scope.save(p)
    assert Scope.load(p) == ctx.scope


def test_unknown_club_name_is_ignored(cfg, data_dir):
    s = select_scope(cfg, data_dir)
    assert "Unknown" not in s.club_names.values()
