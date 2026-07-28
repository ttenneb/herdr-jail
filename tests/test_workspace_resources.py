#!/usr/bin/env python3
import json, os, re, subprocess, tempfile, time, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / 'bin/resource-graph.py'; CODEC = ROOT / 'bin/jail-choice.py'; REFRESH = ROOT / 'bin/jails-refresher.sh'; LOCK = ROOT / 'bin/refresher-lock.py'; A = 'a' * 64; B = 'b' * 64
def write(path, text): Path(path).write_text(text)
def graph(jails, workspaces, panes, workspace=None):
    with tempfile.TemporaryDirectory() as temp:
        d = Path(temp); write(d/'j', jails)
        work_doc = {'result': {'workspaces': [{'workspace_id': item} for item in workspaces]}}
        write(d/'w', json.dumps(work_doc)); write(d/'s', json.dumps({'result': {'snapshot': {'panes': panes}}}))
        cmd = ['python3',str(GRAPH),'--jails',str(d/'j'),'--workspaces',str(d/'w'),'--snapshot',str(d/'s')]
        if workspace: cmd += ['--workspace',workspace]
        return subprocess.run(cmd,text=True,capture_output=True)
class ManifestTests(unittest.TestCase):
    def test_resource_protocol_requires_planned_next_release(self):
        manifest=(ROOT/'herdr-plugin.toml').read_text()
        match=re.search(r'^min_herdr_version\s*=\s*"([^"]+)"\s*$', manifest, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), '0.7.6')
class GraphTests(unittest.TestCase):
    def test_zero_shared_and_per_checkout_kind(self):
        self.assertEqual(json.loads(graph('', ['one'], []).stdout)['workspaces'][0]['resources'], [])
        j = f'yolo-shared\t/tmp/root\t{A}\n'; panes = [{'workspace_id':'a','foreground_cwd':'/tmp/root/a','terminal_title_stripped':'pi','revision':2},{'workspace_id':'b','foreground_cwd':'/tmp/root/b','terminal_title_stripped':'Codex','revision':3}]
        self.assertEqual(graph(j,['a','b'],panes,'a').stdout.split('\t')[2], 'pi'); self.assertEqual(graph(j,['a','b'],panes,'b').stdout.split('\t')[2], 'codex')
        resource = json.loads(graph(j,['a','b'],panes).stdout)['workspaces'][0]['resources'][0]
        self.assertEqual(resource['data']['attachments'],['a','b']); self.assertEqual(resource['detail'], '/tmp/root')
    def test_rejects_ambiguity_duplicate_json_workspace_and_controls(self):
        self.assertNotEqual(graph(f'yolo-a\t/tmp/x\t{A}\nyolo-b\t/tmp/x/\t{B}\n',['w'],[]).returncode,0)
        self.assertNotEqual(graph(f'yolo-a\t/tmp/\u202ex\t{A}\n',['w'],[]).returncode,0)
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); write(d/'j',f'yolo-a\t/tmp/x\t{A}\n'); write(d/'s','{"result":{"snapshot":{"panes":[]}}}')
            write(d/'w','{"result":{"workspaces":[{"workspace_id":"w"},{"workspace_id":"w"}]}}')
            cmd=['python3',str(GRAPH),'--jails',str(d/'j'),'--workspaces',str(d/'w'),'--snapshot',str(d/'s')]
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            write(d/'w','{"result":{"workspaces":[],"workspaces":[]}}'); self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
    def test_overflow_is_bounded_and_visible(self):
        j=''.join(f'yolo-{i:02d}\t/tmp/{i:02d}\t{i+1:064x}\n' for i in range(33)); panes=[{'workspace_id':'w','foreground_cwd':f'/tmp/{i:02d}'} for i in range(33)]
        resources=json.loads(graph(j,['w'],panes).stdout)['workspaces'][0]['resources']; self.assertEqual(len(resources),32); self.assertIn('+1 more jails omitted',resources[-1]['detail'])
class ChoiceTests(unittest.TestCase):
    def test_shared_choice_fingerprint(self):
        line=graph(f'yolo-x\t/tmp/x\t{A}\n',['a','b'],[{'workspace_id':'a','foreground_cwd':'/tmp/x/a'},{'workspace_id':'b','foreground_cwd':'/tmp/x/b'}],'a').stdout
        out=subprocess.run(['python3',str(CODEC),'emit'],input=line,text=True,capture_output=True); choice=json.loads(out.stdout)['choices'][1]
        self.assertIn('shared 2; affects all',choice['label']); self.assertEqual(subprocess.run(['python3',str(CODEC),'parse'],input=json.dumps(choice),text=True,capture_output=True).returncode,0)
class OverlayTests(unittest.TestCase):
    def test_failure_retention_and_shared_close_warning_are_present(self):
        source=(ROOT/'bin/jail-menu-ui.sh').read_text()
        self.assertIn('Showing the previous verified list',source)
        self.assertIn('Type yes to continue',source)
        self.assertIn('"$fingerprint"',source)
