from rapidfuzz import process

CITY_TO_IATA = {
    "mumbai": "BOM",
    "delhi": "DEL",
    "bengaluru": "BLR",
    "bangalore": "BLR",
    "hyderabad": "HYD",
    "goa": "GOI",
}


def to_iata(city_name: str) -> str | None:
    if not city_name:
        return None
    name = city_name.strip().lower()
    if name in CITY_TO_IATA:
        return CITY_TO_IATA[name]
    match = process.extractOne(name, CITY_TO_IATA.keys(), score_cutoff=70)
    if match:
        return CITY_TO_IATA[match[0]]
    return None
