from datetime import datetime, timedelta


def mock_search(source_iata: str, dest_iata: str, depart_at: datetime):
    base_time = depart_at.replace(minute=0, second=0, microsecond=0)
    options = []
    airlines = [("AI", "Air India"), ("6E", "IndiGo"), ("UK", "Vistara")]
    prices = [5800, 6100, 6400]
    for i, (code, name) in enumerate(airlines):
        dep = base_time + timedelta(minutes=60 * i + 30)
        arr = dep + timedelta(hours=2, minutes=5)
        options.append({
            "id": f"{code}{100+i}",
            "airline": name,
            "flight_no": f"{code} {100+i}",
            "depart": dep.isoformat(),
            "arrive": arr.isoformat(),
            "duration_min": 125,
            "price": prices[i],
            "currency": "INR",
        })
    return options
