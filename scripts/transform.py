import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

SCHEMA = Namespace("https://schema.org/")
KG = Namespace("https://example.org/ontology/")
DEFAULT_BASE_URI = "https://example.org/"


def read_csv(data_dir: Path, filename: str) -> list[dict[str, str]]:
    """Read a CSV file from the data directory."""
    path = data_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required CSV file not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def uri(base_uri: str, entity_type: str, identifier: str) -> URIRef:
    """Create a stable URI for an identified RDF entity."""
    return URIRef(f"{base_uri.rstrip('/')}/{entity_type}/{quote(identifier, safe='')}")


def non_empty(value: str | None) -> str | None:
    """Return a stripped value, or None for empty input."""
    value = (value or "").strip()
    return value or None


def add_literal(graph: Graph, subject: URIRef, predicate: URIRef, value: str | None) -> None:
    """Add a plain literal triple when the value is not empty."""
    value = non_empty(value)
    if value is not None:
        graph.add((subject, predicate, Literal(value)))


def add_integer(graph: Graph, subject: URIRef, predicate: URIRef, value: str | None) -> None:
    """Add an xsd:integer triple when the value is not empty."""
    value = non_empty(value)
    if value is not None:
        graph.add((subject, predicate, Literal(int(value), datatype=XSD.integer)))


def add_duration(graph: Graph, subject: URIRef, predicate: URIRef, value: str | None) -> None:
    """Add an xsd:duration triple from a runtime expressed in minutes."""
    value = non_empty(value)
    if value is not None:
        graph.add((subject, predicate, Literal(f"PT{int(value)}M", datatype=XSD.duration)))


def add_decimal(graph: Graph, subject: URIRef, predicate: URIRef, value: str | None) -> None:
    """Add an xsd:decimal triple when the value is not empty."""
    value = non_empty(value)
    if value is not None:
        graph.add((subject, predicate, Literal(Decimal(value), datatype=XSD.decimal)))


def add_date(graph: Graph, subject: URIRef, predicate: URIRef, value: str | None) -> None:
    """Add an xsd:date triple after validating the ISO date."""
    value = non_empty(value)
    if value is not None:
        date.fromisoformat(value)
        graph.add((subject, predicate, Literal(value, datatype=XSD.date)))


def add_person(graph: Graph, person_uri: URIRef, name: str | None) -> None:
    """Declare a person resource and add its name when available."""
    graph.add((person_uri, RDF.type, SCHEMA.Person))
    add_literal(graph, person_uri, SCHEMA.name, name)


