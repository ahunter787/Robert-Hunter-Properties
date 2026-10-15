---
name: project-ecosystem
description: Use when this project's development ecosystem needs to be checked, used or reported on — its Plane work items, its Outline documentation, or its Mailpit mail sink — or when the plan and the documentation must be republished into them.
---

This project keeps its ticketing, documentation and mail sink in a **development ecosystem**: Plane,
Outline and Mailpit. It is not the application, and it never touches the application's own containers,
volumes or ports.

## First, find out which shape this project uses

1. **Inside the workspace.** If `ecosystem/` exists here, the ecosystem lives in this checkout. Read
   `ecosystem/README.md` and follow it; every command is `make -C ecosystem …`, and everything it
   generates lives under `ecosystem/.runtime/`.
2. **Its own repository.** Otherwise the ecosystem lives elsewhere: `AGENTS.md` in this checkout says
   where, and that repository's `README.md` is the runbook. Every command is
   `make -C <tooling-path> …`.

Either way, read that runbook before acting. It holds the traps in both products and the manual
fallback for every automated step, so nobody has to improvise.

## What is true in both shapes

- The **plan of record** is `docs/roadmap.md` (the phases) and `docs/extensions.md` (the register) in
  this checkout. Plane is a *mirror* of them: change the documents, then re-run the sync — never the
  other way round.
- The ecosystem only ever **reads** this checkout: the tracked markdown it publishes, and those two
  documents. It never writes back.
- **Both syncs are dry by default and idempotent.** Neither ever deletes anything: they report drift
  and leave the decision to a person.

## The commands

Where the ecosystem is inside the workspace:

```bash
make -C ecosystem health                   # what answers, and which port belongs to whom
make -C ecosystem docs-sync                # dry run: what would change in Outline
make -C ecosystem docs-sync ARGS=--apply
make -C ecosystem plane-sync               # dry run: what would change in Plane
make -C ecosystem plane-sync ARGS=--apply
make -C ecosystem verify                   # the exit criterion, below
make -C ecosystem mailbox | backup | ps | logs S=plane
```

Where it is its own repository — substitute the path `AGENTS.md` names for `<tooling-path>`:

```bash
make -C <tooling-path> health
make -C <tooling-path> docs-sync [ARGS=--apply]
make -C <tooling-path> plane-sync [ARGS=--apply]
make -C <tooling-path> verify            # where the tooling has it
make -C <tooling-path> mailbox | backup | ps | logs S=plane
```

## How you know the two sides agree

**`verify` is the exit criterion** where the tooling has it: it fails, naming the file or the item, when
the plan and the published copies disagree, when a recorded document has vanished, or when a sync would
change something. Run it before reporting that anything is consistent.

Where an older tooling has no `verify`, the equivalent is: `health` is green, and both syncs report
nothing to do — the documentation sync `would create 0 and update 0`, the roadmap sync
`would create 0, update 0`.

## Hard rules

- **Never stop, prune or reconfigure** the ecosystem's containers, and never run
  `docker system prune` or `docker volume prune`: their datastores look unused whenever the stack is
  stopped, and pruning destroys them.
- **Never bind the ecosystem's ports.** Inside the workspace they are the ones in
  `ecosystem/.runtime/env`; in its own repository they are listed in that repository's `.env` and
  `AGENTS.md`.
- **Never `git add -A`** or `git add .` — stage the paths you changed.
- **Never edit Plane to change the plan.** Edit `docs/roadmap.md` or `docs/extensions.md` and re-run
  `plane-sync`.
- **Never delete** a published document or work item because it looks stale. Report it; removing it is
  the owner's decision. Both syncs report drift rather than acting on it.
- **Never commit generated secrets**: `ecosystem/.runtime/` where the ecosystem is in the workspace, or
  the tooling repository's `secrets/`, `.env` and `plane/plane-app/` where it is not.
- The ecosystem's own files are not yours to change as a side effect of other work. If a change there
  looks necessary, stop and ask.

## Handing over

Give the tooling's `AGENT-BRIEFING.md` — in its own repository — to any other agent or workstream
working in this checkout, so it leaves the containers, the ports and the datastores alone. (Where the
ecosystem is inside the workspace, the section the scaffold appended to `AGENTS.md` is that notice.)
