"""Resolve PPTX slide parts in their presentation display order.

The numeric suffix in a ``ppt/slides/slideN.xml`` part is an implementation
detail.  The order shown by PowerPoint is the order of ``p:sldId`` elements in
``ppt/presentation.xml``; each element points to a slide part through the
presentation relationships part.
"""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


PRESENTATION_PART = "ppt/presentation.xml"
PRESENTATION_RELS_PART = "ppt/_rels/presentation.xml.rels"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
RELATIONSHIP_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


class SlideOrderError(ValueError):
    """Raised when a PPTX cannot provide a safe, ordered slide-part mapping."""


def _read_part(archive: zipfile.ZipFile, name: str, description: str) -> bytes:
    try:
        return archive.read(name)
    except KeyError as exc:
        raise SlideOrderError(f"PPTX is missing {description}: {name}") from exc


def _resolve_internal_target(target: str, archive_names: set[str]) -> str:
    """Resolve an OPC relationship target and reject package-root escapes."""

    decoded = unquote(target)
    if not decoded:
        raise SlideOrderError("presentation slide relationship has an empty target")
    if "\\" in decoded or "\x00" in decoded:
        raise SlideOrderError(f"presentation slide relationship has an invalid target: {target!r}")

    parsed = urlsplit(decoded)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise SlideOrderError(f"presentation slide relationship target is not an internal part: {target!r}")

    source_directory = PurePosixPath(PRESENTATION_PART).parent.as_posix()
    combined = parsed.path.lstrip("/") if parsed.path.startswith("/") else posixpath.join(source_directory, parsed.path)
    parts: list[str] = []
    for component in combined.split("/"):
        if component in {"", "."}:
            continue
        if component == "..":
            if not parts:
                raise SlideOrderError(f"presentation slide relationship escapes the package: {target!r}")
            parts.pop()
            continue
        parts.append(component)
    resolved = "/".join(parts)
    if not resolved:
        raise SlideOrderError(f"presentation slide relationship resolves to an empty part: {target!r}")
    if resolved not in archive_names:
        raise SlideOrderError(
            f"presentation slide relationship target is missing from the package: {resolved}"
        )
    return resolved


def ordered_slide_parts(archive: zipfile.ZipFile) -> list[str]:
    """Return slide-part names in the deck's actual display order.

    Only ``p:sldIdLst`` determines the order.  Every referenced relationship
    must be internal, resolve within the ZIP package, and point to an existing
    part.  Errors are reported as ``ValueError`` subclasses so command-line
    callers can fail cleanly without exposing a ``KeyError`` traceback.
    """

    archive_names = set(archive.namelist())
    presentation = ET.fromstring(_read_part(archive, PRESENTATION_PART, "presentation part"))
    slide_id_list = presentation.find(f"{{{PRESENTATION_NS}}}sldIdLst")
    if slide_id_list is None:
        raise SlideOrderError("presentation part is missing p:sldIdLst")

    relationships_root = ET.fromstring(
        _read_part(archive, PRESENTATION_RELS_PART, "presentation relationships part")
    )
    relationships: dict[str, ET.Element] = {}
    for relation in relationships_root.findall(f"{{{RELATIONSHIP_NS}}}Relationship"):
        relation_id = relation.get("Id")
        if not relation_id:
            raise SlideOrderError("presentation relationships contain an entry without Id")
        if relation_id in relationships:
            raise SlideOrderError(f"presentation relationships contain duplicate Id: {relation_id}")
        relationships[relation_id] = relation

    ordered: list[str] = []
    seen_targets: set[str] = set()
    for display_index, slide_id in enumerate(slide_id_list.findall(f"{{{PRESENTATION_NS}}}sldId"), start=1):
        relation_id = slide_id.get(RELATIONSHIP_ID_ATTR)
        if not relation_id:
            raise SlideOrderError(f"slide {display_index} is missing its r:id relationship")
        relation = relationships.get(relation_id)
        if relation is None:
            raise SlideOrderError(
                f"slide {display_index} references missing presentation relationship: {relation_id}"
            )
        target = relation.get("Target")
        if relation.get("TargetMode", "Internal").casefold() == "external":
            raise SlideOrderError(
                f"slide {display_index} references an external presentation relationship: {relation_id}"
            )
        if target is None:
            raise SlideOrderError(f"presentation relationship {relation_id} is missing Target")
        resolved = _resolve_internal_target(target, archive_names)
        if resolved in seen_targets:
            raise SlideOrderError(f"slide {display_index} repeats slide part target: {resolved}")
        seen_targets.add(resolved)
        ordered.append(resolved)
    return ordered
