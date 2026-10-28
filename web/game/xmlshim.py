"""Tiny stand-in for xml.sax (the browser Python build has no XML parser). Handles what the game's DNA files need:
elements with quoted attributes, text, comments, processing instructions, CDATA and the five basic entities."""
import re
import sys
import types

_TOKEN = re.compile(
    r"<!--.*?-->|<\?.*?\?>|<!\[CDATA\[(?P<cdata>.*?)\]\]>|<!DOCTYPE[^>]*>"
    r"|</\s*(?P<end>[^>\s]+)\s*>"
    r"|<(?P<tag>[^\s/>!?]+)(?P<attrs>(?:\s+[^\s=/>]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(?P<empty>/?)>"
    r"|(?P<text>[^<]+)",
    re.S,
)
_ATTR = re.compile(r"([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


def _unescape(s):
    if "&" not in s:
        return s
    s = s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
    s = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"&#([0-9]+);", lambda m: chr(int(m.group(1))), s)
    return s.replace("&amp;", "&")


class SAXParseException(Exception):
    pass


class ContentHandler:
    def __init__(self):
        pass

    def startElement(self, name, attrs):
        pass

    def endElement(self, name):
        pass

    def characters(self, content):
        pass


def parseString(data, handler):
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    stack = []
    for m in _TOKEN.finditer(data):
        if m.group("tag"):
            attrs = {}
            for a in _ATTR.finditer(m.group("attrs") or ""):
                attrs[a.group(1)] = _unescape(a.group(2) if a.group(2) is not None else a.group(3))
            handler.startElement(m.group("tag"), attrs)
            if m.group("empty"):
                handler.endElement(m.group("tag"))
            else:
                stack.append(m.group("tag"))
        elif m.group("end"):
            if not stack or stack[-1] != m.group("end"):
                raise SAXParseException("mismatched tag </%s>" % m.group("end"))
            stack.pop()
            handler.endElement(m.group("end"))
        elif m.group("text") is not None:
            if stack:
                handler.characters(_unescape(m.group("text")))
        elif m.group("cdata") is not None and stack:
            handler.characters(m.group("cdata"))
    if stack:
        raise SAXParseException("unclosed tag <%s>" % stack[-1])


def parse(source, handler):
    if hasattr(source, "read"):
        data = source.read()
    else:
        with open(source, "rb") as f:
            data = f.read()
    parseString(data, handler)


def install():
    try:
        import xml.sax  # noqa: F401
        return False
    except ImportError:
        pass
    pkg = sys.modules.get("xml")
    if pkg is None:
        pkg = types.ModuleType("xml")
        pkg.__path__ = []
        sys.modules["xml"] = pkg
    sax = types.ModuleType("xml.sax")
    sax.ContentHandler = ContentHandler
    sax.parse = parse
    sax.parseString = parseString
    sax.SAXParseException = SAXParseException
    sys.modules["xml.sax"] = sax
    pkg.sax = sax
    return True
