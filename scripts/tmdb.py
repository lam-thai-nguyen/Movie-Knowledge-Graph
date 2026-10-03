import csv
import os

import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    raise RuntimeError("Set the TMDB_API_KEY environment variable before running this script.")
BASE_URL = "https://api.themoviedb.org/3"

PAGES = [1,2,3,4,5]  # 20 movies per page
OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

# Info retrieval
movies = []             # id, imdb_id, title, overview, original_language, release_date, runtime, vote_average, vote_count
genres = {}             # id -> name
movie_genres = []       # movie_id, genre_id
companies = {}          # id -> (name, origin_country)
movie_companies = []    # movie_id, company_id
countries = {}          # iso_3166_1 -> name
movie_countries = []    # movie_id, iso_3166_1
languages = {}          # iso_639_1 -> name
movie_languages = []    # movie_id, iso_639_1
cast_rows = []          # movie_id, person_id, person_name, character, order
crew_rows = []          # movie_id, person_id, person_name, job

for page in PAGES:
    print(f"🟠 Requesting for {BASE_URL}/movie/popular (page {page}) ...")
    resp = requests.get(f"{BASE_URL}/movie/popular", params={"api_key": TMDB_API_KEY, "page": page}, timeout=10)
    results = resp.json()["results"]
    print("🟢 Success")

    print("🟠 Retrieving information ...")
    for m in results:
        movie_id = m["id"]
        details = requests.get(f"{BASE_URL}/movie/{movie_id}", params={"api_key": TMDB_API_KEY}, timeout=10).json()
        credits = requests.get(f"{BASE_URL}/movie/{movie_id}/credits", params={"api_key": TMDB_API_KEY}, timeout=10).json()

        movies.append({
            "id": movie_id,
            "imdb_id": details.get("imdb_id"),
            "title": details.get("title"),
            "overview": details.get("overview"),
            "original_language": details.get("original_language"),
            "release_date": details.get("release_date"),
            "runtime": details.get("runtime"),
            "vote_average": details.get("vote_average"),
            "vote_count": details.get("vote_count"),
        })

        for g in details.get("genres", []):
            genres[g["id"]] = g["name"]
            movie_genres.append({"movie_id": movie_id, "genre_id": g["id"]})

        for c in details.get("production_companies", []):
            companies[c["id"]] = (c["name"], c.get("origin_country"))
            movie_companies.append({"movie_id": movie_id, "company_id": c["id"]})

        for c in details.get("production_countries", []):
            countries[c["iso_3166_1"]] = c["name"]
            movie_countries.append({"movie_id": movie_id, "country_code": c["iso_3166_1"]})

        for l in details.get("spoken_languages", []):
            languages[l["iso_639_1"]] = l.get("english_name") or l.get("name")
            movie_languages.append({"movie_id": movie_id, "language_code": l["iso_639_1"]})

        for c in credits["cast"][:10]:
            cast_rows.append({
                "movie_id": movie_id,
                "person_id": c["id"],
                "person_name": c["name"],
                "character": c["character"],
                "order": c.get("order"),
            })

        for c in credits["crew"]:
            if c["job"] == "Director":
                crew_rows.append({"movie_id": movie_id, "person_id": c["id"], "person_name": c["name"], "job": c["job"]})

    print(f"🟢 Successfully crawled {len(movies)} movies in total")

def write_csv(filename, fieldnames, rows):
    cleaned_rows = []

    for row in rows:
        cleaned_row = dict(row)
        for fieldname in fieldnames:
            value = cleaned_row.get(fieldname)
            if isinstance(value, str):
                cleaned_row[fieldname] = value.strip()
            elif value is None:
                cleaned_row[fieldname] = ""
        cleaned_rows.append(cleaned_row)

    with open(os.path.join(OUT_DIR, filename), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned_rows)
        print(f"📍 Created: {OUT_DIR}/{filename}")


write_csv(
    "movies.csv",
    [
        "id", "imdb_id", "title", "overview", "original_language",
        "release_date", "runtime", "vote_average", "vote_count"
    ],
    movies
)

write_csv(
    "genres.csv", ["id", "name"],
    [{"id": k, "name": v} for k, v in genres.items()]
)
write_csv("movie_genres.csv", ["movie_id", "genre_id"], movie_genres)

write_csv(
    "companies.csv", ["id", "name", "origin_country"],
    [{"id": k, "name": v[0], "origin_country": v[1]} for k, v in companies.items()]
)
write_csv("movie_companies.csv", ["movie_id", "company_id"], movie_companies)

write_csv(
    "countries.csv", ["country_code", "name"],
    [{"country_code": k, "name": v} for k, v in countries.items()]
)
write_csv("movie_countries.csv", ["movie_id", "country_code"], movie_countries)

write_csv(
    "languages.csv", ["language_code", "name"],
    [{"language_code": k, "name": v} for k, v in languages.items()]
)
write_csv("movie_languages.csv", ["movie_id", "language_code"], movie_languages)

write_csv("cast.csv", ["movie_id", "person_id", "person_name", "character", "order"], cast_rows)
write_csv("crew.csv", ["movie_id", "person_id", "person_name", "job"], crew_rows)
