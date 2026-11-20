"""Read values from the committed k8s manifests as Kustomize would render them, without a YAML
parser (the backend requirements don't include one).

A value comes from the base document of that kind and name, then from every overlay patch that
applies to it, in order. Anything this reader can't follow (an inline patch, the legacy patch
fields) fails loudly instead of being skipped.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K8S = ROOT / "infra" / "k8s"


def _documents(text: str) -> list[str]:
    return [doc for doc in re.split(r"^---\s*$", text, flags=re.M) if doc.strip()]


def _is(doc: str, kind: str, name: str) -> bool:
    doc_kind = re.search(r"^kind: (\S+)\s*$", doc, re.M)
    doc_name = re.search(r"^metadata:\n(?:  .*\n)*?  name: (\S+)\s*$", doc, re.M)
    return bool(doc_kind and doc_name and doc_kind[1] == kind and doc_name[1] == name)


def _patch_items(kustomization: str) -> list[dict[str, str]]:
    """Each `patches:` entry as a flat dict of its scalar keys (path and the target fields)."""
    items: list[dict[str, str]] = []
    in_block = False
    item_indent = None
    for raw in kustomization.splitlines():
        line = re.sub(r"\s+#.*$", "", raw).rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^patches:$", line):
            in_block = True
            continue
        if in_block and re.match(r"^[^\s-]", line):
            in_block = False
        if not in_block:
            continue
        indent = len(line) - len(line.lstrip())
        entry = re.match(r"^\s*- (.*)$", line)
        if entry and (item_indent is None or indent <= item_indent):
            item_indent = indent
            items.append({})
            line = " " * (indent + 2) + entry[1]
        pair = re.match(r"^\s*(\w+):\s*(.*)$", line)
        assert pair and items, f"can't read patch line {raw!r}"
        items[-1][pair[1]] = pair[2].strip("'\"")
    return items


def patches_for(env: str, kind: str, name: str) -> list[str]:
    """The texts of the overlay's patches that Kustomize applies to that object, in order."""
    overlay = K8S / "overlays" / env
    kustomization = (overlay / "kustomization.yaml").read_text(encoding="utf-8")
    for legacy in ("patchesStrategicMerge", "patchesJson6902"):
        assert not re.search(rf"^{legacy}:", kustomization, re.M), f"{env}: {legacy} isn't read"
    found = []
    for item in _patch_items(kustomization):
        assert "path" in item, f"{env}: an inline patch isn't read: {item}"
        docs = _documents((overlay / item["path"]).read_text(encoding="utf-8"))
        if "target" in item:
            # A selector can't be evaluated here, so a patch with one counts as applying.
            matches = (
                (
                    re.fullmatch(item.get("kind", ".*"), kind)
                    and re.fullmatch(item.get("name", ".*"), name)
                )
                or "labelSelector" in item
                or "annotationSelector" in item
            )
            if matches:
                found.extend(docs)
        else:
            found.extend(doc for doc in docs if _is(doc, kind, name))
    return found


def _find(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.M)
    return int(match.group(1)) if match else None


def overlay_value(
    env: str, base: Path, kind: str, name: str, pattern: str, default: int | None = None
) -> int:
    """The base's value unless a patch the overlay applies to that object sets its own."""
    base_docs = [
        doc for doc in _documents(base.read_text(encoding="utf-8")) if _is(doc, kind, name)
    ]
    assert len(base_docs) == 1, f"{kind}/{name} not found once in {base.relative_to(ROOT)}"
    value = _find(base_docs[0], pattern)
    for patch in patches_for(env, kind, name):
        patched = _find(patch, pattern)
        value = patched if patched is not None else value
    if value is None:
        assert default is not None, f"{pattern!r} not set for {kind}/{name} in {env}"
        value = default
    return value
