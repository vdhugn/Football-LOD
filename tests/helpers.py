import csv
from pathlib import Path

from rdflib import Graph

FB = "https://vdhugn.github.io/Football-LOD/ontology#"
R = "https://vdhugn.github.io/Football-LOD/resource/"

HEADERS = {
    "countries.csv": ["country_id", "country_name", "country_code", "confederation", "total_clubs", "total_players", "average_age", "url"],
    "national_teams.csv": ["national_team_id", "name", "team_code", "country_id", "country_name", "country_code", "confederation", "team_image_url", "squad_size", "average_age", "foreigners_number", "foreigners_percentage", "total_market_value", "coach_name", "fifa_ranking", "last_season", "url"],
    "competitions.csv": ["competition_id", "competition_code", "name", "sub_type", "type", "country_id", "country_name", "domestic_league_code", "confederation", "total_clubs", "url"],
    "clubs.csv": ["club_id", "club_code", "name", "domestic_competition_id", "total_market_value", "squad_size", "average_age", "foreigners_number", "foreigners_percentage", "national_team_players", "stadium_name", "stadium_seats", "net_transfer_record", "coach_name", "last_season", "filename", "url"],
    "players.csv": ["player_id", "first_name", "last_name", "name", "last_season", "current_club_id", "player_code", "country_of_birth", "city_of_birth", "country_of_citizenship", "date_of_birth", "sub_position", "position", "foot", "height_in_cm", "contract_expiration_date", "agent_name", "image_url", "international_caps", "international_goals", "current_national_team_id", "url", "current_club_domestic_competition_id", "current_club_name", "market_value_in_eur", "highest_market_value_in_eur"],
    "transfers.csv": ["player_id", "transfer_date", "transfer_season", "from_club_id", "to_club_id", "from_club_name", "to_club_name", "transfer_fee", "market_value_in_eur", "player_name"],
    "player_valuations.csv": ["player_id", "date", "market_value_in_eur", "current_club_name", "current_club_id", "player_club_domestic_competition_id"],
}


def put(data_dir, name, rows):
    header = HEADERS[name]
    with open(Path(data_dir) / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header])


def load_ttl(path):
    g = Graph()
    g.parse(str(path), format="turtle")
    return g


