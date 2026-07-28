#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHOICE = ROOT / "bin" / "jail-choice.py"
MENU = ROOT / "bin" / "jail-menu.sh"
OPS = ROOT / "bin" / "jail-ops.sh"
PROVIDER = ROOT / "bin" / "jail-menu-provider.sh"
SNAPSHOT = ROOT / "tests" / "fixtures" / "snapshot-attached.json"
CONTAINER_ID = "a" * 64
ATTACHMENTS = ["ws-1"]
FINGERPRINT = hashlib.sha256(json.dumps(ATTACHMENTS, separators=(",", ":")).encode()).hexdigest()


def choice_label(operation, container):
    name = container.removeprefix("yolo-")
    if len(name) > 32:
        name = f"{name[:23]}…{name[-8:]}"
    verb = "Open" if operation == "open" else "Close"
    return f"{verb} {name}"


def choice(operation="close", container="yolo-project-abc", container_id=CONTAINER_ID):
    return json.dumps({
        "id": f"{operation}:{container_id}",
        "label": choice_label(operation, container),
        "payload": {"operation": operation, "container": {"name": container, "id": container_id, "attachments": ATTACHMENTS, "attachment_fingerprint": FINGERPRINT}},
    })


def run_codec(mode, value):
    return subprocess.run(["python3", str(CHOICE), mode], input=value, text=True, capture_output=True)


class ChoiceCodecTests(unittest.TestCase):
    def test_emit_is_strict_version_one_json(self):
        run = run_codec("emit", f"yolo-project-abc\t/tmp/project\tpi\t{CONTAINER_ID}\tws-1\t{FINGERPRINT}\n")
        self.assertEqual(run.returncode, 0, run.stderr)
        doc = json.loads(run.stdout)
        self.assertEqual(doc["version"], 1)
        self.assertEqual([item["id"] for item in doc["choices"]], [
            f"open:{CONTAINER_ID}", f"close:{CONTAINER_ID}"
        ])
        self.assertEqual(doc["choices"][0]["payload"]["container"], {
            "name": "yolo-project-abc", "id": CONTAINER_ID, "attachments": ATTACHMENTS, "attachment_fingerprint": FINGERPRINT
        })
        self.assertEqual([item["label"] for item in doc["choices"]], [
            "Open project-abc", "Close project-abc"
        ])

    def test_labels_cap_display_name_and_preserve_identity_suffix(self):
        name = "yolo-" + ("a" * 40) + "-deadbeef"
        run = run_codec("emit", f"{name}\t/tmp/project\tpi\t{CONTAINER_ID}\tws-1\t{FINGERPRINT}\n")
        self.assertEqual(run.returncode, 0, run.stderr)
        labels = [item["label"] for item in json.loads(run.stdout)["choices"]]
        shown = ("a" * 23) + "…deadbeef"
        self.assertEqual(labels, [f"Open {shown}", f"Close {shown}"])
        self.assertEqual(len(shown), 32)

    def test_emit_is_bytewise_sorted_and_capped_before_65(self):
        rows = [
            f"yolo-jail-{i:02d}\t/tmp/{i:02d}\tpi\t{i + 1:064x}\tws-1\t{FINGERPRINT}"
            for i in range(40)
        ]
        forward = run_codec("emit", "\n".join(rows) + "\n")
        reverse = run_codec("emit", "\n".join(reversed(rows)) + "\n")
        self.assertEqual(forward.stdout, reverse.stdout)
        choices = json.loads(forward.stdout)["choices"]
        self.assertEqual(len(choices), 64)
        names = [item["payload"]["container"]["name"] for item in choices[::2]]
        self.assertEqual(names, [f"yolo-jail-{i:02d}" for i in range(32)])

    def test_parse_rejects_unknown_operation_duplicate_keys_and_bad_identity(self):
        values = [
            choice("destroy"),
            choice().replace('"id":', '"id":"duplicate","id":', 1),
            json.dumps({
                "id": f"close:{CONTAINER_ID}", "label": "Close Jail oth...",
                "payload": {"operation": "close", "container": {
                    "name": "yolo-project-abc", "id": CONTAINER_ID
                }},
            }),
        ]
        for value in values:
            self.assertNotEqual(run_codec("parse", value).returncode, 0)

    def test_requires_full_64_hex_identity(self):
        short_id = "a" * 63
        self.assertNotEqual(run_codec("parse", choice(container_id=short_id)).returncode, 0)
        emitted = json.loads(run_codec(
            "emit", f"yolo-project-abc\t/tmp/project\tpi\t{short_id}\tws-1\t{FINGERPRINT}\n"
        ).stdout)
        self.assertEqual(emitted["choices"], [])

    def test_invalid_herdr_bin_falls_back_to_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "herdr"
            fake.write_text("#!/bin/sh\nprintf fallback-ok\n")
            fake.chmod(0o755)
            run = subprocess.run(
                ["/bin/bash", "-c", '. bin/lib.sh; "$HERDR"'],
                cwd=ROOT,
                env={
                    "HOME": str(Path(tmp) / "home"),
                    "PATH": tmp,
                    "HERDR_BIN_PATH": str(Path(tmp) / "herdr (deleted)"),
                },
                text=True,
                capture_output=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "fallback-ok")

    def test_shell_quote_preserves_hostile_path_as_one_literal(self):
        hostile = "/tmp/a path/'quote;$(touch /tmp/herdr-jail-injected)"
        marker = Path("/tmp/herdr-jail-injected")
        marker.unlink(missing_ok=True)
        run = subprocess.run(
            ["bash", "-c", '. bin/lib.sh; q=$(shell_quote "$VALUE"); bash -c "printf %s $q"'],
            cwd=ROOT, env={**os.environ, "VALUE": hostile}, text=True, capture_output=True, check=True,
        )
        self.assertEqual(run.stdout, hostile)
        self.assertFalse(marker.exists())


class FakeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin = root / "bin"
        self.bin.mkdir()
        self.stop_log = root / "stops"
        self.herdr_log = root / "herdr.log"
        self.snapshot = root / "snapshot.json"
        self.snapshot.write_text(SNAPSHOT.read_text())
        self.container_home = root / "container-home"
        (self.container_home / ".config").mkdir(parents=True)
        (self.container_home / ".yolo-shims").mkdir()
        (self.container_home / ".config" / "yolo-user-env.sh").write_text(
            'export PATH=/bin:/usr/bin\n'
            'mise() { printf \'export FAKE_MISE_LOADED=1\\n\'; }\n'
        )
        (self.container_home / ".yolo-shims" / "pi").write_text("""#!/bin/bash
printf 'PATH=%s\\nMISE=%s\\nPWD=%s\\nARGS=%s\\n' \
  "$PATH" "${FAKE_MISE_LOADED:-}" "$PWD" "$*" > "$FAKE_AGENT_LOG"
""")
        (self.container_home / ".yolo-shims" / "pi").chmod(0o755)
        self.container_workdir = root / "container-workspace" / "subdir"
        self.container_workdir.mkdir(parents=True)

        (self.bin / "podman").write_text("""#!/bin/bash
case "$1" in
  ps)
    [ "${FAKE_PS_FAIL:-}" = 1 ] && exit 1
    printf '%s\\n' "${FAKE_JAIL_NAME:-yolo-project-abc}" ;;
  inspect)
    [ "${FAKE_INSPECT_FAIL:-}" = 1 ] && exit 1
    if [[ "$*" == *"{{.Id}}"* ]]; then
      [ -n "${FAKE_IDENTITY_FAIL_NAME:-}" ] && [ "$2" = "$FAKE_IDENTITY_FAIL_NAME" ] && exit 1
      if [ "${FAKE_MULTI_JAIL:-}" = 1 ]; then
        case "$2" in
          yolo-alpha-abc) printf '%064x\\n' 10 ;;
          yolo-beta-abc) printf '%064x\\n' 11 ;;
          *) exit 1 ;;
        esac
        exit 0
      fi
      count=0; [ -f "$FAKE_INSPECT_COUNT" ] && count="$(cat "$FAKE_INSPECT_COUNT")"
      count=$((count + 1)); printf '%s' "$count" > "$FAKE_INSPECT_COUNT"
      [ "${FAKE_REMOVE_AFTER_FIRST:-}" = 1 ] && [ "$count" -gt 1 ] && exit 1
      if [ "${FAKE_REPLACE_AFTER_FIRST:-}" = 1 ] && [ "$count" -gt 1 ]; then
        printf '%s\\n' 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
      else
        printf '%s\\n' "${FAKE_CONTAINER_ID:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}"
      fi
    else
      [ "${FAKE_HOST_INSPECT_FAIL:-}" = 1 ] && exit 1
      if [ "${FAKE_HOST_DIR_MISSING:-}" != 1 ]; then
        if [ "${FAKE_MULTI_JAIL:-}" = 1 ]; then
          case "$2" in
            yolo-alpha-abc) printf 'YOLO_HOST_DIR=/tmp/alpha\\n' ;;
            yolo-beta-abc) printf 'YOLO_HOST_DIR=/tmp/beta\\n' ;;
            *) exit 1 ;;
          esac
        else
          printf 'YOLO_HOST_DIR=%s\\n' "${FAKE_JAIL_DIR:-/tmp/project}"
        fi
      fi
    fi ;;
  stop) printf '%s\\n' "$2" >> "$FAKE_STOP_LOG" ;;
  exec)
    shift
    [ "$1" = -it ] || exit 3; shift
    [ "$1" = --workdir ] || exit 3; workdir="$2"; shift 2
    [ "$1" = "${FAKE_CONTAINER_ID:-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}" ] || exit 3
    shift
    [ "${FAKE_EXEC_CONTAINER:-}" = 1 ] || exit 0
    if [ "$1" = /bin/bash ] && [ "$2" = -lc ]; then
      script="${3//\\/workspace\\/subdir/$FAKE_CONTAINER_WORKDIR}"
      HOME="$FAKE_CONTAINER_HOME" PATH=/bin:/usr/bin FAKE_AGENT_LOG="$FAKE_AGENT_LOG" "$1" "$2" "$script"
    else
      exit 3
    fi ;;
  *) exit 2 ;;
esac
""")
        (self.bin / "podman").chmod(0o755)
        (self.bin / "herdr").write_text("""#!/bin/bash
printf '%s' "$1" >> "$FAKE_HERDR_LOG"
for arg in "${@:2}"; do printf '\\t%s' "$arg" >> "$FAKE_HERDR_LOG"; done
printf '\\n' >> "$FAKE_HERDR_LOG"
case "$1 $2" in
  "workspace list") printf '%s\\n' '{"result":{"workspaces":[{"workspace_id":"ws-1"}]}}' ;;
  "api snapshot") cat "$FAKE_SNAPSHOT" ;;
  "notification show") exit 0 ;;
  "tab create")
    [ "${FAKE_FAIL_AT:-}" = tab-create ] && exit 1
    printf '%s\\n' '{"result":{"root_pane":{"pane_id":"left-pane"},"tab":{"tab_id":"new-tab"}}}' ;;
  "tab close") exit 0 ;;
  "pane split")
    [ "${FAKE_FAIL_AT:-}" = split ] && exit 1
    printf '%s\\n' '{"result":{"pane":{"pane_id":"right-pane"}}}' ;;
  "pane run")
    pane="$3"; command="$4"
    if [[ "$command" == *"__hj_ready_"* ]]; then
      [ "${FAKE_FAIL_AT:-}" = ready-run ] && exit 1
    elif [[ "$command" == *"podman"*" exec "* ]]; then
      [ "${FAKE_FAIL_AT:-}" = "run-$pane" ] && exit 1
      if [ "${FAKE_EXEC_CONTAINER:-}" = 1 ] && [ "$pane" = left-pane ]; then
        command="${command#clear && exec }"
        PATH=/bin:/usr/bin /bin/bash -c "exec $command"
      fi
    fi
    exit 0 ;;
  "pane wait-output") [ "${FAKE_FAIL_AT:-}" = wait ] && exit 1 || exit 0 ;;
  *) exit 2 ;;
esac
""")
        (self.bin / "herdr").chmod(0o755)

    def env(self, repo="/tmp/project"):
        env = os.environ.copy()
        env.update({
            "PATH": f"{self.bin}:{env.get('PATH', '')}",
            "HERDR_BIN_PATH": str(self.bin / "herdr"),
            "PODMAN_BIN_PATH": str(self.bin / "podman"),
            "HERDR_WORKSPACE_ID": "ws-1",
            "HERDR_PLUGIN_CONTEXT_JSON": json.dumps({"workspace_id": "ws-1", "workspace_cwd": repo}),
            "FAKE_SNAPSHOT": str(self.snapshot),
            "FAKE_STOP_LOG": str(self.stop_log),
            "FAKE_HERDR_LOG": str(self.herdr_log),
            "FAKE_INSPECT_COUNT": str(Path(self.tmp.name) / "inspect-count"),
            "FAKE_CONTAINER_HOME": str(self.container_home),
            "FAKE_AGENT_LOG": str(Path(self.tmp.name) / "agent.log"),
            "FAKE_CONTAINER_WORKDIR": str(self.container_workdir),
        })
        return env

    def herdr_lines(self):
        return self.herdr_log.read_text().splitlines() if self.herdr_log.exists() else []

    def run_ops(self, repo="/tmp/project/subdir", **extra_env):
        env = self.env(repo)
        env.update(extra_env)
        return subprocess.run([
            "bash", str(OPS), "open", "ws-1", "yolo-project-abc",
            "/tmp/project", "pi", CONTAINER_ID, repo,
        ], env=env, text=True, capture_output=True)

    def test_provider_uses_live_fixture_mapping(self):
        run = subprocess.run(["bash", str(PROVIDER)], env=self.env(), text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual([item["id"] for item in json.loads(run.stdout)["choices"]], [
            f"open:{CONTAINER_ID}", f"close:{CONTAINER_ID}"
        ])

    def test_provider_rejects_multi_jail_partial_identity_failure(self):
        self.snapshot.write_text(json.dumps({"result": {"snapshot": {"panes": [
            {"workspace_id": "ws-1", "foreground_cwd": "/tmp/alpha/sub", "revision": 1},
            {"workspace_id": "ws-1", "foreground_cwd": "/tmp/beta/sub", "revision": 2},
        ]}}}))
        env = self.env()
        env.update({
            "FAKE_MULTI_JAIL": "1",
            "FAKE_JAIL_NAME": "yolo-alpha-abc\nyolo-beta-abc",
            "FAKE_IDENTITY_FAIL_NAME": "yolo-beta-abc",
        })
        run = subprocess.run(["bash", str(PROVIDER)], env=env, text=True, capture_output=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "")
        self.assertIn("could not resolve immutable container ID", run.stderr)
        self.assertIn("could not validate every attributed jail", run.stderr)

    def test_open_execs_bootstrapped_agent_and_shell_in_exact_container(self):
        run = self.run_ops()
        self.assertEqual(run.returncode, 0, run.stderr)
        commands = {
            fields[2]: fields[3]
            for line in self.herdr_lines()
            if (fields := line.split("\t", 3))[:2] == ["pane", "run"]
            and len(fields) == 4 and " exec " in fields[3]
        }
        self.assertEqual(set(commands), {"left-pane", "right-pane"})

        agent_argv = shlex.split(commands["left-pane"].removeprefix("clear && exec "))
        shell_argv = shlex.split(commands["right-pane"].removeprefix("clear && exec "))
        common = [str(self.bin / "podman"), "exec", "-it", "--workdir"]
        self.assertEqual(len(agent_argv), 9)  # inner script is one podman-exec argv
        self.assertEqual(len(shell_argv), 9)
        self.assertEqual(agent_argv[:4], common)
        self.assertEqual(agent_argv[4:8], [
            "/workspace/subdir", CONTAINER_ID, "/bin/bash", "-lc",
        ])
        self.assertEqual(shell_argv[:4], common)
        self.assertEqual(shell_argv[4:8], [
            "/workspace", CONTAINER_ID, "/bin/bash", "-lc",
        ])
        bootstrap = ('source "$HOME/.config/yolo-user-env.sh"; '
                     'eval "$(mise env -s bash)"; '
                     'export PATH="$HOME/.yolo-shims:$PATH"')
        self.assertEqual(
            agent_argv[8], bootstrap + "; cd -- '/workspace/subdir' && exec 'pi'"
        )
        self.assertEqual(
            shell_argv[8], bootstrap + "; cd -- '/workspace' && exec /bin/bash -i"
        )
        self.assertNotIn("yolo --", "\n".join(commands.values()))

    def test_agent_bootstrap_finds_pi_with_minimal_container_path(self):
        self.assertNotEqual(
            subprocess.run(
                ["/bin/bash", "-c", "command -v pi"],
                env={"PATH": "/bin:/usr/bin"}, capture_output=True,
            ).returncode,
            0,
        )
        run = self.run_ops(FAKE_EXEC_CONTAINER="1")
        self.assertEqual(run.returncode, 0, run.stderr)
        agent_log = Path(self.tmp.name, "agent.log").read_text()
        self.assertIn(f"PATH={self.container_home}/.yolo-shims:/bin:/usr/bin", agent_log)
        self.assertIn("MISE=1", agent_log)
        self.assertIn(f"PWD={self.container_workdir}", agent_log)
        self.assertIn("ARGS=", agent_log)

    def test_selected_open_passes_identity_through_full_action_path(self):
        env = self.env("/tmp/project/subdir")
        env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice("open")
        run = subprocess.run(["bash", str(MENU)], env=env, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        commands = [line for line in self.herdr_lines() if "podman" in line and " exec " in line]
        self.assertEqual(len(commands), 2)
        self.assertTrue(all(CONTAINER_ID in command for command in commands))

    def test_linked_worktree_prefers_checkout_path(self):
        env = self.env()
        env["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps({
            "workspace_id": "ws-1",
            "worktree": {
                "checkout_path": "/tmp/project/subdir",
                "repo_root": "/tmp/not-the-checkout",
            },
            "workspace_cwd": "/tmp/also-not-the-checkout",
        })
        env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice("open")
        run = subprocess.run(["bash", str(MENU)], env=env, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(any(
            line.startswith("tab\tcreate") and "\t--cwd\t/tmp/project/subdir" in line
            for line in self.herdr_lines()
        ))
        self.assertTrue(any("/workspace/subdir" in line for line in self.herdr_lines()))

    def test_repo_outside_jail_fails_before_creating_tab(self):
        run = self.run_ops(repo="/tmp/another-project")
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(any(line.startswith("tab\tcreate") for line in self.herdr_lines()))

    def test_replacement_or_removal_fails_before_creating_tab(self):
        for env in ({"FAKE_CONTAINER_ID": "b" * 64}, {"FAKE_INSPECT_FAIL": "1"}):
            with self.subTest(env=env):
                self.herdr_log.unlink(missing_ok=True)
                run = self.run_ops(**env)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(any(line.startswith("tab\tcreate") for line in self.herdr_lines()))

    def test_tab_creation_failure_returns_nonzero_without_dispatch(self):
        run = self.run_ops(FAKE_FAIL_AT="tab-create")
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(any(" exec " in line for line in self.herdr_lines()))

    def test_post_create_failures_return_nonzero_and_close_tab(self):
        for point in ("split", "ready-run", "wait", "run-right-pane", "run-left-pane"):
            with self.subTest(point=point):
                self.herdr_log.unlink(missing_ok=True)
                Path(self.tmp.name, "inspect-count").unlink(missing_ok=True)
                run = self.run_ops(FAKE_FAIL_AT=point)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("tab\tclose\tnew-tab", self.herdr_lines())

    def test_replacement_or_removal_after_tab_creation_is_cleaned_up(self):
        for env in ({"FAKE_REPLACE_AFTER_FIRST": "1"}, {"FAKE_REMOVE_AFTER_FIRST": "1"}):
            with self.subTest(env=env):
                self.herdr_log.unlink(missing_ok=True)
                Path(self.tmp.name, "inspect-count").unlink(missing_ok=True)
                run = self.run_ops(**env)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("tab\tclose\tnew-tab", self.herdr_lines())

    def test_valid_close_is_revalidated_then_executed(self):
        env = self.env()
        env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice()
        run = subprocess.run(["bash", str(MENU)], env=env, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.stop_log.read_text().strip(), CONTAINER_ID)

    def test_close_rejects_missing_identity(self):
        run = subprocess.run(
            ["bash", str(OPS), "close", "yolo-project-abc"],
            env=self.env(), text=True, capture_output=True,
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("full immutable container ID required", run.stderr)
        self.assertFalse(self.stop_log.exists())

    def test_podman_discovery_failures_fail_provider_and_action(self):
        for failure in ("FAKE_PS_FAIL", "FAKE_HOST_INSPECT_FAIL", "FAKE_HOST_DIR_MISSING"):
            with self.subTest(failure=failure):
                self.stop_log.unlink(missing_ok=True)
                env = self.env(); env[failure] = "1"
                provider = subprocess.run(
                    ["bash", str(PROVIDER)], env=env, text=True, capture_output=True
                )
                self.assertNotEqual(provider.returncode, 0)
                self.assertIn("could not query Podman", provider.stderr)

                env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice()
                action = subprocess.run(
                    ["bash", str(MENU)], env=env, text=True, capture_output=True
                )
                self.assertNotEqual(action.returncode, 0)
                self.assertIn("could not query live Podman jails", action.stderr)
                self.assertFalse(self.stop_log.exists())

    def test_stale_replacement_invalid_and_context_choices_fail_closed(self):
        cases = [
            (choice(container="yolo-stale-abc"), {}),
            (choice(), {"FAKE_CONTAINER_ID": "b" * 64}),
            (choice("destroy"), {}),
        ]
        for selected, extra in cases:
            with self.subTest(selected=selected, extra=extra):
                self.stop_log.unlink(missing_ok=True)
                env = self.env(); env.update(extra)
                env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = selected
                run = subprocess.run(["bash", str(MENU)], env=env, text=True, capture_output=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(self.stop_log.exists())

        for context in ('{malformed', json.dumps({"workspace_id": "other"})):
            env = self.env()
            env["HERDR_PLUGIN_CONTEXT_JSON"] = context
            env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice()
            self.assertNotEqual(
                subprocess.run(["bash", str(MENU)], env=env, capture_output=True).returncode, 0
            )

    def test_resource_context_is_exact_and_changed_attachment_fails_closed(self):
        context = {
            "workspace_id": "ws-1", "workspace_cwd": "/tmp/project",
            "workspace_resource": {"plugin_id": "hs.jail", "resource_id": CONTAINER_ID,
                "data": {"container_id": CONTAINER_ID, "attachments": ATTACHMENTS, "attachment_fingerprint": FINGERPRINT}},
        }
        env = self.env(); env["HERDR_PLUGIN_CONTEXT_JSON"] = json.dumps(context)
        provider = subprocess.run(["bash", str(PROVIDER)], env=env, text=True, capture_output=True)
        self.assertEqual(provider.returncode, 0, provider.stderr)
        self.assertEqual([x["id"] for x in json.loads(provider.stdout)["choices"]], [f"open:{CONTAINER_ID}", f"close:{CONTAINER_ID}"])
        # The menu's old Close is rejected after fresh attribution loses its
        # only Checkout projection; no container-wide stop is dispatched.
        self.snapshot.write_text(json.dumps({"result": {"snapshot": {"panes": [
            {"workspace_id": "ws-1", "foreground_cwd": "/tmp/unattached"}]}}}))
        env["HERDR_PLUGIN_ACTION_CHOICE_JSON"] = choice()
        action = subprocess.run(["bash", str(MENU)], env=env, text=True, capture_output=True)
        self.assertNotEqual(action.returncode, 0)
        self.assertFalse(self.stop_log.exists())

    def test_jail_ops_rejects_unsupported_agent_and_short_id(self):
        for agent, identity in (("not-an-agent", CONTAINER_ID), ("pi", "a" * 63)):
            run = subprocess.run([
                "bash", str(OPS), "open", "ws-1", "yolo-project-abc",
                "/tmp/project", agent, identity, "/tmp/project",
            ], env=self.env(), text=True, capture_output=True)
            self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
