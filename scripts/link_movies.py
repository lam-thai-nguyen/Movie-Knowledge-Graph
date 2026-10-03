"""Find Wikidata and DBpedia links for local movie resources."""

import argparse
import csv
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, XSD

SCHEMA = Namespace("https://schema.org/")
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{item}.json"
USER_AGENT = "semantic-web-movie-linker/1.0 (educational project)"
MOVIE_ID_PATTERN = re.compile(r"/movie/([^/?#]+)$")
IMDB_ID_PATTERN = re.compile(r"^tt\d+$")


def query_wikidata(query: str, session: requests.Session) -> list[dict[str, str]]:
    response = session.get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        timeout=30,
    )

    response.raise_for_status()
    return [
        {key: value["value"] for key, value in binding.items() if "value" in value}
        for binding in response.json()["results"]["bindings"]
    ]

def sparql_string(value: str) -> str:
    """Escape a value for a SPARQL string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

def identifier_candidates(tmdb_id: str | None, imdb_id: str | None, session: requests.Session) -> list[dict[str, str]]:
    clauses = []
    if tmdb_id:
        clauses.append(f'{{ ?item wdt:P4947 {sparql_string(tmdb_id)} . }}')
    if imdb_id:
        clauses.append(f'{{ ?item wdt:P345 {sparql_string(imdb_id)} . }}')
    if not clauses:
        return []

    query = f"""
        SELECT DISTINCT ?item ?itemLabel ?tmdb ?imdb ?releaseDate WHERE {{
            {" UNION ".join(clauses)}
            OPTIONAL {{ ?item wdt:P4947 ?tmdb . }}
            OPTIONAL {{ ?item wdt:P345 ?imdb . }}
            OPTIONAL {{ ?item wdt:P577 ?releaseDate . }}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
    """
    return query_wikidata(query, session)

def title_date_candidates(title: str, release_date: str | None, session: requests.Session) -> list[dict[str, str]]:
    year_filter = ""
    if release_date:
        year_filter = f"FILTER(YEAR(?releaseDate) = {release_date[:4]})"

    query = f"""
        SELECT DISTINCT ?item ?itemLabel ?releaseDate WHERE {{
            ?item rdfs:label {sparql_string(title)}@en ;
                  wdt:P577 ?releaseDate .
            {year_filter}
            SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
    """
    return query_wikidata(query, session)

def wikidata_id(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]

def dbpedia_uri(item: str, session: requests.Session) -> str | None:
    response = session.get(
        WIKIDATA_ENTITY.format(item=wikidata_id(item)),
        timeout=30,
    )
    response.raise_for_status()
    entity = response.json()["entities"][wikidata_id(item)]
    sitelink = entity.get("sitelinks", {}).get("enwiki")
    if not sitelink:
        return None
    return "http://dbpedia.org/resource/" + quote(
        sitelink["title"].replace(" ", "_"),
        safe="_()!':,-",
    )

def local_movies(graph: Graph) -> list[dict[str, str | None]]:
    movies = []
    for subject in graph.subjects(RDF.type, SCHEMA.Movie):
        identifiers = [str(value) for value in graph.objects(subject, SCHEMA.identifier)]
        tmdb_match = MOVIE_ID_PATTERN.search(str(subject))
        imdb_id = next((value for value in identifiers if IMDB_ID_PATTERN.fullmatch(value)), None)
        release = next(graph.objects(subject, SCHEMA.datePublished), None)
        movies.append(
            {
                "local_uri": str(subject),
                "tmdb_id": tmdb_match.group(1) if tmdb_match else None,
                "imdb_id": imdb_id,
                "title": str(next(graph.objects(subject, SCHEMA.name), "")),
                "release_date": str(release) if release else None,
            }
        )
    return movies

def release_year(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(date.fromisoformat(value[:10]).year)
    except ValueError:
        return value[:4]

def score_candidate(movie: dict[str, str | None], candidate: dict[str, str]) -> tuple[float, str]:
    identifier_matches = []
    if movie["tmdb_id"] and candidate.get("tmdb") == movie["tmdb_id"]:
        identifier_matches.append("tmdb_id")
    if movie["imdb_id"] and candidate.get("imdb") == movie["imdb_id"]:
        identifier_matches.append("imdb_id")
    if identifier_matches:
        local_year = release_year(movie["release_date"])
        wikidata_year = release_year(candidate.get("releaseDate"))
        if local_year and wikidata_year and local_year == wikidata_year:
            return 1.0, "+".join(identifier_matches + ["release_year"])
        if local_year and wikidata_year and local_year != wikidata_year:
            return 0.0, "+".join(identifier_matches + ["release_year_mismatch"])
        return 0.5, "+".join(identifier_matches + ["release_year_missing"])

    matched_by = []
    if movie["title"].casefold() == candidate.get("itemLabel", "").casefold():
        matched_by.append("title")
    if release_year(movie["release_date"]) == release_year(candidate.get("releaseDate")):
        matched_by.append("release_year")
    return (0.9 if len(matched_by) == 2 else 0.5), "+".join(matched_by)

def link_movies(input_path: Path, candidates_path: Path, links_path: Path, delay: float) -> tuple[int, int]:
    graph = Graph()
    graph.parse(input_path, format="turtle")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    candidate_rows = []
    approved_graph = Graph()
    approved_graph.bind("owl", "http://www.w3.org/2002/07/owl#")
    owl_same_as = URIRef("http://www.w3.org/2002/07/owl#sameAs")

    for movie in local_movies(graph):
        # movie: [{'local_uri': '...', 'tmdb_id': '...', 'imdb_id': '...', 'title': '...', 'release_date': '...'}]
        candidates = identifier_candidates(movie["tmdb_id"], movie["imdb_id"], session)
        # candiates: [{'item': '...', 'tmdb': '...', 'imdb': '...', 'releaseDate': '...', 'itemLabel': '...'}]
        search_method = "identifier"
        if not candidates and movie["title"]:
            candidates = title_date_candidates(movie["title"], movie["release_date"], session)
            search_method = "title+release_year"

        unique_candidates = {}
        local_year = release_year(movie["release_date"])
        for candidate in candidates:
            current = unique_candidates.get(candidate["item"])
            candidate_year_matches = local_year and local_year == release_year(candidate.get("releaseDate"))
            current_year_matches = current and local_year == release_year(current.get("releaseDate"))
            if current is None or (candidate_year_matches and not current_year_matches):
                unique_candidates[candidate["item"]] = candidate
        for candidate in unique_candidates.values():
            # candidate: {'item': '...', 'tmdb': '...', 'imdb': '...', 'releaseDate': '...', 'itemLabel': '...'}
            score, matched_by = score_candidate(movie, candidate)
            wikidata = candidate["item"]
            dbpedia = dbpedia_uri(wikidata, session)
            if score == 1.0 and dbpedia:
                status = "approved"
            elif "release_year_mismatch" in matched_by:
                status = "rejected"
            else:
                status = "review"
            candidate_rows.append(
                {
                    "local_uri": movie["local_uri"],
                    "tmdb_id": movie["tmdb_id"] or "",
                    "imdb_id": movie["imdb_id"] or "",
                    "title": movie["title"] or "",
                    "release_date": movie["release_date"] or "",
                    "wikidata_uri": wikidata,
                    "wikidata_label": candidate.get("itemLabel", ""),
                    "wikidata_release_date": candidate.get("releaseDate", ""),
                    "dbpedia_uri": dbpedia or "",
                    "search_method": search_method,
                    "matched_by": matched_by,
                    "score": f"{score:.2f}",
                    "status": status,
                }
            )
            if status == "approved":
                approved_graph.add((URIRef(movie["local_uri"]), owl_same_as, URIRef(wikidata)))
                approved_graph.add((URIRef(movie["local_uri"]), owl_same_as, URIRef(dbpedia)))
            time.sleep(delay)
        time.sleep(delay)

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    with candidates_path.open("w", newline="", encoding="utf-8") as output:
        fieldnames = list(candidate_rows[0]) if candidate_rows else [
            "local_uri", "tmdb_id", "imdb_id", "title", "release_date",
            "wikidata_uri", "wikidata_label", "wikidata_release_date",
            "dbpedia_uri", "search_method", "matched_by", "score", "status",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candidate_rows)

    links_path.parent.mkdir(parents=True, exist_ok=True)
    approved_graph.serialize(destination=links_path, format="turtle")
    return len(candidate_rows), len(approved_graph)


def main() -> None:
    parser = argparse.ArgumentParser(description="Link local movies to Wikidata and DBpedia.")
    parser.add_argument("--input", type=Path, default=Path("output/movies.ttl"))
    parser.add_argument("--candidates", type=Path, default=Path("output/movie_candidates.csv"))
    parser.add_argument("--links", type=Path, default=Path("output/movie_links.ttl"))
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()

    try:
        candidates, triples = link_movies(
            args.input,
            args.candidates,
            args.links,
            max(args.delay, 0),
        )
    except (OSError, requests.RequestException, KeyError, ValueError) as error:
        parser.error(str(error))
    print(f"Created {args.candidates} with {candidates} candidates.")
    print(f"Created {args.links} with {triples} approved link triples.")


if __name__ == "__main__":
    main()
