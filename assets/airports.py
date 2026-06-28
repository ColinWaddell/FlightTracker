import csv
import json
import urllib.request

url = "https://ourairports.com/airports.csv"

with urllib.request.urlopen(url) as r:
    rows = csv.DictReader(line.decode("utf-8") for line in r)

    airports = {
        row["iata_code"]: row["name"]
        for row in rows
        if row["iata_code"] and len(row["iata_code"]) == 3
    }

with open("airports.json", "w", encoding="utf-8") as f:
    json.dump(airports, f, indent=2, sort_keys=True)
