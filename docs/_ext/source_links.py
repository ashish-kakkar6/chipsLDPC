"""Render repository-relative code links from the checkout being documented."""

import html
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from docutils import nodes
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from sphinx.util import logging

ROOT = Path(__file__).resolve().parents[2]
CODE_SUFFIXES = {".scala", ".py", ".cpp", ".h", ".sh", ".sc"}
MARKDOWN_TARGET = re.compile(r"(?<=\]\()(\.\.?/[^\s)]+)(?=\))")
LINE = re.compile(r"L([1-9][0-9]*)\Z")
LOGGER = logging.getLogger(__name__)


def prepare_links(app, docname, source):
    """Preserve line fragments which MyST otherwise drops for downloads."""
    files = set()
    source_dir = Path(app.env.doc2path(docname)).parent

    def replace(match):
        target = urlsplit(match.group())
        path = (source_dir / unquote(target.path)).resolve()
        if path.suffix not in CODE_SUFFIXES:
            return match.group()
        location = (docname, source[0].count("\n", 0, match.start()) + 1)
        if not path.is_relative_to(ROOT) or not path.is_file():
            LOGGER.warning("Source link does not name a repository file: %s",
                           match.group(), location=location)
            return match.group()
        line = LINE.fullmatch(target.fragment) if target.fragment else None
        if target.fragment and not line:
            LOGGER.warning("Source link must use a single #L<number> anchor: %s",
                           match.group(), location=location)
            return match.group()
        if line and int(line[1]) > len(path.read_text().splitlines()):
            LOGGER.warning("Source link line is beyond the end of %s", path,
                           location=location)
            return match.group()
        name = path.relative_to(ROOT).as_posix()
        files.add(name)
        app.env.note_dependency(str(path))
        return "code:///" + name + ("#" + target.fragment if line else "")

    source[0] = MARKDOWN_TARGET.sub(replace, source[0])
    if not hasattr(app.env, "repository_source_files"):
        app.env.repository_source_files = {}
    app.env.repository_source_files[docname] = files


def resolve_links(app, doctree, docname):
    for node in list(doctree.findall(nodes.reference)):
        uri = node.get("refuri", "")
        if not uri.startswith("code:///"):
            continue
        target = urlsplit(uri)
        name = target.path.lstrip("/")
        if app.builder.format != "html":
            node.replace_self(nodes.inline("", "", *node.children))
            continue
        page = "_code/" + name
        node["refuri"] = app.builder.get_relative_uri(docname, page)
        if target.fragment:
            node["refuri"] += "#L-" + target.fragment[1:]
        node["internal"] = True
        node["classes"].append("source-link")


def collect_pages(app):
    files = set().union(*getattr(app.env, "repository_source_files", {}).values())
    for name in sorted(files):
        code = (ROOT / name).read_text()
        formatter = HtmlFormatter(linenos="inline", lineanchors="L",
                                  anchorlinenos=True, cssclass="highlight")
        body = (f'<h1 class="source-code-title">{html.escape(name)}</h1>'
                "<p>Source from the repository checkout used to build these docs. "
                "Line numbers link to individual source lines.</p>"
                + highlight(code, get_lexer_for_filename(name, stripnl=False, ensurenl=False), formatter))
        yield "_code/" + name, {"title": name, "body": body}, "page.html"


def purge_doc(app, env, docname):
    getattr(env, "repository_source_files", {}).pop(docname, None)


def merge_info(app, env, docnames, other):
    if not hasattr(env, "repository_source_files"):
        env.repository_source_files = {}
    for name in docnames:
        env.repository_source_files[name] = getattr(
            other, "repository_source_files", {}).get(name, set())


def setup(app):
    app.connect("source-read", prepare_links)
    app.connect("doctree-resolved", resolve_links)
    app.connect("html-collect-pages", collect_pages)
    app.connect("env-purge-doc", purge_doc)
    app.connect("env-merge-info", merge_info)
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}
