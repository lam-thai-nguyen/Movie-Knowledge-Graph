import argparse
import re
import time
from urllib.error import HTTPError

from owlrl import DeductiveClosure, OWLRL_Semantics
from rdflib import OWL, Graph
from rdflib.plugins.stores.sparqlstore import SPARQLStore
from tabulate import tabulate

REMOTE_ENDPOINTS = {
    "wikidata": "https://query.wikidata.org/sparql",
    "dbpedia": "https://dbpedia.org/sparql",
}
REMOTE_HEADERS = {
    "User-Agent": "semantic-web-movie-kg/1.0",
}

def print_rdflib_results(results):
    if results.type == "ASK":
        print(str(results.askAnswer).lower())
        return

    if results.type == "DESCRIBE":
        serialized = results.serialize(format="turtle")
        if isinstance(serialized, bytes):
            serialized = serialized.decode()
        print(serialized, end="")
        return

    headers = [str(v) for v in results.vars] if results.vars else []
    print(tabulate(list(results), headers=headers, tablefmt="simple"))

def remote_query_with_local_links(query, links_path, target):
    links = Graph()
    links.parse(links_path, format="turtle")

    target_host = f"{target}.org"
    remote_links = [(subject, obj) for subject, predicate, obj in links
                    if predicate == OWL.sameAs and target_host in obj]

    same_as_pattern = re.compile(
        r"(?P<subject><[^>]+>)\s+"
        r"(?P<predicate>(?:owl:sameAs|"
        r"<http://www\.w3\.org/2002/07/owl#sameAs>))\s+"
        r"(?P<object>\?[A-Za-z_][A-Za-z0-9_]*)\s*\."
    )

    def replace_same_as(match):
        subject = match.group("subject")[1:-1]
        objects = [obj for linked_subject, obj in remote_links if str(linked_subject) == subject]
        if not objects:
            return "FILTER(false) ."
        values = " ".join(f"<{obj}>" for obj in objects)
        return f"VALUES {match.group('object')} {{ {values} }}"

    return same_as_pattern.sub(replace_same_as, query)

def main():
    parser = argparse.ArgumentParser(description="Interactive SPARQL CLI using rdflib")
    parser.add_argument("--rdf", help="Path to RDF file", default="output/movies.ttl")
    parser.add_argument("--ontology", help="Path to OWL ontology", default="ontology/ontology.owl")
    parser.add_argument("--links", help="Path to links or sameAs(es)", default="output/movie_links.ttl")
    parser.add_argument("-q", "--query-file", help="Path to a file containing a SPARQL query", required=True)
    parser.add_argument("--target", choices=["local", "wikidata", "dbpedia"], default="local", help="Query target (default: local RDF graph)")
    parser.add_argument("--reasoning", action="store_true", help="Enable OWL-RL inference")
    args = parser.parse_args()

    with open(args.query_file, encoding="utf-8") as f:
        query = f.read()

    if args.target == "local":
        g = Graph()
        g.parse(args.rdf, format="turtle")
        g.parse(args.ontology, format="turtle")
        g.parse(args.links, format="turtle")

        if args.reasoning:
            start = time.time()
            DeductiveClosure(OWLRL_Semantics).expand(g)
            elapsed = time.time() - start
            print(f"[timing] OWL-RL Reasoning: {elapsed:.3f}s\n")

        print_rdflib_results(g.query(query))
        return

    remote_query = remote_query_with_local_links(query, args.links, args.target)
    remote_graph = Graph(
        store=SPARQLStore(
            REMOTE_ENDPOINTS[args.target],
            returnFormat="json",
            headers=REMOTE_HEADERS,
        )
    )
    print(f"[remote] Waiting 2 seconds before querying {args.target}...")
    time.sleep(2)

    try:
        print_rdflib_results(remote_graph.query(remote_query))
    except HTTPError as error:
        if error.code == 429:
            print("[remote] Rate limit reached. Please wait and try again later.")
            return
        raise
    except ValueError as error:
        underlying_error = error.__cause__ or error.__context__
        if isinstance(underlying_error, HTTPError) and underlying_error.code == 429:
            print("[remote] Rate limit reached. Please wait and try again later.")
            return
        raise

if __name__ == "__main__":
    start = time.time()
    main()
    elapsed = time.time() - start
    print(f"\n[timing] Total time: {elapsed:.3f}s")
