import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_ext"))

project = "chipsLDPC"
author = "chipsLDPC contributors"
copyright = "2026, chipsLDPC contributors"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx.ext.mathjax",
    "source_links",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".md": "markdown",
}
root_doc = "index"
myst_url_schemes = ["http", "https", "mailto", "ftp", "code"]

myst_enable_extensions = [
    "colon_fence",
    "dollarmath",
    "amsmath",
]

html_theme = "sphinx_rtd_theme"
html_title = "chipsLDPC"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "titles_only": False,
}
