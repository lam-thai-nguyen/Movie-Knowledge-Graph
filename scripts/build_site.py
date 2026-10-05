"""Build a DBpedia-style static browser for the movie knowledge graph."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from collections import Counter
from pathlib import Path
from urllib.parse import quote, urlparse

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

SCHEMA = "https://schema.org/"
SOURCE_BASE = "https://example.org/"
DEFAULT_SITE_URL = "https://lam-thai-nguyen.github.io/Movie-Knowledge-Graph/"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def local_name(uri: str) -> str:
    return uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def label(graph: Graph, node: URIRef | Literal) -> str:
    if isinstance(node, Literal):
        return str(node)
    names = list(graph.objects(node, URIRef(SCHEMA + "name")))
    if names:
        return str(names[0])
    labels = list(graph.objects(node, RDFS.label))
    return str(labels[0]) if labels else local_name(str(node))


def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return value or "resource"


def rewrite_uri(uri: str, site_url: str) -> str:
    """Move project-owned identifiers under /resource without changing external links."""
    if uri.startswith(SOURCE_BASE + "ontology/"):
        return site_url + "ontology/" + uri[len(SOURCE_BASE + "ontology/") :]
    if uri.startswith(SOURCE_BASE):
        return site_url + "resource/" + uri[len(SOURCE_BASE) :]
    return uri


def resource_path(uri: str) -> str | None:
    parsed = urlparse(uri)
    marker = "/resource/"
    if marker in parsed.path:
        return parsed.path[parsed.path.index(marker) :].rstrip("/") + "/"
    return None


def page_url(uri: str, site_url: str) -> str | None:
    rewritten = rewrite_uri(uri, site_url)
    path = resource_path(rewritten)
    return site_url.rstrip("/") + path if path else None


def object_html(graph: Graph, obj: URIRef | Literal | BNode, site_url: str) -> str:
    if isinstance(obj, Literal):
        datatype = f' <small class="datatype">{esc(local_name(str(obj.datatype)))}</small>' if obj.datatype else ""
        return f"<span>{esc(obj)}</span>{datatype}"
    if isinstance(obj, BNode):
        types = [local_name(str(value)) for value in graph.objects(obj, RDF.type) if not isinstance(value, BNode)]
        heading = ", ".join(types) or "anonymous RDF node"
        nested = []
        for predicate, value in graph.predicate_objects(obj):
            if predicate == RDF.type or isinstance(value, BNode):
                continue
            nested.append(
                f"<div><strong>{esc(local_name(str(predicate)))}</strong>: "
                f"{object_html(graph, value, site_url)}</div>"
            )
        details = "".join(nested)
        return (
            f'<details class="blank-node"><summary>{esc(heading)}</summary>'
            f"{details or '<em>No public identifier</em>'}</details>"
        )
    target = page_url(str(obj), site_url)
    text = esc(label(graph, obj))
    if target:
        return f'<a href="{esc(target)}">{text}</a> <small title="{esc(rewrite_uri(str(obj), site_url))}">↗</small>'
    return f'<a href="{esc(obj)}" rel="external noopener">{text}</a> ↗'


def shell(title: str, content: str, site_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · Movie Knowledge Graph</title>
  <link rel="stylesheet" href="{esc(site_url)}assets/style.css">
</head>
<body>
  <header class="topbar"><div class="wrap">
    <a class="brand" href="{esc(site_url)}">Movie Knowledge Graph</a>
    <nav><a href="{esc(site_url)}">Home</a><a href="{esc(site_url)}ontology/">Ontology</a><a href="{esc(site_url)}downloads/">Downloads</a></nav>
  </div></header>
  <main class="wrap">{content}</main>
  <footer class="wrap">Generated from RDF · <a href="{esc(site_url)}ontology/">Browse ontology</a></footer>
</body>
</html>"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build(args: argparse.Namespace) -> None:
    site_url = args.site_url.rstrip("/") + "/"
    site_dir = args.site_dir
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)

    graph = Graph()
    graph.parse(args.graph, format="turtle")
    ontology = Graph()
    ontology.parse(args.ontology, format="turtle")

    owned = sorted(
        {str(subject) for subject in graph.subjects() if str(subject).startswith(SOURCE_BASE)},
        key=lambda uri: (local_name(uri).casefold(), uri),
    )
    entity_types = Counter(
        str(obj) for subject in graph.subjects() for obj in graph.objects(subject, RDF.type)
        if str(subject).startswith(SOURCE_BASE)
    )

    search = []
    for uri in owned:
        rewritten = rewrite_uri(uri, site_url)
        target = page_url(uri, site_url)
        if not target:
            continue
        types = [str(obj) for obj in graph.objects(URIRef(uri), RDF.type)]
        item = {"uri": rewritten, "url": target, "label": label(graph, URIRef(uri)), "types": types}
        search.append(item)
        triples = list(graph.predicate_objects(URIRef(uri)))
        incoming = [(predicate, subject) for subject, predicate in graph.subject_predicates(URIRef(uri))]
        rows = []
        for predicate, obj in sorted(triples, key=lambda pair: (local_name(str(pair[0])).casefold(), str(pair[1]))):
            rows.append(
                f"<tr><th><a href=\"{esc(str(predicate))}\" rel=\"external noopener\">{esc(local_name(str(predicate)))}</a></th>"
                f"<td>{object_html(graph, obj, site_url)}</td></tr>"
            )
        if incoming:
            rows.append(
                '<tr><th>Referenced by</th><td>'
                + ", ".join(object_html(graph, subject, site_url) for _, subject in incoming[:50])
                + ("…" if len(incoming) > 50 else "")
                + "</td></tr>"
            )
        types_html = ", ".join(
            f'<a href="{esc(t)}" rel="external noopener">{esc(local_name(t))}</a>' for t in types
        ) or "RDF resource"
        content = f"""<div class="crumb"><a href="{esc(site_url)}">Home</a> / Resource</div>
