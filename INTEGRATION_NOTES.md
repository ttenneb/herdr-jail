# Herdr Workspace Resource integration assumptions

This plugin calls the planned CLI exactly:

```sh
herdr workspace report-resources <workspace> --plugin hs.jail --file <path> --ttl-ms <n>
```

`--file` contains a JSON array of `WorkspaceResourceInput` objects. The
reporter sends one replacement report (including `[]`) for every workspace
returned by `workspace list`. It deliberately omits `--seq`, because Herdr
retains monotonic sequence state across reporter restarts; it sends nothing
when Podman, the workspace list, the snapshot, or graph validation fails.

The refresher uses Python's portable `fcntl.flock` helper rather than an
external `flock` binary. It opens a no-follow UID-owned regular lock file in a
private UID runtime directory and retains the advisory FD across `exec`.

The action code expects `HERDR_PLUGIN_CONTEXT_JSON.workspace_resource` for a
resource invocation, shaped as a `WorkspaceResourceInfo` object with
`plugin_id`, `resource_id`, and `data`. It requires `plugin_id == "hs.jail"`,
`resource_id == data.container_id`, and
`data.attachment_fingerprint`. If Herdr names this selected-resource field
otherwise, adapt only the two jq reads in `bin/jail-menu-provider.sh` and
`bin/jail-menu.sh`; retain these owner, immutable-ID, and fingerprint checks.

The selected child resource's `data` is emitted as:
`{container_name, container_id, attachments, attachment_fingerprint}`. The
attachment list is bytewise UTF-8 sorted and its fingerprint is SHA-256 of the
compact UTF-8 JSON list. This is intentionally plugin-owned context, not a
Herdr identity.

The manifest provisionally declares `min_herdr_version = "0.7.6"`. Herdr
0.7.5 is already released and does not contain Workspace Resources, even
though the unreleased Herdr worktree still identifies as 0.7.5. Confirm that
0.7.6 is the first released version containing `workspace_resource` contexts
and `report-resources`, and raise this minimum if the feature lands later.
