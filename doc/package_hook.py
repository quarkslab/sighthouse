from pathlib import Path
import mkdocs.plugins
import logging
import inspect
import re

import sighthouse.pipeline.package as pkg

TABLE_PLACEHOLDER = "{% generate_package_table %}"
DESC_PLACEHOLDER = "{% generate_package_description %}"
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})(\s)")


def get_packages():
    """Return the core package metadata"""
    log = logging.getLogger("mkdocs")
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

    return sorted(data, key=lambda e: e.name)


def cell(value):
    """Make a value safe for a single Markdown table cell."""
    text = "" if value is None else str(value)
    text = text.replace("|", r"\|")
    return " ".join(text.split())


def slug(name):
    """Match the generated title id"""
    return re.sub(r"[^\w\- ]", "", str(name)).strip().lower().replace(" ", "-")


def downgrade_headings(text, levels=3):
    """Push docstring headings down so they nest under the package's '## name'."""
    out, fence = [], None
    for line in text.splitlines():
        m = FENCE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker[0]
            elif marker[0] == fence:
                fence = None
        elif fence is None:
            line = HEADING.sub(
                lambda h: "#" * min(len(h.group(1)) + levels, 6) + h.group(2), line
            )
        out.append(line)
    return "\n".join(out)


def generate_table(packages):
    lines = [
        "| Name | Version | Author | Description |",
        "| ---- | ------- | ------ | ----------- |",
    ]
    for pkg in packages:
        lines.append(
            f"| [{cell(pkg.name)}](#{slug(pkg.name)}) | {cell(pkg.version)} "
            f"| {cell(pkg.author)} | {cell(pkg.description)} |"
        )
    return "\n".join(lines)


def generate_package_description(packages):
    out = []
    for pkg in packages:
        doc = inspect.cleandoc(
            pkg.doc or f"No documentation was found for {pkg.name}:{pkg.version} ."
        )
        out.append(f"### {pkg.name}\n\n{downgrade_headings(doc)}\n")
    return "\n".join(out)


@mkdocs.plugins.event_priority(-50)
def on_page_markdown(markdown, page, config, files):
    has_table = TABLE_PLACEHOLDER in markdown
    has_desc = DESC_PLACEHOLDER in markdown
    if not (has_table or has_desc):
        return markdown

    # Load the packages
    packages = get_packages()
    if has_table:
        markdown = markdown.replace(
            TABLE_PLACEHOLDER, f"\n\n{generate_table(packages)}\n\n"
        )
    if has_desc:
        markdown = markdown.replace(
            DESC_PLACEHOLDER, f"\n\n{generate_package_description(packages)}\n\n"
        )

    return markdown
