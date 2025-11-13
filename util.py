import requests

def get_sunset():
    endpoint = "https://api.sunrise-sunset.org/json"
    with requests.Session() as session:
        response = session.get(endpoint, params={"lat": 510507.7, "lng": 102245.4, "tzid": "Europe/Berlin"})
        data = response.json()
        return data["results"]["sunset"]
