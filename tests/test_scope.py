from scope import Scope, select_scope


def test_clubs_filtered_by_league_and_season(ctx):
    s = ctx.scope
    assert "11" in s.club_ids
    assert "50" not in s.club_ids                 # GB1 but last_season 2020
    assert "60" not in s.club_ids                 # season 2025 but TR1


def test_clubs_from_transfers_and_valuations(ctx):
    s = ctx.scope
    assert s.club_ids == {"11", "148", "999", "888"}   # in-scope players' transfers / valuations
    assert "777" not in s.club_ids                # valuation of an out-of-scope player
    assert "555" not in s.club_ids                # transfer of an out-of-scope player
    assert s.club_names["11"] == "Arsenal FC"
    assert s.club_names["148"] == "Tottenham Hotspur"
    assert s.club_names["999"] == "Hale End"      # "Unknown" valuation name never wins


def test_players(ctx):
    assert ctx.scope.player_ids == {"10", "20"}   # 30: club outside the leagues; 40: last_season 2021


def test_save_and_load_round_trip(ctx, tmp_path):
    p = tmp_path / "scope.json"
    ctx.scope.save(p)
    assert Scope.load(p) == ctx.scope


def test_unknown_club_name_is_ignored(cfg, data_dir):
    s = select_scope(cfg, data_dir)
    assert "Unknown" not in s.club_names.values()
