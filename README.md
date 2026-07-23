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

## Jail indicator in the workspaces sidebar (native)

Each workspace row can show a live jail count (🔒N) in Herdr's own sidebar —
not a separate pane. A `[[startup]]` refresher keeps a `$jails` metadata token
current per workspace (set on jail boot, cleared on stop).

Herdr renders reported tokens only if the row layout references them, so add to
`~/.config/herdr/config.toml`:

```toml
[ui.sidebar.spaces]
rows = [["state_icon", "workspace"], ["branch", "git_status"], ["$jails"]]
```

Note: Herdr's plugin API cannot add a *new expandable node type* under a
workspace (the workspace→tab→pane tree is fixed). This puts the jail indicator
on the workspace's own row instead — the closest the native sidebar allows.
The standalone Jail Tree pane remains for a full grouped view.

## Enforce jailing (auto-jail every agent in Herdr)

The plugin actions above are opt-in (you invoke them). For **automatic**
jailing — where typing `claude`/`pi`/etc. in any Herdr pane always runs jailed —
point Herdr's shell at the enforcing wrapper. This is shell-level, not a plugin
action, because Herdr has no launch-interception hook.

```sh
# 1. Install the shims (symlinks per agent -> bin/jail-shim)
bin/install-shims.sh                      # -> ~/.herdr-jail-shims

# 2. Point Herdr at the enforcing shell — add to ~/.config/herdr/config.toml:
[terminal]
default_shell = "/ABSOLUTE/PATH/TO/herdr-jail/bin/herdr-jail-shell"

# 3. Reload
herdr server reload-config
```

Now every supported agent launched in a Herdr pane is auto-wrapped as
`yolo -- <agent>`. Bypass a single invocation with `YOLO_BYPASS=1 <agent>`.

**How it stays robust and non-invasive:** the wrapper launches zsh with a
custom `ZDOTDIR` (`zdotdir/`) whose `.zshrc` sources *your* real config first
(mise, pyenv, PATH edits, everything), then prepends the shim dir **last** — so
the shims win the PATH race no matter what your config or macOS `path_helper`
does. Your own rc files are read, never modified. Outside Herdr, nothing
changes: your normal shells don't use this wrapper, so agents run un-jailed
there as usual.

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