def write_mini(d):
    put(d, "countries.csv", [
        {"country_id": "189", "country_name": "England", "country_code": "GB1", "confederation": "europa", "url": "https://www.transfermarkt.co.uk/wettbewerbe/national/wettbewerbe/189"},
        {"country_id": "50", "country_name": "Türkiye", "country_code": "TR1", "confederation": "europa"},
    ])
    put(d, "national_teams.csv", [
        {"national_team_id": "3299", "name": "England", "team_code": "england", "country_id": "189", "country_name": "England", "country_code": "GB1", "confederation": "UEFA", "team_image_url": "https://tmssl.akamaized.net/e.png", "squad_size": "26", "average_age": "27.1", "foreigners_number": "0", "total_market_value": "1000000000", "coach_name": "Gareth Southgate", "fifa_ranking": "4", "last_season": "2025", "url": "https://www.transfermarkt.co.uk/england/startseite/verein/3299"},
    ])
    put(d, "competitions.csv", [
        {"competition_id": "GB1", "competition_code": "premier-league", "name": "premier-league", "type": "domestic_league", "country_id": "189", "country_name": "England", "confederation": "europa", "url": "https://www.transfermarkt.co.uk/premier-league/startseite/wettbewerb/GB1"},
        {"competition_id": "FIWC", "competition_code": "fifa-world-cup", "name": "fifa-world-cup", "type": "national_team_competition", "country_id": "-1", "confederation": "fifa"},
    ])
    put(d, "clubs.csv", [
        {"club_id": "11", "club_code": "arsenal", "name": "Arsenal FC", "domestic_competition_id": "GB1", "total_market_value": "1200000000", "squad_size": "25", "average_age": "25.1", "foreigners_number": "15", "foreigners_percentage": "60.0", "national_team_players": "10", "stadium_name": "Emirates Stadium", "stadium_seats": "60704", "net_transfer_record": "+€5.90m", "coach_name": "Mikel Arteta", "last_season": "2025", "url": "https://www.transfermarkt.co.uk/arsenal/startseite/verein/11"},
        {"club_id": "50", "name": "Relegated FC", "domestic_competition_id": "GB1", "stadium_name": "Old Ground", "last_season": "2020"},
        {"club_id": "60", "name": "Galatasaray", "domestic_competition_id": "TR1", "stadium_name": "Rams Park", "last_season": "2025"},
        {"club_id": "888", "name": "Atlético Nacional", "domestic_competition_id": "COL1", "last_season": "2020"},
    ])
    put(d, "players.csv", [
        {"player_id": "10", "first_name": "Bukayo", "last_name": "Saka", "name": "Bukayo Saka", "date_of_birth": "2001-09-05 00:00:00", "country_of_birth": "England", "city_of_birth": "London  ", "country_of_citizenship": "England", "sub_position": "Right Winger", "position": "Attack", "foot": "left", "height_in_cm": "178", "current_club_id": "11", "current_club_name": "Arsenal FC", "market_value_in_eur": "120000000", "highest_market_value_in_eur": "130000000", "image_url": "https://img.example/10.jpg", "url": "https://www.transfermarkt.co.uk/saka/profil/spieler/10", "current_national_team_id": "3299", "last_season": "2025"},
        {"player_id": "20", "first_name": "Heung-min", "last_name": "Son", "name": "Heung-min Son", "country_of_citizenship": "Korea, South", "position": "Missing", "current_club_id": "11", "current_club_name": "Arsenal FC", "last_season": "2025"},
        {"player_id": "30", "name": "Far Away", "current_club_id": "60", "current_club_name": "Galatasaray", "last_season": "2025"},
        {"player_id": "40", "name": "Gone Away", "current_club_id": "11", "current_club_name": "Arsenal FC", "last_season": "2021"},
    ])
    put(d, "transfers.csv", [
        {"player_id": "10", "transfer_date": "2019-07-01", "transfer_season": "19/20", "from_club_id": "999", "to_club_id": "11", "from_club_name": "Hale End", "to_club_name": "Arsenal FC", "transfer_fee": "0.000", "market_value_in_eur": "500000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2019-07-01", "transfer_season": "19/20", "from_club_id": "999", "to_club_id": "11", "from_club_name": "Hale End", "to_club_name": "Arsenal FC", "transfer_fee": "0.000", "market_value_in_eur": "500000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2023-01-01", "transfer_season": "22/23", "from_club_id": "11", "to_club_id": "148", "from_club_name": "Arsenal FC", "to_club_name": "Tottenham Hotspur", "transfer_fee": "5000000.000", "market_value_in_eur": "90000000.000", "player_name": "Bukayo Saka"},
        {"player_id": "10", "transfer_date": "2024-01-01", "transfer_season": "23/24", "from_club_id": "148", "to_club_id": "11", "from_club_name": "Tottenham Hotspur", "to_club_name": "Arsenal FC", "transfer_fee": "", "player_name": "Bukayo Saka"},
        {"player_id": "30", "transfer_date": "2020-01-01", "transfer_season": "19/20", "from_club_id": "555", "to_club_id": "999", "from_club_name": "Nowhere", "to_club_name": "Elsewhere FC", "transfer_fee": "100.000", "player_name": "Far Away"},
    ])
    put(d, "player_valuations.csv", [
        {"player_id": "10", "date": "2023-06-01", "market_value_in_eur": "100000000", "current_club_name": "Arsenal FC", "current_club_id": "11"},
        {"player_id": "10", "date": "2019-01-01", "market_value_in_eur": "5000000", "current_club_name": "Unknown", "current_club_id": "999"},
        {"player_id": "20", "date": "2020-01-01", "market_value_in_eur": "2000000", "current_club_name": "Atlético Nacional", "current_club_id": "888"},
        {"player_id": "30", "date": "2020-01-01", "market_value_in_eur": "1000", "current_club_name": "Elsewhere FC", "current_club_id": "777"},
    ])
