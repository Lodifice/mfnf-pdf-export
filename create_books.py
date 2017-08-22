"""Creates a PDF from an article of the project „Mathe für Nicht-Freaks“."""

import os
import shelve

import requests

from mfnf.api import HTTPMediaWikiAPI
from mfnf.parser import ArticleParser
from mfnf.utils import CachedFunction
from mfnf.sitemap import parse_sitemap
from mfnf.latex import LatexExporter

# title of article which shall be converted to PDF
SITEMAP_ARTICLE_NAME = "Mathe für Nicht-Freaks: Projekte/LMU Buchprojekte"

def create_book(book):
    """Creates the LaTeX file of a book."""
    target = os.path.join("out", book["name"], book["name"] + ".tex")

    try:
        os.makedirs(os.path.dirname(target))
    except FileExistsError:
        pass

    with open(target, "w") as latex_file:
        LatexExporter()(book, latex_file)

def run_script():
    """Runs this script."""
    with shelve.open(".cache.db", "c", writeback=True) as database:
        cached_function = CachedFunction(database)

        class CachedMediaWikiAPI(HTTPMediaWikiAPI):
            """A version of the API where the main function calls are
            cached."""

            @cached_function
            def get_content(self, title):
                return super().get_content(title)

            @cached_function
            def convert_text_to_html(self, title, text):
                return super().convert_text_to_html(title, text)

        api = CachedMediaWikiAPI(requests.Session())
        parser = ArticleParser(api=api)

        sitemap = parse_sitemap(api.get_content(SITEMAP_ARTICLE_NAME))
        sitemap = parser(sitemap)

        for book in sitemap["children"]:
            create_book(book)

if __name__ == "__main__":
    run_script()
