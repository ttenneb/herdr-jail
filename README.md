# Herdr Jail

A [Herdr](https://herdr.dev) plugin that runs coding agents inside
[yolo-jail](https://github.com/mschulkind-oss/yolo-jail) sandboxes.

Three features:

1. **Parent-jail reuse** — when you launch an agent in a pane whose directory
   is a *subdirectory* of another pane's jail (in the same Herdr workspace),
   the plugin prompts to **join the existing parent jail** instead of spawning
   a brand-new one. (yolo-jail already reuses a jail for the *same* directory;
   this extends that to descendants.)
2. **Enforce jailing** — a best-effort watchdog: launches go through
   `yolo -- <agent>`, and if a supported agent is detected running *outside* a
   jail, the plugin warns and marks the pane.
3. **Jail tree** — a pane that visualizes running jails grouped under their
   Herdr workspaces.

## Install

```sh
# local dev
herdr plugin link /path/to/herdr-jail
herdr plugin list        # should show hs.jail

# keybindings (optional) — add to ~/.config/herdr/config.toml
# [[keys.command]]
# key = "prefix+j"
# type = "plugin_action"
# command = "hs.jail.run"
#
# [[keys.command]]
# key = "prefix+shift+j"
# type = "plugin_action"
# command = "hs.jail.open-tree"
```

Requires Herdr 0.7.0+, yolo-jail, and Podman (as configured for yolo-jail).

## Actions

| Action | id | What it does |
|---|---|---|
| Run agent in jail | `hs.jail.run` | Launch a supported agent jailed; reuse a parent jail if present (feature #1 + #2). |
| Open Jail Tree | `hs.jail.open-tree` | Open the jail-tree pane (feature #3). |
| Migrate agent into jail | `hs.jail.migrate` | Stop an un-jailed agent in the pane and relaunch it jailed, resuming where possible (manual recovery). |

Set the agent with `HERDR_JAIL_AGENT` (default `claude`). Supported:
`claude pi codex gemini opencode copilot`.

## How it works

Herdr runs plugin `command`s as short-lived processes with context in env
vars (`HERDR_PANE_ID`, `HERDR_PLUGIN_CONTEXT_JSON`, `HERDR_BIN_PATH`, …) and a
**minimal PATH**. The scripts therefore resolve `yolo`/`podman`/`jq`
explicitly (see `bin/lib.sh`) and drive Herdr via the `herdr` CLI. Jails are
discovered by querying `podman` for containers named `yolo-*` and reading each
one's `YOLO_HOST_DIR` env label — that maps a jail to its workspace directory.

## Known limitations

- **`migrate` is recovery, not prevention.** The migrate action stops a
  running un-jailed agent and relaunches it jailed with resume (Claude:
  `--continue`; other agents may start fresh). It is destructive (interrupts
  in-flight work) and leaves the pre-migration un-jailed window, so it is a
  manual convenience, never automatic. A live host process cannot be moved
  into the container (different kernel/VM); migration = kill + jailed relaunch.
- **Enforcement is best-effort, not airtight.** Herdr exposes no
  launch-interception hook, so an agent a user types manually in a raw shell
  can still start un-jailed. The watchdog *detects and flags* that after the
  fact (via `pane.agent_detected`) but cannot prevent it. ("Attempt to
  enforce" — hardening is future work.)
- **The jail tree is a pane, not a sidebar node.** Herdr's plugin API has no
  workspace-tree/sidebar extension surface (the workspace→tab→pane hierarchy is
  fixed), so jails are visualized in a dedicated plugin pane rather than nested
  under workspaces in the native sidebar. The alternative — decorating existing
  rows via `pane report-metadata` tokens — is used by the enforcement watchdog
  to mark un-jailed panes.
- `pane.created` / `workspace.created` event payloads are not fully documented
  upstream; the plugin relies on `agent`/`pane_id` fields observed at runtime.

## Layout

```
herdr-plugin.toml   manifest (actions, events, panes)
bin/lib.sh          shared helpers: PATH fixup, jail discovery
bin/jail-run.sh     action: launch agent jailed (+ parent-jail reuse)
bin/enforce.sh      event handler: flag un-jailed agents
bin/jail-tree.sh    pane: gather data, render loop
bin/group.py        jail→workspace grouping (deepest-ancestor attribution)
bin/open-tree.sh    action: open the jail-tree pane
```
