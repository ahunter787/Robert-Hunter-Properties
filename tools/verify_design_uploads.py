"""Read-only local Outline upload verification; record only Design IDs and source hashes.

The existing API key cannot list attachments. Read only approved gallery/prototype metadata from
the local service, and hash stored files without modifying its database or file store.
Use --record after authenticated UI uploads; ordinary execution verifies the recorded manifest.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/design"


def run(command):
    return subprocess.check_output(command, text=True).strip()  # noqa: S603


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    published = json.loads((DESIGN / "published.json").read_text())
    ids = [str(UUID(value)) for value in published["galleries"]]
    if len(ids) != 4:
        raise ValueError("Expected exactly the four approved Design export galleries")
    prototype = published.get("documents", {}).get("prototype.md")
    if prototype:
        ids.append(str(UUID(prototype["id"])))
    revision = published.get("documents", {}).get("prototype-revision-02.md")
    if revision:
        ids.append(str(UUID(revision["id"])))
    implementation = published.get("documents", {}).get("implementation.md")
    if implementation:
        ids.append(str(UUID(implementation["id"])))
    placeholders = ",".join(f"'{value}'" for value in ids)
    query = (  # noqa: S608 - every interpolated value parsed through UUID above
        'SELECT json_agg(row_to_json(a)) FROM (SELECT id, key, "documentId" '  # noqa: S608
        f'FROM attachments WHERE "documentId" IN ({placeholders})) a;'
    )
    uploaded = (
        json.loads(
            run(
                [
                    "docker",
                    "exec",
                    "rhp-outline-db",
                    "psql",
                    "-U",
                    "outline",  # noqa: S607
                    "-d",
                    "outline",
                    "-t",
                    "-A",
                    "-c",
                    query,
                ]
            )
        )
        or []
    )
    expected = {}
    for folder, pattern in (
        ("artifacts", "*.pdf"),
        ("artifacts", "*.png"),
        ("artifacts", "*.jpg"),
        ("sources", "*.json"),
    ):
        for path in (DESIGN / folder).glob(pattern):
            if "-grayscale-" not in path.name:
                expected[path.name] = path
    for name in ("navigation-01.svg", "maintenance-workflow-01.svg"):
        expected[name] = DESIGN / "artifacts" / name
    inventory = {}
    expected_hashes = {
        hashlib.sha256(path.read_bytes()).hexdigest(): path for path in expected.values()
    }
    for row in uploaded:
        key = Path(row["key"])
        if key.is_absolute() or ".." in key.parts:
            raise ValueError("Unsafe attachment path")
        # Clipboard uploads keep a generic filename. Match only exact source bytes within
        # the already-allowlisted review documents, without adopting owner screenshots.
        if key.name not in expected and key.name != "clipboard.jpeg":
            continue
        remote_hash = run(
            [
                "docker",
                "exec",
                "rhp-outline-app",
                "sha256sum",  # noqa: S607
                str(Path("/var/lib/outline/data") / key),
            ]
        ).split()[0]
        local = expected.get(key.name) or expected_hashes.get(remote_hash)
        if local is None:
            continue
        local_hash = hashlib.sha256(local.read_bytes()).hexdigest()
        if local_hash == remote_hash:
            inventory[local.relative_to(ROOT).as_posix()] = {
                "id": row["id"],
                "document": row["documentId"],
                "sha256": local_hash,
            }
    missing = set(expected) - {Path(path).name for path in inventory}
    if missing:
        raise RuntimeError(f"Missing or stale Design uploads: {', '.join(sorted(missing))}")
    manifest = DESIGN / "outline-assets.json"
    if args.record:
        manifest.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    elif json.loads(manifest.read_text()) != inventory:
        raise RuntimeError("Design attachment IDs or hashes differ from recorded publication")
    print(  # noqa: T201
        f"Verified {len(inventory)} Design uploads against source hashes; no service data changed"
    )


if __name__ == "__main__":
    main()