<section class="hero"><p class="eyebrow">Resource</p><h1>{esc(label(graph, URIRef(uri)))}</h1>
<p class="uri">{esc(rewritten)}</p></section>
<div class="grid">
  <section class="card"><h2>About this resource</h2><dl>
    <dt>Type</dt><dd>{types_html}</dd>
    <dt>Canonical URI</dt><dd><code>{esc(rewritten)}</code></dd>
  </dl></section>
  <section class="card"><h2>RDF properties</h2><table><tbody>{''.join(rows)}</tbody></table></section>
</div>"""
        local_path = resource_path(rewritten)
        if not local_path:
            continue
        path = site_dir / local_path.strip("/") / "index.html"
        write(path, shell(label(graph, URIRef(uri)), content, site_url))

    write(site_dir / "search-index.json", json.dumps(search, ensure_ascii=False, indent=2))
    write(site_dir / "assets" / "style.css", CSS)
    write(site_dir / "assets" / "search.js", SEARCH_JS)

    type_links = []
    for type_uri, count in sorted(entity_types.items(), key=lambda pair: local_name(pair[0]).casefold()):
        type_links.append(f"<li><a href=\"{esc(type_uri)}\" rel=\"external noopener\">{esc(local_name(type_uri))}</a> <span>{count}</span></li>")
    home = f"""<section class="hero">
  <p class="eyebrow">Linked Open Data</p><h1>Movie Knowledge Graph</h1>
  <p>Explore movies, people, genres, organizations, ratings, and links to DBpedia and Wikidata.</p>
  <input id="search" type="search" placeholder="Search {len(search):,} resources…" autocomplete="off">
  <div id="results" class="results"></div>
</section>
<div class="grid">
  <section class="card"><h2>Dataset</h2><dl><dt>Triples</dt><dd>{len(graph):,}</dd><dt>Resources</dt><dd>{len(search):,}</dd><dt>Source</dt><dd>TMDB, DBpedia, Wikidata</dd></dl></section>
  <section class="card"><h2>Resource types</h2><ul class="plain">{''.join(type_links)}</ul></section>
</div>
<p class="notice">This is a pre-generated static browser. The original Turtle and OWL files are available from the <a href="{esc(site_url)}downloads/">downloads</a> page.</p>
<script src="{esc(site_url)}assets/search.js"></script>"""
    write(site_dir / "index.html", shell("Home", home, site_url))

    classes = sorted(str(s) for s in ontology.subjects(RDF.type, OWL.Class))
    properties = sorted(
        str(s) for s in ontology.subjects() if (s, RDF.type, OWL.ObjectProperty) in ontology or (s, RDF.type, OWL.DatatypeProperty) in ontology
    )
    ontology_rows = "".join(
        f'<li><a href="{esc(site_url)}ontology/class/{esc(local_name(uri))}/">{esc(local_name(uri))}</a></li>' for uri in classes
    )
    property_rows = "".join(
        f'<li><a href="{esc(site_url)}ontology/property/{esc(local_name(uri))}/">{esc(local_name(uri))}</a></li>' for uri in properties
    )
    ontology_home = f"""<section class="hero"><p class="eyebrow">Vocabulary</p><h1>Ontology browser</h1>
<p>{esc(next(iter(ontology.objects(None, RDFS.comment)), "Movie Knowledge Graph ontology"))}</p></section>
<div class="grid"><section class="card"><h2>Classes</h2><ul class="plain">{ontology_rows}</ul></section>
<section class="card"><h2>Properties</h2><ul class="plain">{property_rows}</ul></section></div>
<p class="notice"><a href="{esc(site_url)}downloads/ontology.owl">Download ontology.owl</a></p>"""
    write(site_dir / "ontology" / "index.html", shell("Ontology", ontology_home, site_url))
    for kind, uris in (("class", classes), ("property", properties)):
        for uri in uris:
            node = URIRef(uri)
            details = []
            for predicate, obj in ontology.predicate_objects(node):
                if predicate in (RDF.type, OWL.disjointWith):
                    continue
                details.append(f"<tr><th>{esc(local_name(str(predicate)))}</th><td>{object_html(ontology, obj, site_url)}</td></tr>")
            body = f"""<div class="crumb"><a href="{esc(site_url)}ontology/">Ontology</a> / {esc(kind)}</div>
