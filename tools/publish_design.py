"""Scoped Outline Design publisher. No ecosystem configuration or credential changes."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design"
NAMES = [
    "README.md",
    "principles.md",
    "case-study.md",
    "navigation.md",
    "screenshots.md",
    "concepts.md",
    "decisions.md",
    "publication.md",
    "prototype.md",
    "prototype-revision-02.md",
    "implementation.md",
    "prior-activity-calculator.md",
    "financial-audit.md",
    "financial-vocabulary.md",
    "financial-implementation.md",
    "financial-clarity-owner-notes.md",
    "financial-clarity/README.md",
]


def canonical(text):
    """Outline joins paragraphs and rewrites bullet/table spacing when an editor opens."""
    # Quote paragraphs are reflowed too: their text, not wrapping markers, is authoritative.
    text = re.sub(r"(?m)^> ?", "", text)
    text = re.sub(r"(?m)^\|?[-:| ]{3,}\|?$", "", text)
    text = re.sub(r"(?m)^[ \t]*[-*] ", "- ", text)
    text = re.sub(r"[ \t]*\|[ \t]*", "|", text)
    text = re.sub(r' " =\d+(?:\.\d+)?x\d+(?:\.\d+)?"', "", text)
    return re.sub(r"\s+", " ", text).strip()


def text_hash(text):
    return hashlib.sha256(canonical(text).encode()).hexdigest()


def protect_owner_edits(doc, previous):
    recorded = previous.get("published_text_sha256")
    if recorded and text_hash(doc.get("text", "")) != recorded:
        raise RuntimeError(f"Owner edits need reconciliation before publishing: {doc['title']}")


def preserve_migration_notes(text, doc, previous, name):
    """Keep the reviewed owner appendix in Outline, never copy its private images into git.

    Only the known migration appendix is supported. Any edit to the authored prefix still
    blocks publishing. Hashes are metadata, not a local copy of the owner's material.
    """
    if name != "implementation.md" or "\nAustin Notes:" not in doc.get("text", ""):
        return text, False
    current = doc["text"]
    start = current.index("\nAustin Notes:")
    marker = "Source record: `docs/design/implementation.md`"
    end = current.rfind(marker)
    if end < start or current[end:].strip() != marker:
        raise RuntimeError("Migration owner-note boundary needs manual reconciliation")
    authored = current[:start] + "\n\n" + marker
    expected = previous.get("published_source_text_sha256", previous.get("published_text_sha256"))
    if not expected or text_hash(authored) != expected:
        raise RuntimeError("Migration authored content changed; preserve and reconcile it first")
    return text.replace(marker, current[start:end].strip() + "\n\n" + marker), True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=NAMES,
        help="Publish selected sources without touching galleries or other owner feedback",
    )
    args = parser.parse_args()
    manifest_file = DESIGN / "published.json"
    previous = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
    references_file = DESIGN / "references.json"
    references = json.loads(references_file.read_text()) if references_file.exists() else []
    origin = os.environ["OUTLINE_URL"].rstrip("/")
    if not origin.startswith(("http://", "https://")):
        raise ValueError("Outline origin must use HTTP or HTTPS")
    token = os.environ["OUTLINE_API_TOKEN"]

    def api(method, data):
        req = Request(  # noqa: S310 - HTTP(S) origin validated above
            f"{origin}/api/{method}",
            data=json.dumps(data).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urlopen(req, timeout=30) as response:  # noqa: S310
            result = json.load(response)
        if result.get("ok") is False:
            raise RuntimeError(f"{method}: {result.get('error', 'request refused')}")
        return result["data"]

    collections = api("collections.list", {"limit": 100})
    collection = next((c for c in collections if c["name"] == "Design"), None)
    if not collection:
        if not args.apply:
            print("Would create Design collection and eight source documents")  # noqa: T201
            return
        collection = api("collections.create", {"name": "Design", "permission": None})
    rows = []
    offset = 0
    while True:
        page = api(
            "documents.list", {"collectionId": collection["id"], "limit": 100, "offset": offset}
        )
        rows.extend(page)
        if len(page) < 100:
            break
        offset += len(page)
    docs = {}
    for name in NAMES:
        if args.only and name not in args.only:
            continue
        marker = f"Source record: `docs/design/{name}`"
        title = (DESIGN / name).read_text().splitlines()[0].removeprefix("# ")
        legacy = f"<!-- rhp-design-source: docs/design/{name} -->"
        doc = next(
            (d for d in rows if marker in d.get("text", "") or legacy in d.get("text", "")), None
        )
        # Adopt the index created while checking collection access, but not unrelated pages.
        if not doc and name == "README.md":
            doc = next((d for d in rows if d["title"] == "RHP Design"), None)
        if not doc:
            if not args.apply:
                if args.verify:
                    raise RuntimeError(f"Missing Design document: {name}")
                print(f"Would create {name}")  # noqa: T201
                continue
            doc = api(
                "documents.create",
                {
                    "title": title,
                    "text": marker + "\n\n# " + title,
                    "collectionId": collection["id"],
                    "publish": True,
                },
            )
        docs[name] = doc

    galleries = [d for d in rows if d["title"].startswith("Design exports - ")]
    changed = 0
    manifest = {
        "collection": origin + collection["url"],
        "documents": {},
        "galleries": {d["id"]: {"title": d["title"], "url": origin + d["url"]} for d in galleries},
    }
    if args.only:
        manifest["documents"] = previous.get("documents", {}).copy()
        manifest["galleries"] = previous.get("galleries", {}).copy()
    for name, doc in docs.items():
        source = (DESIGN / name).read_text()
        marker = f"Source record: `docs/design/{name}`"
        text = source + "\n\n---\n\n" + marker

        def link(match):
            label, path = match.group(1), match.group(2)
            if path in docs:
                return f"[{label}]({origin}{docs[path]['url']})"
            if path in previous.get("documents", {}):
                return f"[{label}]({previous['documents'][path]['url']})"
            return match.group(0)

        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
        if name == "screenshots.md":
            for reference in references:
                text += f"\n\n## {reference['title']}\n\n"
                text += f"![{reference['title']}]({origin}/api/attachments.redirect?id="
                text += f"{reference['attachment']})\n"
        if name in ("README.md", "concepts.md", "navigation.md", "screenshots.md") and galleries:
            text += "\n\n## Published visual material\n\n"
            for gallery in sorted(galleries, key=lambda d: d["title"]):
                text += f"- [{gallery['title']}]({origin}{gallery['url']})\n"
        source_text_hash = text_hash(text)
        text, preserved_notes = preserve_migration_notes(
            text, doc, previous.get("documents", {}).get(name, {}), name
        )
        if canonical(text) != canonical(doc.get("text", "")):
            changed += 1
            if args.verify:
                raise RuntimeError(f"Design source drift: {name}")
            if args.apply:
                if not preserved_notes:
                    protect_owner_edits(doc, previous.get("documents", {}).get(name, {}))
                api(
                    "documents.update",
                    {"id": doc["id"], "text": text, "title": source.splitlines()[0][2:]},
                )
            else:
                print(f"Would update {name}")  # noqa: T201
        manifest["documents"][name] = {
            "id": doc["id"],
            "url": origin + doc["url"],
            "sha256": hashlib.sha256(source.encode()).hexdigest(),
            "published_text_sha256": text_hash(text),
            "published_source_text_sha256": source_text_hash,
        }
    assets_file = DESIGN / "outline-assets.json"
    if assets_file.exists() and not args.only:
        assets = json.loads(assets_file.read_text())
        for gallery in galleries:
            own = {
                Path(path).name: row
                for path, row in assets.items()
                if row["document"] == gallery["id"]
            }
            text = "Proposal only. Synthetic data. These are wireframes, not shipped screens.\n\n"
            text += f"[Study index]({origin}{docs['README.md']['url']}) / "
            text += f"[Decisions and feedback]({origin}{docs['decisions.md']['url']})\n\n"
            text += "## Print and editable files\n\n"
            for name, asset in sorted(own.items()):
                if not name.endswith((".png", ".jpg")):
                    text += f"- [{name}]({origin}/api/attachments.redirect?id={asset['id']})\n"
            for name, asset in sorted(own.items()):
                if not name.endswith((".png", ".jpg")):
                    continue
                if name.startswith("entry-"):
                    caption = "Actual application QA screenshot - synthetic accounts / " + (
                        "tenant phone" if "tenant" in name else "manager desktop"
                    )
                elif name.startswith("navigation-"):
                    caption = "Proposed role-aware navigation map"
                elif name.startswith("maintenance-workflow-"):
                    caption = "Maintenance and financial responsibility remain separate"
                else:
                    number = int(name.rsplit("-", 1)[1].split(".")[0])
                    screen = (
                        "Staff queue",
                        "Request detail",
                        "Tenant maintenance",
                        "Lease ledger",
                    )[(number - 1) // 2]
                    caption = (
                        f"{number}. {screen} / {'Desktop' if number % 2 else 'Phone'} wireframe"
                    )
                text += f"\n\n### {caption}\n\n"
                text += f"![{caption}]({origin}/api/attachments.redirect?id={asset['id']})\n"
            refs = [r for r in references if r["document"] == gallery["id"]]
            for reference in refs:
                text += f"\n\n## {reference['title']}\n\n"
                text += "Owner-supplied reference; original retained, not an RHP concept.\n\n"
                text += f"![{reference['title']}]({origin}/api/attachments.redirect?id="
                text += f"{reference['attachment']})\n"
            if canonical(text) != canonical(gallery.get("text", "")):
                changed += 1
                if args.verify:
                    raise RuntimeError(f"Design gallery drift: {gallery['title']}")
                if args.apply:
                    protect_owner_edits(
                        gallery, previous.get("galleries", {}).get(gallery["id"], {})
                    )
                    known = {a["id"] for a in own.values()} | {r["attachment"] for r in refs}
                    linked = set(
                        re.findall(r"attachments\.redirect\?id=([\w-]+)", gallery.get("text", ""))
                    )
                    if linked - known:
                        raise RuntimeError(f"Unreconciled owner attachments: {gallery['title']}")
                    api("documents.update", {"id": gallery["id"], "text": text})
                else:
                    print(f"Would update {gallery['title']}")  # noqa: T201
            manifest["galleries"][gallery["id"]]["published_text_sha256"] = text_hash(text)
    if args.apply:
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    print(  # noqa: T201
        f"Design: {len(docs)} source documents; "
        f"{len(galleries)} export galleries; {changed} changes"
    )


if __name__ == "__main__":
    main()
