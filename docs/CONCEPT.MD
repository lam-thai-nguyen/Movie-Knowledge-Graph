# Conceptualization for Movie Knowledge Graph

## 1) Define an ontology for the selected domain

Reusing classes and properties from https://schema.org/.

### Classes

- `schema:Movie` - represents a movie.
- `schema:CreativeWork` - Schema.org superclass of `schema:Movie`.
- `schema:Person` - represents an actor, director, or other crew member.
- `schema:Role` - represents an acting role with character and cast-order details.
- `schema:Genre` - represents a movie genre.
- `schema:Country` - represents a country of origin or company location.
- `schema:Language` - represents a movie language.
- `schema:Organization` - represents a production company.
- `schema:AggregateRating` - represents a movie's vote average and vote count.
- `schema:Rating` - Schema.org superclass of `schema:AggregateRating`.
- `schema:Thing` - Schema.org superclass used by people, countries, and organizations.
- `schema:Intangible` - Schema.org superclass used by roles, genres, and languages.

### Properties

- `schema:abstract` - movie synopsis or overview.
- `schema:actor` - links a movie to an actor or an acting role.
- `schema:aggregateRating` - links a movie to its aggregate rating.
- `schema:characterName` - character portrayed by an actor in a role.
- `schema:contributor` - links a movie to a non-director crew member.
- `schema:countryOfOrigin` - links a movie to its country of origin.
- `schema:datePublished` - movie release date.
- `schema:director` - links a movie to its director.
- `schema:duration` - movie runtime as an `xsd:duration`.
- `schema:genre` - links a movie to a genre.
- `schema:identifier` - TMDB and IMDb identifiers.
- `schema:inLanguage` - links a movie to a language.
- `schema:location` - links a production company to its origin country.
- `schema:name` - name or title of an entity.
- `schema:position` - cast order within a movie.
- `schema:productionCompany` - links a movie to a production company.
- `schema:ratingCount` - number of votes in an aggregate rating.
- `schema:ratingValue` - numeric value of an aggregate rating.
- `schema:roleName` - crew job title when no more specific property is used.
- `schema:sameAs` - links a movie to its TMDB and IMDb resources.

## 2) Collect relevant data for this domain

- Scrape from TMDB (The Movie Database)

## 3) Transform collected data into 4* standard

- Transform raw data (CSV) into RDF (Turtle) using URIs 

## 4) Build an ontology using OWL

- Define ontology classes, properties, restrictions, and relationships using OWL

## 5) Find and establish links to other datasets to obtain 5* standard

- Link to DBpedia, Wikidata for shared entities

## 6) Provide an interface via SPARQL endpoint to query the data

- Set up a SPARQL endpoint via Apache Jena Fuseki