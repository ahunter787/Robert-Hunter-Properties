"""Archive RHP only, verify a restore, and create a separate empty development database.

Never edits environment settings, drops a database, or touches ecosystem services. Requires Docker
access and explicit --apply. Archives contain private data and belong outside version control.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose"]


def command(args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)  # noqa: S603


def db(args, **kwargs):
    return command([*COMPOSE, "exec", "-T", "db", *args], **kwargs)


def counts(user, name):
    sql = """SELECT table_name FROM information_schema.tables
             WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"""
    tables = db(
        ["psql", "-U", user, "-d", name, "-Atc", sql], capture_output=True, text=True
    ).stdout.splitlines()
    result = {}
    for table in tables:
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", table):
            raise ValueError("Unexpected table identifier")
        result[table] = int(
            db(
                ["psql", "-U", user, "-d", name, "-Atc", f'SELECT count(*) FROM "{table}"'],  # noqa: S608 - identifier validated above
                capture_output=True,
                text=True,
            ).stdout
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--new-database", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"rhp_cutover_dev_[a-z0-9_]+", args.new_database):
        parser.error("Use an explicit rhp_cutover_dev_... database name")
    if not args.apply:
        print(  # noqa: T201 - explicit CLI output
            "Dry run: archive current RHP database/media, restore-check, create separate empty DB. "
            "No drops or settings edits."
        )
        return
    os.umask(0o077)
    identity = command(
        [
            *COMPOSE,
            "exec",
            "-T",
            "web",
            "python",
            "manage.py",
            "shell",
            "-c",
            "from django.conf import settings; import json; "
            "print(json.dumps({'db': settings.DATABASES['default']['NAME'], "
            "'user': settings.DATABASES['default']['USER'], 'media': settings.MEDIA_ROOT, "
            "'development': settings.DEBUG}))",
        ],
        capture_output=True,
        text=True,
    ).stdout
    config = json.loads(identity.strip().splitlines()[-1])
    if not config["development"]:
        raise ValueError("Refusing to run development initialization against production settings")
    if config["db"] == args.new_database:
        raise ValueError("Refusing to reuse the current database")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    archive = ROOT / ".uv-cache" / "cutover-backups" / stamp
    archive.mkdir(parents=True, mode=0o700)
    dump = archive / "rhp.dump"
    with dump.open("xb") as stream:
        db(["pg_dump", "-U", config["user"], "-d", config["db"], "-Fc"], stdout=stream)
    media = archive / "media.tar"
    with media.open("xb") as stream:
        command(
            [*COMPOSE, "exec", "-T", "web", "tar", "-C", config["media"], "-cf", "-", "."],
            stdout=stream,
        )
    scratch = "rhp_restore_" + uuid4().hex[:16]
    db(["createdb", "-U", config["user"], scratch])
    with dump.open("rb") as stream:
        db(
            ["pg_restore", "-U", config["user"], "-d", scratch, "--exit-on-error", "--no-owner"],
            stdin=stream,
            capture_output=True,
        )
    restored = counts(config["user"], scratch)
    original = counts(config["user"], config["db"])
    if restored != original:
        raise ValueError(
            f"Source changed or restore counts differ; archive retained at {archive}. "
            "No fresh database created."
        )
    restored_media = archive / "restored-media"
    restored_media.mkdir(mode=0o700)
    with tarfile.open(media) as bundle:
        bundle.extractall(restored_media, filter="data")
    db(["createdb", "-U", config["user"], args.new_database])
    manifest = {
        "created_at": stamp,
        "original_database": config["db"],
        "restored_database": scratch,
        "new_empty_database": args.new_database,
        "table_counts": restored,
        "restore_verified": True,
        "sha256": {
            p.name: hashlib.file_digest(p.open("rb"), "sha256").hexdigest() for p in (dump, media)
        },
        "restore": (
            "Use pg_restore --exit-on-error --no-owner into a NEW named database. "
            "Extract media.tar into a NEW private directory; verify checksums first. "
            "Original database/media retained. Repoint development after migration and review. "
            "Never use this as a production reset."
        ),
    }
    (archive / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Archive and restore verified: {archive}")  # noqa: T201
    print(f"Original retained; scratch retained; empty database created: {args.new_database}")  # noqa: T201


if __name__ == "__main__":
    main()