class LockHelperTests(unittest.TestCase):
    def test_exec_inherits_lock_and_rejects_duplicate_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp); lock=d/'lock'; command=['python3',str(LOCK),'--lock',str(lock),'--','/bin/sh','-c','test "$HERDR_JAIL_REFRESH_LOCKED" = 1; sleep 1']
            first=subprocess.Popen(command); time.sleep(.1)
            second=subprocess.run(command,text=True,capture_output=True,timeout=2)
            self.assertEqual(second.returncode,0); self.assertIn('another refresher',second.stderr); first.terminate(); first.wait(2)
            target=d/'target'; target.write_text('x'); link=d/'link'; link.symlink_to(target)
            bad=subprocess.run(['python3',str(LOCK),'--lock',str(link),'--','true'],text=True,capture_output=True)
            self.assertNotEqual(bad.returncode,0); self.assertIn('unsafe refresher lock',bad.stderr)
    def test_foreign_or_nonregular_lock_is_unsafe(self):
        with tempfile.TemporaryDirectory() as temp:
            lock=Path(temp)/'directory-lock'; lock.mkdir()
            bad=subprocess.run(['python3',str(LOCK),'--lock',str(lock),'--','true'],text=True,capture_output=True)
            self.assertNotEqual(bad.returncode,0); self.assertIn('unsafe refresher lock',bad.stderr)
            # A non-root test process cannot create a foreign-owned file; the
            # helper's fstat UID check is still explicitly exercised under root.
            if os.geteuid() == 0:
                foreign=Path(temp)/'foreign'; foreign.write_text('x'); os.chown(foreign,1,-1)
                bad=subprocess.run(['python3',str(LOCK),'--lock',str(foreign),'--','true'],text=True,capture_output=True)
                self.assertNotEqual(bad.returncode,0); self.assertIn('unsafe refresher lock',bad.stderr)
class RefresherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.d=Path(self.temp.name); self.bin=self.d/'bin'; self.bin.mkdir(); (self.d/'tmp').mkdir(); self.log=self.d/'log'
        write(self.bin/'podman',f'''#!/bin/bash
case "$1" in ps) echo yolo-x;; inspect) if [[ "$*" == *'{{.Id}}'* ]]; then echo {A}; else echo YOLO_HOST_DIR=/tmp/x; fi;; esac
'''); (self.bin/'podman').chmod(0o755)
        write(self.bin/'herdr','''#!/bin/bash
printf '%s\\t%s\\n' "$1" "$*" >> "$FAKE_LOG"
case "$1 $2" in 'workspace list') echo '{"result":{"workspaces":[{"workspace_id":"w"}]}}';; 'api snapshot') echo '{"result":{"snapshot":{"panes":[{"workspace_id":"w","foreground_cwd":"/tmp/x"}]}}}';; esac
'''); (self.bin/'herdr').chmod(0o755)
    def env(self,socket): return dict(os.environ,PATH=f'{self.bin}:'+os.environ['PATH'],HERDR_BIN_PATH=str(self.bin/'herdr'),PODMAN_BIN_PATH=str(self.bin/'podman'),FAKE_LOG=str(self.log),TMPDIR=str(self.d/'tmp'),XDG_RUNTIME_DIR='',HERDR_SOCKET_PATH=socket,HERDR_JAIL_REFRESH_INTERVAL='1')
    def test_report_omits_seq_and_cleans_legacy(self):
        p=subprocess.Popen(['bash',str(REFRESH)],env=self.env('one'))
        try:
            deadline=time.monotonic()+2
            text=''
            while time.monotonic() < deadline:
                text=self.log.read_text() if self.log.exists() else ''
                if '--clear-token jail5' in text: break
                time.sleep(.02)
            self.assertIn('report-resources w --plugin hs.jail --file',text)
            self.assertNotIn(' --seq ',text)
            self.assertIn('--clear-token jail5',text)
        finally:
            p.terminate(); p.wait(2)
    def test_advisory_lock_handles_stale_file_and_racing_starters(self):
        key=str(self.d/'sock'); digest=subprocess.check_output(['cksum'],input=key,text=True).split()[0]; root=self.d/'tmp'/f'herdr-jail-{os.getuid()}'; root.mkdir(); write(root/f'refresher-{digest}.lock','old')
        first=subprocess.Popen(['bash',str(REFRESH)],env=self.env(key)); time.sleep(.15); second=subprocess.run(['bash',str(REFRESH)],env=self.env(key),text=True,capture_output=True,timeout=2); self.assertIsNone(first.poll()); self.assertIn('another refresher',second.stderr); first.terminate(); first.wait(2)
    def test_sessions_are_scoped(self):
        a=subprocess.Popen(['bash',str(REFRESH)],env=self.env('a')); b=subprocess.Popen(['bash',str(REFRESH)],env=self.env('b')); time.sleep(.15); self.assertIsNone(a.poll()); self.assertIsNone(b.poll()); a.terminate(); b.terminate(); a.wait(2); b.wait(2)
if __name__=='__main__': unittest.main()
