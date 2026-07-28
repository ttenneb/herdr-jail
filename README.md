# Herdr Jail

A [Herdr](https://herdr.dev) plugin that runs coding agents inside
[yolo-jail](https://github.com/mschulkind-oss/yolo-jail) sandboxes.

Three features:

1. **Parent-jail reuse** — when you launch an agent in a pane whose directory
   is a *subdirectory* of another pane's jail (in the same Herdr Checkout),
   the plugin prompts to **join the existing parent jail** instead of spawning
   a brand-new one. (yolo-jail already reuses a jail for the *same* directory;
   this extends that to descendants.)
2. **Enforce jailing** — a best-effort watchdog: launches go through
   `yolo -- <agent>`, and if a supported agent is detected running *outside* a
   jail, the plugin warns and marks the pane.
3. **Jail tree** — a supplementary pane that visualizes running jails grouped
   under their Herdr Checkouts; actionable jail children appear in Spaces.

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

Requires a Herdr build with Workspace Resource support (the planned minimum is
0.7.6, pending release confirmation; see `INTEGRATION_NOTES.md`), yolo-jail,
Podman (as configured for yolo-jail),
`jq`, and Python 3.9+. The scripts treat both JSON tools as required dependencies
and fail clearly rather than skipping validation when either is unavailable.

## Actions

| Action | id | What it does |
|---|---|---|
| Run agent in jail | `hs.jail.run` | Launch a supported agent jailed; reuse a parent jail if present (feature #1 + #2). |
| Open Jail Tree | `hs.jail.open-tree` | Open the jail-tree pane (feature #3). |
| Migrate agent into jail | `hs.jail.migrate` | Stop an un-jailed agent in the pane and relaunch it jailed, resuming where possible (manual recovery). |
| Jails… | `hs.jail.jails` | Choose a live jail attributed to the Checkout, then open or close it. |

Set the agent with `HERDR_JAIL_AGENT` (default `claude`). Supported:
`claude pi codex gemini opencode copilot`.

## Jail resources in Spaces

The refresher reports structured Workspace Resources. Herdr renders each live
jail as a `🔒` child of every attached Checkout; a shared jail appears below
all of its Checkouts. Right-clicking a Checkout keeps aggregate Open/Close
choices. Right-clicking a jail child targets that exact immutable Podman
container; Close states when it affects every attachment.

No `[ui.sidebar.spaces]` jail rows or `$giticon`/`$jails`/`$jail1`–`$jail5`
tokens are needed. On each successful refresh this version clears those legacy
tokens for known Checkouts. The standalone Jail Tree pane remains available.

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
one's `YOLO_HOST_DIR` env label — that maps a jail to its Checkout directory.

The refresher invokes `herdr workspace report-resources <checkout> --plugin
hs.jail --file <path> --ttl-ms <n>` with one replacement resource set
per Checkout. A report failure is never treated as an empty set. Each resource
uses the full immutable Podman ID and a canonically sorted attachment-set
fingerprint. The **Jails…** action uses Herdr's plugin action choices protocol;
before acting it re-queries Podman and a fresh Herdr snapshot and requires the
same immutable ID and attachment fingerprint. A stale/replaced container or a
changed shared attachment set fails closed (reopen the menu). Open uses
`podman exec` with that full immutable ID for both the agent and shell panes;
a repository beneath the jail root is mapped under `/workspace`, while an
unrelated repository path is rejected.

This plugin requires the Herdr release that supports Workspace Resources and
`workspace_resource` action contexts. The overlay remains only as a direct
invocation fallback.

## Gotchas

- **Opening a running jail favors exact identity over lifecycle refresh.** The
  Open action uses `podman exec` with the selected full container ID so a
  same-name replacement cannot be targeted accidentally. This retains the
  existing container sandbox, but bypasses the normal host-side `yolo` attach
  maintenance and in-container `yolo-entrypoint` regeneration. The plugin
  restores the user environment, Mise environment, and yolo shim path, but a
  long-running jail can retain stale generated shims, agent/MCP configuration,
  CA setup, briefings, or broker-relay state after related configuration
  changes. Restart or normally reattach to the jail when those inputs change.
  **TODO:** switch to an immutable-ID-aware yolo-jail attach operation when one
  is available.

### Pending hardening

The following review findings are known and intentionally tracked rather than
silently treated as guarantees:

- **Open completion is currently submission-based.** `herdr pane run` confirms
  that Herdr accepted the command, not that the inner `podman exec`, bootstrap,
  shell, or agent remained running. An inner startup failure can therefore be
  logged as a successful Open. **TODO:** emit and await per-pane readiness
  markers, then use agent detection where applicable.
- **Interrupted Open operations can leave partial tabs.** Explicit failures use
  cleanup paths, but interruption or an unexpected shell exit after tab
  creation can leave an empty or half-initialized tab. **TODO:** add guarded
  `EXIT`, `INT`, and `TERM` cleanup that is disarmed only after verified startup.
- **Checkout attribution is not atomic with Open.** Attribution is checked
  before panes are created and container identity is checked again before
  dispatch, but the Checkout's panes can move in between. The immutable ID
  still prevents targeting a same-name replacement. **TODO:** repeat attribution
  immediately before dispatch to narrow the logical race.
- **Native choices expose at most 32 jails.** Herdr permits 64 choices and each
  jail consumes an Open and Close row. This is an intentional bounded-provider
  limit; use the fallback picker if a Checkout exceeds it. Pagination can be
  added if this becomes a practical constraint.

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
- **The Jail Tree is supplementary.** Live jail resources are actionable
  children beneath Checkouts in Spaces; the Jail Tree pane remains a separate
  overview surface.
- `pane.created` / `workspace.created` event payloads are not fully documented
  upstream; the plugin relies on `agent`/`pane_id` fields observed at runtime.

## Layout

```
herdr-plugin.toml   manifest (actions, events, panes)
bin/lib.sh          shared helpers: PATH fixup, jail discovery
bin/jail-run.sh     action: launch agent jailed (+ parent-jail reuse)
bin/enforce.sh      event handler: flag un-jailed agents
bin/jail-tree.sh    pane: gather data, render loop
bin/resource-graph.py complete validated jail→Checkout attachment graph
bin/group.py        Jail Tree grouping (deepest-ancestor attribution)
bin/open-tree.sh    action: open the jail-tree pane
bin/jail-menu-provider.sh  native action choices provider
bin/jail-menu.sh    selected-choice validation/invocation + overlay fallback
bin/jail-menu-ui.sh overlay picker fallback
bin/jail-choice.py  strict choice JSON encoder/decoder
bin/jail-ops.sh     validated open/close operations
```
