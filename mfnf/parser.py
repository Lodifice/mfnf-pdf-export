"""Module defining a parser for MediaWiki code."""

import json
import re

from itertools import count
from html.parser import HTMLParser
from mfnf.transformations import NodeTransformation, ChainedAction, Action, \
    NodeTypeTransformation, DeleteTransformation, check, NotInterested
from mfnf.utils import lookup, remove_prefix, remove_suffix, add_dict

TEMPLATE_SPEC = {
    "Definition": lambda x: x in ["definition"],
    "Warnung": lambda x: x in ["1"],
    "Aufgabe": lambda x: x in ["aufgabe", "lösung", "beweis"],
    "Liste": lambda x: x.startswith("item")
}

TEMPLATE_LIST_PARAMS = {
    "Liste": ["item"]
}

def parse_content(api, title, text):
    """Parse MediaWiki code `text`."""
    return MediaWikiCodeParser(api=api, title=title)(text)

def parse_inline_content(api, title, text):
    """Parse MediaWiki code `text` in inline mode."""
    content = MediaWikiCodeParser(api=api, title=title)(text)

    assert len(content) == 1
    assert content[0]["type"] == "element"
    assert content[0]["name"] == "p"

    return content[0]["children"]

def text_rstrip(content):
    """Applies `rstrip()` to parsed MediaWiki content."""
    try:
        return content[:-1] + [{"type": "text",
                                "data": content[-1]["data"].rstrip()}]
    except (IndexError, KeyError):
        return content

class HTML2JSONParser(HTMLParser):
    """Parser for converting HTML to JSON."""

    def __init__(self):
        super(HTML2JSONParser, self).__init__()

        self._node_stack = []
        self.content = []
        self._last_node = None
        self._is_first_node = True

    def _append(self, node):
        self._last_node = node

        if self._node_stack:
            self._node_stack[-1]["children"].append(node)
        else:
            self.content.append(node)

    def handle_starttag(self, tag, attrs):
        node = {"type": "element", "name": tag,
                "attrs": dict(attrs),
                "children": []}

        self._append(node)
        self._node_stack.append(node)
        self._is_first_node = True

    def handle_endtag(self, tag):
        assert self._last_node

        try:
            self._last_node["data"] = self._last_node["data"].rstrip()
        except KeyError:
            pass

        self._is_first_node = False

        assert self._node_stack
        assert self._node_stack[-1]["name"] == tag

        self._node_stack.pop()

    def handle_data(self, data):
        if re.search("\S", data):
            data = re.sub(r"(?<=\S\s)\s+$", "", data)
            data = re.sub(r"^\s+(?=\s\S)", "", data)
            data = re.sub(r"\s", " ", data)

            if self._is_first_node:
                data = data.lstrip()
                self._is_first_node = False

            self._append({"type": "text", "data": data})

    def error(self, message):
        raise AssertionError(message)

class MediaWikiCodeParser(ChainedAction):
    """Parses MediaWikiCode and restore template definitions."""

    class MediaWikiCode2HTML(Action):
        """Converts MediaWiki code to HTML"""

        def __call__(self, text):
            return self.api.convert_text_to_html(self.title, text)

    class MediaWikiCodeHTML2JSON(Action):
        """Converts HTML of a MediaWiki document to JSON."""

        def __call__(self, text):
            parser = HTML2JSONParser()

            parser.feed(text)

            return parser.content

    class TemplateDeinclusion(NodeTransformation):
        """Replaces included MediaWiki templates with template
        specification."""

        def parse_parameter_value(self, name, param_key, param_value):
            """Parses `param_value` in case `param_key` is a content
            parameter."""
            if name in TEMPLATE_SPEC and TEMPLATE_SPEC[name](param_key):
                return parse_content(self.api, self.title, param_value)
            else:
                return param_value

        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "attrs", "typeof") == "mw:Transclusion"

            template = json.loads(obj["attrs"]["data-mw"])
            template = template["parts"][0]["template"]

            name = template["target"]["wt"].strip()
            name = remove_prefix(name, ":Mathe für Nicht-Freaks: Vorlage:")

            params = template["params"]
            params = {k: v["wt"] for k, v in params.items()}
            params = {key: self.parse_parameter_value(name, key, value) \
                        for key, value in params.items()}

            return {"type": "template", "name": name, "params": params}

    class HandleGalleries(NodeTransformation):
        def parse_gallery_item(self, text):
            try:
                name, caption = text.split("|", 1)
                caption = parse_inline_content(self.api, self.title, caption)

                return {"type": "galleryitem",
                        "name": name,
                        "caption": caption}
            except ValueError:
                return {"type": "error",
                        "message": "Gallery item needs a caption"}

        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "name") == "ul"
            check(obj, "attrs", "typeof") == "mw:Extension/gallery"

            data_mw = json.loads(obj["attrs"]["data-mw"])
            spec = data_mw["body"]["extsrc"].strip()
            items = [self.parse_gallery_item(x) for x in spec.splitlines()]

            return {"type": "gallery",
                    "widths": int(data_mw["attrs"].get("widths", 120)),
                    "heights": int(data_mw["attrs"].get("heights", 120)),
                    "children": items}

