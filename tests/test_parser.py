import requests
import yaml

from unittest import TestCase
from mfnf.api import HTTPMediaWikiAPI
from mfnf.parser import HTML2JSONParser, ArticleContentParser

class TestParser(TestCase):

    def setUp(self):
        self.api = HTTPMediaWikiAPI(requests.Session())
        self.title = "Mathe für Nicht-Freaks: Analysis 1"
        self.maxDiff = None

    def parse(self, text):
        return ArticleContentParser(api=self.api, title=self.title)(text)

    def test_html2json_parser(self):
        with open("docs/html.spec.yml") as spec_file:
            spec = yaml.load(spec_file)

        for html, target_json in ((x["in"], x["out"]) for x in spec):
            with self.subTest(html=html):
                parser = HTML2JSONParser()
                parser.feed(html)

                self.assertListEqual(parser.content, target_json, msg=html)

    def test_parsing_block_elements(self):
        with open("docs/mfnf-block-elements.spec.yml") as spec_file:
            spec = yaml.load(spec_file)

        for text, target in ((x["in"], x["out"]) for x in spec):
            with self.subTest(text=text):
                self.assertListEqual(self.parse(text), target, msg=text)

    def test_parsing_inline_elements(self):
        with open("docs/mfnf-inline-elements.spec.yml") as spec_file:
            spec = yaml.load(spec_file)

        for text, target in ((x["in"], x["out"]) for x in spec):
            with self.subTest(text=text):
                target = [{"type": "paragraph", "children": [target]}]

                self.assertListEqual(self.parse(text), target, msg=text)