<section class="hero"><p class="eyebrow">{esc(kind.title())}</p><h1>{esc(local_name(uri))}</h1><p class="uri">{esc(uri)}</p></section>
<section class="card"><table><tbody>{''.join(details) or '<tr><td>No annotations available.</td></tr>'}</tbody></table></section>"""
            write(site_dir / "ontology" / kind / slug(local_name(uri)) / "index.html", shell(local_name(uri), body, site_url))

    downloads = site_dir / "downloads"
    downloads.mkdir()
    for source in (args.graph, args.raw_graph, args.links, args.ontology):
        shutil.copy2(source, downloads / Path(source).name)
    write(downloads / "index.html", shell("Downloads", "<section class=\"hero\"><h1>Downloads</h1><p>RDF and OWL source files used to build this site.</p></section><section class=\"card\"><ul class=\"plain\">" + "".join(f'<li><a href="{esc(site_url)}downloads/{esc(Path(source).name)}">{esc(Path(source).name)}</a></li>' for source in (args.graph, args.raw_graph, args.links, args.ontology)) + "</ul></section>", site_url))
    print(f"Built {len(search):,} resource pages and {len(classes) + len(properties):,} ontology pages in {site_dir}")


CSS = """*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:#172b4d;font:16px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.wrap{max-width:1120px;margin:auto;padding:0 24px}.topbar{background:#172b4d;color:#fff;padding:16px 0}.topbar .wrap{display:flex;justify-content:space-between;gap:24px;align-items:center}.brand,nav a{color:#fff;text-decoration:none}.brand{font-weight:700}nav{display:flex;gap:20px}.hero{padding:64px 0 32px}.eyebrow{color:#526581;text-transform:uppercase;letter-spacing:.12em;font-size:.8rem;font-weight:700}.hero h1{font-size:clamp(2rem,5vw,4rem);line-height:1.1;margin:.2em 0}.uri,code{color:#526581;overflow-wrap:anywhere;font-size:.9rem}input{width:100%;max-width:680px;padding:14px;border:1px solid #bcc7d6;border-radius:8px;font:inherit;margin-top:20px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}.card{background:#fff;border:1px solid #d9e1ea;border-radius:10px;padding:24px;margin:0 0 24px;overflow:auto}h2{margin-top:0}dl{display:grid;grid-template-columns:max-content 1fr;gap:8px 24px}dt{font-weight:700}dd{margin:0}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e6ebf0;padding:12px 8px}th{width:30%;color:#526581}a{color:#0969da}.plain{list-style:none;padding:0;margin:0}.plain li{padding:7px 0;border-bottom:1px solid #e6ebf0}.plain span{float:right;color:#526581}.crumb{padding-top:28px;color:#526581}.notice{background:#e8f1fb;padding:16px;border-radius:8px;margin:24px 0 48px}.results{background:#fff;border-radius:8px;margin-top:8px;max-width:680px}.results a{display:block;padding:10px 14px;border-bottom:1px solid #e6ebf0;text-decoration:none}.results small{color:#526581}.blank-node{background:#f6f8fa;border:1px solid #d9e1ea;border-radius:6px;padding:4px 8px}.blank-node div{margin:4px 0}footer{color:#526581;padding:32px 24px}"""

SEARCH_JS = """const input=document.querySelector('#search');const results=document.querySelector('#results');if(input){fetch((document.querySelector('base')||{}).href||'search-index.json').then(r=>r.json()).then(items=>{input.addEventListener('input',()=>{const q=input.value.trim().toLowerCase();if(!q){results.innerHTML='';return}const found=items.filter(x=>(x.label+' '+x.uri).toLowerCase().includes(q)).slice(0,20);results.innerHTML=found.map(x=>`<a href="${x.url}">${x.label}<br><small>${x.uri}</small></a>`).join('')||'<small>No matching resources.</small>'})})}"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("output/inferred_graph_clean.ttl"))
    parser.add_argument("--raw-graph", type=Path, default=Path("output/movies.ttl"))
    parser.add_argument("--links", type=Path, default=Path("output/movie_links.ttl"))
    parser.add_argument("--ontology", type=Path, default=Path("ontology/ontology.owl"))
    parser.add_argument("--site-dir", type=Path, default=Path("_site"))
    parser.add_argument("--site-url", default=DEFAULT_SITE_URL)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
