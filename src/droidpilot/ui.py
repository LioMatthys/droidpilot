"""Parse a UIAutomator hierarchy dump into a searchable node tree."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Iterator

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass
class UiNode:
    text: str = ""
    resource_id: str = ""
    content_desc: str = ""
    cls: str = ""
    package: str = ""
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    children: list["UiNode"] = field(default_factory=list)

    @property
    def center(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def label(self) -> str:
        """Best human-readable label for this node."""
        return self.text or self.content_desc or self.resource_id.split("/")[-1]

    def walk(self) -> Iterator["UiNode"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def find_all(self, pred: Callable[["UiNode"], bool]) -> list["UiNode"]:
        return [n for n in self.walk() if pred(n)]

    def find(self, pred: Callable[["UiNode"], bool]) -> "UiNode | None":
        for n in self.walk():
            if pred(n):
                return n
        return None


def _parse_bounds(s: str) -> tuple[int, int, int, int]:
    m = _BOUNDS_RE.match(s or "")
    if not m:
        return (0, 0, 0, 0)
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def _node_from_el(el: ET.Element) -> UiNode:
    a = el.attrib
    node = UiNode(
        text=a.get("text", ""),
        resource_id=a.get("resource-id", ""),
        content_desc=a.get("content-desc", ""),
        cls=a.get("class", ""),
        package=a.get("package", ""),
        clickable=a.get("clickable") == "true",
        enabled=a.get("enabled", "true") == "true",
        focused=a.get("focused") == "true",
        bounds=_parse_bounds(a.get("bounds", "")),
    )
    node.children = [_node_from_el(child) for child in el if child.tag == "node"]
    return node


def parse_hierarchy(xml: str) -> UiNode:
    """Parse a uiautomator dump. Returns a synthetic root wrapping the tree."""
    root_el = ET.fromstring(xml)
    top = [_node_from_el(c) for c in root_el if c.tag == "node"]
    root = UiNode(cls="hierarchy")
    root.children = top
    return root


# --- selector helpers -------------------------------------------------------

def by_text(query: str, exact: bool = False) -> Callable[[UiNode], bool]:
    q = query if exact else query.lower()

    def pred(n: UiNode) -> bool:
        hay = n.text if exact else n.text.lower()
        desc = n.content_desc if exact else n.content_desc.lower()
        if exact:
            return hay == q or desc == q
        return q in hay or q in desc

    return pred


def by_resource_id(rid: str) -> Callable[[UiNode], bool]:
    def pred(n: UiNode) -> bool:
        return n.resource_id == rid or n.resource_id.endswith("/" + rid)

    return pred


def by_desc(query: str, exact: bool = False) -> Callable[[UiNode], bool]:
    q = query if exact else query.lower()

    def pred(n: UiNode) -> bool:
        d = n.content_desc if exact else n.content_desc.lower()
        return d == q if exact else q in d

    return pred


def summarize(root: UiNode, max_nodes: int = 80) -> str:
    """A compact, agent-readable list of the meaningful on-screen elements."""
    lines: list[str] = []
    for n in root.walk():
        if not (n.text or n.content_desc or n.clickable):
            continue
        x, y = n.center
        tag = "tap" if n.clickable else "txt"
        rid = n.resource_id.split("/")[-1]
        label = n.text or n.content_desc or rid or n.cls.split(".")[-1]
        extra = f" id={rid}" if rid else ""
        lines.append(f'[{tag}] "{label}" @({x},{y}){extra}')
        if len(lines) >= max_nodes:
            lines.append("… (truncated)")
            break
    return "\n".join(lines) if lines else "(no labeled elements found)"
