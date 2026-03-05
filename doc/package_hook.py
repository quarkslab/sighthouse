from pathlib import Path
import mkdocs.plugins
import logging

import sighthouse.pipeline.package as pkg

log = logging.getLogger("mkdocs")


def generate_table():
    loader = pkg.PackageLoader(log)

    # For now core_modules are shipped inside sighthouse.pipeline package
    core_modules_path = Path(pkg.__file__).parent / "core_modules"
    if not core_modules_path.exists() or not core_modules_path.is_dir():
        log.error(f"Fail to find SightHouse core_modules directory: '{core_modules}'")
        return ""

    data = []
    # Iterate over all the package, loading their metadata
    for path in core_modules_path.iterdir():
        metadata = loader.load_metadata(path)
        log.debug(f"Found package: {metadata}")
        data.append(metadata)

    # Create the HTML table
    table_html = "<table><tr><th>Name</th><th>Version</th><th>Author</th><th>Description</th></tr>"
    for row in data:
        table_html += f"<tr><td>{row.name}</td><td>{row.version}</td><td>{row.author}</td><td>{row.description}</td></tr>"
    table_html += "</table>"
    return table_html


@mkdocs.plugins.event_priority(-50)
def on_page_content(html, page, config, files):
    if "{% generate_package_table %}" in html:
        table_content = generate_table()
        html = html.replace("{% generate_package_table %}", table_content)
    return html
