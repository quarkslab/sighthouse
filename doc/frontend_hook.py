from pathlib import Path
import mkdocs.plugins
from mkdocs.structure.toc import AnchorLink
import markdown
import logging
import html
from griffe import Docstring
from griffe._internal.docstrings.models import (
    DocstringSectionText,
    DocstringSectionParameters,
    DocstringSectionReturns,
)

from sighthouse.frontend.restapi import FrontendRestAPI

log = logging.getLogger("mkdocs")


def convert_markdown_to_html(markdown_content):
    # Use the markdown library to convert to HTML
    html_content = markdown.markdown(markdown_content)
    # Hacky way of adding the same look to code blocks
    html_content = html_content.replace("<code>", '<div class="highlight"><pre>')
    html_content = html_content.replace("</code>", "</pre></div>")
    return html_content


def generate_api_description(page):
    # Create a fake frontend API to trigger routes registration
    frontend = FrontendRestAPI(None, "", None, [], [], None)
    # Accessing private flask member of FrontendRestAPI class
    app = frontend.__dict__.get("_FrontendRestAPI__app")
    if app is None:
        log.error("Fail to get app from frontend")
        return ""

    html_doc = [
        "<style>",
        ".container { margin: 20px; }",
        ".endpoint { border: 1px solid #d8d8d8; border-radius: 6px; margin: 15px 0; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }",
        ".summary { padding: 12px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; }",
        ".method { color: white; border-radius: 4px; padding: 4px 8px; font-weight: bold; font-size: 12px; }",
        ".method.GET { background: #61affe; }",
        ".method.POST { background: #49cc90; }",
        ".method.PUT { background: #fca130; }",
        ".method.DELETE { background: #f93e3e; }",
        ".details { display: none; padding: 15px; border-top: 1px solid #eee; }",
        "table { width: 100%; border-collapse: collapse; margin-top: 10px; }",
        "th, td { padding: 8px 10px; border: 1px solid #ddd; text-align: left; }",
        "th { background: #fafafa; }",
        "p.description { margin: 8px 0; }",
        "</style>",
        "<script>",
        "function toggleDetails(id) {",
        "  var section = document.getElementById(id);",
        "  section.style.display = (section.style.display === 'block') ? 'none' : 'block';",
        "}",
        "</script>",
        "<div class='container'>",
    ]

    for route_id, route in enumerate(app.url_map.iter_rules()):
        if not route.rule.startswith("/api/"):
            log.debug(f"Skipping non API route {route.endpoint}")
            continue

        func = app.view_functions.get(route.endpoint)
        if func is None:
            log.debug(f"Count not find function callback for {route.endpoint}")
            continue

        methods = [m for m in route.methods if m not in ("HEAD", "OPTIONS")]
        if not methods:
            continue

        html_doc.append(f"<div class='endpoint' id='__endpoint_{route_id}'>")

        # Add item to ToC
        if page.toc and page.toc.items:
            # See: https://github.com/squidfunk/mkdocs-material/discussions/7783
            # Assume the "Public REST API" Section is the last one (hence the -1 index)
            page.toc.items[0].children[-1].children.append(
                AnchorLink(html.escape(route.rule), f"__endpoint_{route_id}", 2)
            )

        # Top bar summary for each route
        methods_html = " ".join(
            [f"<span class='method {m}'>{m}</span>" for m in methods]
        )
        html_doc.append(
            f"<div class='summary' onclick=\"toggleDetails('details-{route_id}')\">"
            f"<div>{methods_html} <b>{html.escape(route.rule)}</b></div>"
            f"<div>›</div></div>"
        )
        html_doc.append(f"<div id='details-{route_id}' class='details'>")

        # Parse docstring if available
        if func.__doc__:
            doc = Docstring(func.__doc__).parse("google")
            for section in doc:
                if isinstance(section, DocstringSectionText):
                    html_doc.append(f"<p class='description'>{section.value}</p>")

                if isinstance(section, DocstringSectionParameters):
                    html_doc.append("<h4>Parameters</h4>")
                    html_doc.append(
                        "<table><tr><th>Name</th><th>Type</th><th>Description</th></tr>"
                    )
                    for param in section.value:
                        html_doc.append(
                            f"<tr><td>{param.name}</td><td>{param.annotation or ''}</td><td>{convert_markdown_to_html(param.description)}</td></tr>"
                        )
                    html_doc.append("</table>")

                if isinstance(section, DocstringSectionReturns):
                    html_doc.append("<h4>Responses</h4>")
                    html_doc.append("<table><tr><th>Code</th><th>Description</th></tr>")
                    for ret in section.value:
                        html_doc.append(
                            f"<tr><td>{ret.name or 'default'}</td><td>{convert_markdown_to_html(ret.description)}</td></tr>"
                        )
                    html_doc.append("</table>")
        else:
            html_doc.append("<p><i>No documentation available.</i></p>")

        html_doc.append("</div></div>")

    html_doc.append("</div>")

    return "\n".join(html_doc)


@mkdocs.plugins.event_priority(-50)
def on_page_content(html, page, config, files):
    if "{% generate_frontend_api %}" in html:
        content = generate_api_description(page)
        return html.replace("{% generate_frontend_api %}", content)

    return None
