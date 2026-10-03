# Copilot Instructions

## Project scope

This project builds Linked Open Data (LOD) for the movie domain using a Knowledge
Graph. Refer to `README.MD` and `docs/CONCEPT.MD` as the authoritative project-scope documents.

The planned technology and data stack is:

- **Ontology:** Reuse classes and properties from [schema.org](https://schema.org/),
  including movies, people, countries, organizations, ratings, actors, directors,
  genres, production companies, publication dates, and awards.
- **Data source:** Scrape relevant movie data from TMDB (The Movie Database).
- **LOD transformation:** Convert collected CSV data into RDF in Turtle format,
  using stable URIs.
- **Dataset linking:** Link shared entities to DBpedia and Wikidata to support the
  five-star Linked Open Data standard.
- **Query interface:** Provide the data through a SPARQL endpoint using Apache
  Jena Fuseki.
- **Environment:** Use the Python interpreter as 
`/home/thai/miniconda3/envs/semantic-web/bin/python3`.
Use pip as `/home/thai/miniconda3/envs/semantic-web/bin/pip3`.
Initial environment setup by `pip3 install -r requirements.txt`
Install additional packages by `pip3 install`. 
Remember to `pip3 freeze > requirements.txt` after installing packages.

## Response formatting

Start every answer after a line of `====================`.