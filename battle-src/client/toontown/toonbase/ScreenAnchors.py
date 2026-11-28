"""Corner anchors for the interface pieces that were laid out for a 4:3 screen (the laff meter, the Shticker Book button).
Their coordinates, and the tutorial script's, are written for that screen: a node placed with them under one of these anchors lands
where it always did on 4:3 but follows the real screen corner on any other shape, so on a phone or a narrow window it stays in view."""

from . import ToontownGlobals

_anchors = {}


def updateScale():
    scale = ToontownGlobals.getUiScale()
    for node, x in _anchors.values():
        node.setScale(scale)
        node.setPos(x * scale, 0, scale if x else 0)


def _anchor(name, corner, x):
    node, _ = _anchors.get(name, (None, 0))
    if node is None or node.isEmpty():
        node = corner.attachNewNode(name)
        _anchors[name] = (node, x)
        updateScale()
    return node


def bottomRight():
    """Origin where aspect2d's (4/3, 0, -1) is on a 4:3 screen: the bottom right corner."""
    return _anchor('bottomRightAnchor', base.a2dBottomRight, -4.0 / 3.0)


def bottomLeft():
    """Origin where aspect2d's (-4/3, 0, -1) is on a 4:3 screen: the bottom left corner."""
    return _anchor('bottomLeftAnchor', base.a2dBottomLeft, 4.0 / 3.0)


def chatTopLeft():
    return _anchor('chatTopLeftAnchor', base.a2dTopLeft, 0)
