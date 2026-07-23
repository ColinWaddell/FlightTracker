import csv
import json
import urllib.request

url = "https://ourairports.com/airports.csv"

OVERRIDES = {
    "LTN": {
        "country_name": "United Kingdom",
        "municipality": "Luton, Bedfordshire",
        "name": "London Luton Airport",
    }
}

with urllib.request.urlopen(url) as r:
    rows = csv.DictReader(line.decode("utf-8") for line in r)

    airports = {}
    ica0 = {}

    for row in rows:
        if row["iata_code"] and len(row["iata_code"]) == 3:
            iata = row["iata_code"]
            ica0[row["icao_code"]] = iata

            if iata in OVERRIDES:
                airports[iata] = OVERRIDES[iata]
            else:
                airports[iata] = {
                    "name": row["name"].replace("–", "-"),
                    "country_name": row["country_name"],
                    "municipality": row["municipality"],
                }


with open("airports.json", "w", encoding="utf-8") as f:
    json.dump(airports, f, indent=2, sort_keys=True, ensure_ascii=False)

with open("icao_to_iata.json", "w", encoding="utf-8") as f:
    json.dump(ica0, f, indent=2, sort_keys=True, ensure_ascii=False)
