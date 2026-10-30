"""Rewrite or check the generated blocks of a card (F6; R50).

A block is everything between `<!-- card:begin NAME -->` and
`<!-- card:end NAME -->`. `render_card` replaces each block's content with what
its renderer returns, so the prose around the blocks is never touched; every
marker needs a renderer and every renderer a marker.
"""

import re
from collections.abc import Mapping
from pathlib import Path

from heartbeat.runs import write_text_atomic

BLOCK = re.compile(
    r"(<!-- card:begin (?P<name>[a-z0-9_]+) -->\n)(?P<body>.*?)"
    r"(\n<!-- card:end (?P=name) -->)",
    re.S,
)


class CardError(ValueError):
    """A card's markers and the renderers do not match."""


def block_names(text: str) -> list[str]:
    """The names of the generated blocks, in order."""
    return [m.group("name") for m in BLOCK.finditer(text)]


def block_bodies(text: str) -> dict[str, str]:
    """Each block's current content, without its blank framing lines."""
    return {m.group("name"): m.group("body").strip("\n") for m in BLOCK.finditer(text)}


def render_card(text: str, blocks: Mapping[str, str]) -> str:
    """The card with every block replaced by its rendered content.

    Raises:
        CardError: If a marker has no renderer, a renderer no marker, or a
            name appears twice.
    """
    names = block_names(text)
    if len(set(names)) != len(names):
        raise CardError(f"a block appears twice: {names}")
    if set(names) != set(blocks):
        raise CardError(
            f"markers {sorted(names)} and renderers {sorted(blocks)} differ"
        )
    return BLOCK.sub(
        lambda m: f"{m.group(1)}\n{blocks[m.group('name')]}\n{m.group(4)}", text
    )


def stale_blocks(text: str, blocks: Mapping[str, str]) -> list[str]:
    """Blocks whose content differs from what would be rendered now (R50)."""
    rendered = block_bodies(render_card(text, blocks))
    current = block_bodies(text)
    return [name for name in block_names(text) if current[name] != rendered[name]]


def write_card(path: Path, blocks: Mapping[str, str]) -> list[str]:
    """Rewrite a card's blocks in place; return the names that changed."""
    text = path.read_text(encoding="utf-8")
    changed = stale_blocks(text, blocks)
    if changed:
        write_text_atomic(path, render_card(text, blocks))
    return changed


def pending_after_sealed(text: str, pending: str) -> list[str]:
    """`test_*` blocks still pending although a sealed run is logged (R50)."""
    return [
        name
        for name, body in block_bodies(text).items()
        if name.startswith("test_") and body == pending
    ]