def transform(data_dir: Path, output_path: Path, base_uri: str) -> Graph:
    """Transform all movie CSV files into an RDF graph and serialize it."""
    graph = Graph()
    graph.bind("schema", SCHEMA)
    graph.bind("kg", KG)
    graph.bind("rdf", RDF)
    graph.bind("xsd", XSD)

    # Load data: [row1, row2, ...] each row is a dict
    movies = read_csv(data_dir, "movies.csv")
    genres = read_csv(data_dir, "genres.csv")
    companies = read_csv(data_dir, "companies.csv")
    countries = read_csv(data_dir, "countries.csv")
    languages = read_csv(data_dir, "languages.csv")
    cast_rows = read_csv(data_dir, "cast.csv")
    crew_rows = read_csv(data_dir, "crew.csv")
    movie_genres = read_csv(data_dir, "movie_genres.csv")
    movie_companies = read_csv(data_dir, "movie_companies.csv")
    movie_countries = read_csv(data_dir, "movie_countries.csv")
    movie_languages = read_csv(data_dir, "movie_languages.csv")

    # transform 1. :genre_id (10749) schema:name genre (Romance) 
    for row in genres:
        subject = uri(base_uri, "genre", row["id"])
        graph.add((subject, RDF.type, SCHEMA.Genre))
        add_literal(graph, subject, SCHEMA.name, row.get("name"))

    # transform 2. :country_code (US) schema:name country_name (United States)
    for row in countries:
        subject = uri(base_uri, "country", row["country_code"])
        graph.add((subject, RDF.type, SCHEMA.Country))
        add_literal(graph, subject, SCHEMA.name, row.get("name"))

    # transform 3. :language_code (en) schema:name language (English) 
    for row in languages:
        subject = uri(base_uri, "language", row["language_code"])
        graph.add((subject, RDF.type, SCHEMA.Language))
        add_literal(graph, subject, SCHEMA.name, row.get("name"))

    # transform 4. :company_id (420) schema:name company_name (Marvel Studios)
    # transform 5. :company_id (420) schema:location :country
    for row in companies:
        subject = uri(base_uri, "company", row["id"])
        graph.add((subject, RDF.type, SCHEMA.Organization))
        add_literal(graph, subject, SCHEMA.name, row.get("name"))
        country_code = non_empty(row.get("origin_country"))
        if country_code:
            graph.add((subject, SCHEMA.location, uri(base_uri, "country", country_code)))

    # transform 6. :movie_id (969681) schema:... corresponding_literal
    for row in movies:
        subject = uri(base_uri, "movie", row["id"])
        graph.add((subject, RDF.type, SCHEMA.Movie))
        add_literal(graph, subject, SCHEMA.identifier, row.get("id"))
        add_literal(graph, subject, SCHEMA.name, row.get("title"))
        add_literal(graph, subject, SCHEMA.abstract, row.get("overview"))
        add_date(graph, subject, SCHEMA.datePublished, row.get("release_date"))
        add_duration(graph, subject, SCHEMA.duration, row.get("runtime"))
        rating_value = non_empty(row.get("vote_average"))
        rating_count = non_empty(row.get("vote_count"))
        if rating_value or rating_count:
            rating = BNode()
            graph.add((subject, SCHEMA.aggregateRating, rating))
            graph.add((rating, RDF.type, SCHEMA.AggregateRating))
            add_decimal(graph, rating, SCHEMA.ratingValue, rating_value)
            add_integer(graph, rating, SCHEMA.ratingCount, rating_count)

        language_code = non_empty(row.get("original_language"))
        if language_code:
            graph.add((subject, SCHEMA.inLanguage, uri(base_uri, "language", language_code)))

        imdb_id = non_empty(row.get("imdb_id"))
        if imdb_id:
            graph.add((subject, SCHEMA.identifier, Literal(imdb_id)))
            imdb_page = URIRef(f"https://www.imdb.com/title/{quote(imdb_id, safe='')}/")
            graph.add((subject, SCHEMA.sameAs, imdb_page))
            graph.add((subject, KG.imdbPage, imdb_page))
        graph.add((subject, SCHEMA.sameAs, URIRef(f"https://www.themoviedb.org/movie/{quote(row['id'], safe='')}")))

    # transform 7. :movie_id (1368337) schema:actor :person_id (1136406)
    seen_people: set[str] = set()
    for row in cast_rows:
        movie = uri(base_uri, "movie", row["movie_id"])
        person = uri(base_uri, "person", row["person_id"])
        graph.add((movie, SCHEMA.actor, person))
        if row["person_id"] not in seen_people:
            add_person(graph, person, row.get("person_name"))
            seen_people.add(row["person_id"])

        character = non_empty(row.get("character"))
        order = non_empty(row.get("order"))
        if character or order:
            role = BNode()
            graph.add((movie, SCHEMA.actor, role))
            graph.add((role, RDF.type, SCHEMA.Role))
            graph.add((role, SCHEMA.actor, person))
            add_literal(graph, role, SCHEMA.characterName, character)
            add_integer(graph, role, SCHEMA.position, order)

    for row in crew_rows:
        movie = uri(base_uri, "movie", row["movie_id"])
        person = uri(base_uri, "person", row["person_id"])
        job = non_empty(row.get("job"))
        if job and job.casefold() == "director":
            graph.add((movie, SCHEMA.director, person))
        else:
            graph.add((movie, SCHEMA.contributor, person))
            if job:
                graph.add((person, SCHEMA.roleName, Literal(job)))
        if row["person_id"] not in seen_people:
            add_person(graph, person, row.get("person_name"))
            seen_people.add(row["person_id"])

    # transform 8. :movie_id (1368337) schema:genre :genre_id (12, 14, or 28)
    for row in movie_genres:
        graph.add((
            uri(base_uri, "movie", row["movie_id"]),
            SCHEMA.genre,
            uri(base_uri, "genre", row["genre_id"]),
        ))

    # transform 9. :movie_id (1368337) schema:productionCompany :company_id
    for row in movie_companies:
        graph.add((
            uri(base_uri, "movie", row["movie_id"]),
            SCHEMA.productionCompany,
            uri(base_uri, "company", row["company_id"]),
        ))

    # transform 10. similar to transforms 8 and 9
    for row in movie_countries:
        graph.add((
            uri(base_uri, "movie", row["movie_id"]),
            SCHEMA.countryOfOrigin,
            uri(base_uri, "country", row["country_code"]),
        ))

    # transform 11. similar to transforms 8 and 9
    for row in movie_languages:
        graph.add((
            uri(base_uri, "movie", row["movie_id"]),
            SCHEMA.inLanguage,
            uri(base_uri, "language", row["language_code"]),
        ))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=output_path, format="turtle")
    return graph


def main() -> None:
    """Parse command-line arguments and run the CSV-to-RDF transformation."""
    parser = argparse.ArgumentParser(description="Transform movie CSV files into RDF/Turtle.")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("output/movies.ttl"))
    parser.add_argument("--base-uri", default=DEFAULT_BASE_URI)
    args = parser.parse_args()

    try:
        graph = transform(args.data_dir, args.output, args.base_uri)
    except (FileNotFoundError, KeyError, ValueError, InvalidOperation) as error:
        parser.error(str(error))
    print(f"🟢 Created {args.output} with {len(graph)} triples.")


if __name__ == "__main__":
    main()