class ArticleContentParser(ChainedAction):
    class MediaWikiCode2HTML(Action):
        def __call__(self, text):
            return parse_content(self.api, self.title, text)

    class MergeListParametersInTemplates(NodeTypeTransformation):
        def transform_template(self, obj):
            if obj["name"] in TEMPLATE_LIST_PARAMS:
                params = obj["params"].copy()

                for param_prefix in TEMPLATE_LIST_PARAMS[obj["name"]]:
                    result = []

                    for n in count(1):
                        try:
                            result.append(params.pop(param_prefix + str(n)))
                        except KeyError:
                            break

                    params[param_prefix + "_list"] = result

                return add_dict(obj, {"params": params})
            else:
                raise NotInterested()

    class HandleLists(NodeTransformation):
        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "name").of("ul", "ol")

            children = [self(li["children"]) for li in obj["children"]]

            return {"type": "list",
                    "ordered": obj["name"] == "ol",
                    "children": children}

    class HandleFigures(NodeTransformation):
        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "name") == "figure"
            check(obj, "attrs", "typeof").of("mw:Image", "mw:Image/Thumb")

            caption = [child
                       for child in obj["children"]
                       if child["name"] == "figcaption"]
            try:
                caption = caption[0]["children"]
            except IndexError:
                caption = []

            img = obj["children"][0]["children"][0]["attrs"]
            name = remove_prefix(img["resource"], "./Datei:")

            return {"type": "image", "caption": self(caption),
                    "name": name, "url": img["src"],
                    "thumbnail": obj["attrs"]["typeof"] == "mw:Image/Thumb"}

    class HandleInlineFigures(NodeTransformation):
        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "name") == "span"
            check(obj, "attrs", "typeof") == "mw:Image"

            return {"type": "error",
                    "message": "Inline images are not allowed"}

    class HandleTable(NodeTransformation):
        def transform_dict(self, obj):
            check(obj, "type") == "element"
            check(obj, "name") == "table"

            content = obj["children"]

            if lookup(content, 0, "name") == "tbody":
                content = content[0]["children"]

            return {"type": "table", "children": self(content)}

    class ConvertInlineMath(NodeTransformation):
        def transform_dict(self, obj):
            check(obj, "attrs", "typeof") == "mw:Extension/math"

            formula = json.loads(obj["attrs"]["data-mw"])["body"]["extsrc"]

            return {"type": "inlinemath", "formula": formula}

    class HandleWrongInlineMath(NodeTypeTransformation):
        def transform_inlinemath(self, obj):
            if "\\begin{align}" in obj["formula"]:
                return {"type": "error",
                        "message": "\\begin{align} not allowed in inline math"}
            else:
                raise NotInterested()

    class CleanupTemplateInclusion(DeleteTransformation):
        """The restoring of template definitions only replaces the top level
        HTML element. This step deletes the other ones."""

        #def shall_delete_dict(self, obj):
        #    return lookup(obj, "type") == "element" \
        #            and lookup(obj, "attrs", "about") != None

    class HandleTemplates(NodeTypeTransformation):
        def transform_template(self, obj):
            if obj["name"] == "Liste":
                return {"type": "list",
                        "ordered": obj["params"].get("type", "") == "ol",
                        "children": obj["params"]["item_list"]}
            if obj["name"] == "Formel":
                formula = obj["params"]["1"].strip()
                formula = re.match("<math>(.*)</math>", formula).group(1)
                formula = formula.strip()

                formula = remove_prefix(formula, "\\begin{align}")
                formula = remove_suffix(formula, "\\end{align}")
                formula = formula.strip()

                return {"type": "equation",
                        "formula": formula}
            else:
                raise NotInterested()

    class DeleteHeaderAndFooter(DeleteTransformation):
        def shall_delete_dict(self, obj):
            return lookup(obj, "type") == "template" \
                    and obj["name"].startswith("#invoke:")

    class FixNodeTypes(NodeTypeTransformation):
        def transform_element(self, obj):
            if obj["name"] == "p":
                return {"type": "paragraph", "children": self(obj["children"])}
            elif obj["name"] == "dfn":
                return {"type": "i", "children": self(obj["children"])}
            elif obj["name"] in ("i", "b", "th", "tr", "td"):
                return {"type": obj["name"], "children": self(obj["children"])}
            elif obj["name"] in ("h2", "h3"):
                return {"type": "header",
                        # Header begin with h2 in our project -> subtract 1
                        "depth": int(obj["name"][-1])-1,
                        "children": self(obj["children"])}
            elif obj["name"] in ("h1", "h4", "h5", "h6"):
                message = "Heading of depth {} is not allowed"

                return {"type": "error",
                        "message": message.format(int(obj["name"][-1]))}
            else:
                return {"type": "notimplemnted",
                        "target": obj}

    class HandleHeadingAnchors(NodeTypeTransformation):
        def transform_header(self, obj):
            check(obj, "children", -1, "type") == "template"
            check(obj, "children", -1, "name") == "Anker"

            heading = text_rstrip(obj["children"][:-1])
            anchor = obj["children"][-1]["params"]["1"]

            return add_dict(obj, {"children": heading, "anchor": anchor})

class ArticleParser(ChainedAction):
    class LoadArticleContent(NodeTypeTransformation):
        """Loads the content of an article."""

        def transform_article(self, article):
            parser = ArticleContentParser(api=self.api, title=article["title"])

            content = parser(self.api.get_content(article["title"]))

            return add_dict(article, {"content": content})
