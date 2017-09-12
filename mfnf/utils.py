"""Module with utility functions."""

import hashlib
import collections
import re
import logging
import json
import shelve
import os

from functools import reduce

report_logger = logging.getLogger("report_logger")

def log_parser_error(message, obj):
    report_logger.error("=== ERROR: {} ===".format(message))
    report_logger.debug(" <nowiki>")
    report_logger.debug(json.dumps(obj, indent=4, sort_keys=True))
    report_logger.debug(" </nowiki>")

def query_path(obj, path):
    # TODO: Tests and documentation
    return reduce(lambda x, y: y(x) if callable(y) else x[y], path, obj)

def lookup(obj, *path):
    """Lookups repeatedly the items in the list `path` of the object `obj`. In
    case any `IndexError` or `KeyError` is thrown, `None` is returned. For
    example the call `safe_lookup(obj, "a", 0, "b")` returns
    `obj["a"][0]["b"]` when it exists and `None` otherwise."""
    try:
        return query_path(obj, path)
    except (IndexError, KeyError, TypeError):
        return None

def open_database(database_path):
    """Open a database at path `database_path` where arbitrary python objects
    can be stored."""
    try:
        os.makedirs(os.path.dirname(database_path))
    except FileExistsError:
        pass

    return shelve.open(database_path, "c", writeback=True)

def to_snake_case(text):
    """Converts `text` to snake_case.

    >>> to_snake_case("Analysis 1")
    'analysis1'
    >>> to_snake_case("Mathe für Nicht-Freaks 2")
    'mathe_für_nicht-freaks2'
    """
    return re.sub(r"\s", "_", re.sub(r"\s+(?=\d)", "", text.lower()))

def select_singleton(x):
    # TODO: Tests and documentation
    return next(iter(x.values()))

def remove_prefix(text, prefix):
    """Removes the prefix `prefix` from string `text` in case it is present."""
    return text[len(prefix):] if text.startswith(prefix) else text

def remove_suffix(text, suffix):
    """Removes the suffix `suffix` from string `text` in case it is present."""
    return text[:len(text)-len(suffix)] if text.endswith(suffix) else text

def merge(obj1, obj2):
    """Merges two objects depending of the type of the first argument.

    >>> merge(None, 42)
    42
    >>> merge(None, None) is None
    True
    >>> merge([1, 2], [6, 7])
    [1, 2, 6, 7]
    >>> d = merge({ "a": 1, "b": 2}, {"b": 3, "c": 4})
    >>> d == {"a": 1, "b": 3, "c": 4}
    True
    """
    if obj1 is None:
        return obj2
    elif isinstance(obj1, list):
        return obj1 + obj2
    elif isinstance(obj2, dict):
        return {**obj1, **obj2}
    else:
        raise NotImplementedError()

def sha256(text):
    """Returns SHA256 of the string `text`."""
    return hashlib.sha256(text.encode("utf8")).hexdigest()

def stablehash(obj):
    """Returns an unique hash of object `obj`."""
    try:
        return obj._stablehash()
    except AttributeError:
        if isinstance(obj, str):
            return sha256(obj)
        elif isinstance(obj, collections.abc.Sequence):
            return sha256("|".join([stablehash(x) for x in obj]))
        elif isinstance(obj, collections.abc.Mapping):
            return stablehash(["<" + stablehash(k) + ";" + stablehash(v) + ">"
                               for k, v in obj.items()])
        else:
            raise NotImplementedError()

class CachedFunction:
    def __init__(self, db):
        self.db = db

    def __call__(self, func):
        def new_func(*args, **kwargs):
            key = stablehash([func.__name__, args, kwargs])

            if key in self.db:
                return self.db[key]
            else:
                result = func(*args, **kwargs)

                self.db[key] = result

                return result

        return new_func
