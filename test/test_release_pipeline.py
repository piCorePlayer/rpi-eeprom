import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / ".github/scripts/check-upstream-releases.sh"
PACKAGE = ROOT / ".github/scripts/package-release.sh"

GH = """\
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
state_file = Path(os.environ["MOCK_GH_STATE"])
state = json.loads(state_file.read_text())
if args[0] == "api":
    print(json.dumps([list(state.values())]))
    sys.exit(0)
action, tag = args[1:3]
if action == "create":
    if os.environ.get("FAIL_CREATE") == tag:
        sys.exit("Simulated release creation failure")
    state[tag] = {"tag_name": tag, "draft": True}
elif action == "upload":
    state[tag]["package"] = Path("rpi-eeprom.tcz").read_text()
elif action == "edit" and "--draft=false" in args:
    if os.environ.get("FAIL_PUBLISH") == tag:
        sys.exit("Simulated publication failure")
    state[tag]["draft"] = False
    if "--latest" in args:
        for release in state.values():
            release["latest"] = False
    state[tag]["latest"] = "--latest" in args
state_file.write_text(json.dumps(state))
"""

MKSQUASHFS = """\
#!/bin/sh
cat sqfs-root/usr/local/bin/pcp-rpi-eeprom-update \
    sqfs-root/usr/local/lib/firmware/raspberrypi/bootloader-2711/default/pieeprom-test.bin > "$2"
"""

UNSQUASHFS = """\
#!/bin/sh
echo squashfs-root/usr/local/bin/pcp-rpi-eeprom-update
"""


class ReleasePipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.origin = self.root / "origin.git"
        self.repo = self.root / "pcp"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, script in [("gh", GH), ("mksquashfs", MKSQUASHFS), ("unsquashfs", UNSQUASHFS)]:
            path = self.bin / name
            path.write_text(script)
            path.chmod(0o755)
        self.state = self.root / "releases.json"
        self.state.write_text(json.dumps({
            "v1.0-1-pCP": {"tag_name": "v1.0-1-pCP", "draft": False}
        }))
        self.env = os.environ.copy()
        self.env.update({
            "PATH": f"{self.bin}:{self.env['PATH']}",
            "MOCK_GH_STATE": str(self.state),
            "UPSTREAM_URL": str(self.upstream),
            "RELEASE_REPOSITORY": "example/repo",
        })

        self.run_cmd("git", "init", "-q", "--initial-branch=master", str(self.upstream))
        self.configure(self.upstream)
        for name in ["rpi-eeprom-config", "rpi-eeprom-digest", "rpi-eeprom-update",
                     "pcp-rpi-eeprom-config", "rpi-eeprom-update-default-pcp", "LICENSE",
                     "tools/rpi-test"]:
            self.write(self.upstream / name, "fixture\n")
        self.write(self.upstream / "pcp-rpi-eeprom-update", 'VERSION="1.0-1-pCP"\n')
        for chip in ("2711", "2712"):
            self.write(self.upstream / f"firmware-{chip}/default/pieeprom-test.bin", "baseline\n")
            self.write(self.upstream / f"firmware-{chip}/old/archived.bin", "old\n")
        self.git(self.upstream, "add", ".")
        self.git(self.upstream, "commit", "-qm", "baseline")
        self.git(self.upstream, "tag", "apt/0.9-1")
        self.git(self.upstream, "tag", "apt/1.0-1")
        self.git(self.upstream, "tag", "unrelated/9.9-1")

        self.run_cmd("git", "init", "-q", "--bare", str(self.origin))
        self.run_cmd("git", "clone", "-q", str(self.upstream), str(self.repo))
        self.configure(self.repo)
        self.git(self.repo, "switch", "-qc", "pCP")
        self.git(self.repo, "remote", "set-url", "origin", str(self.origin))
        self.git(self.repo, "tag", "v1.0-1-pCP")
        self.git(self.repo, "push", "-q", "-u", "origin", "pCP", "v1.0-1-pCP")

        for version in ("1.1-1", "1.2-1"):
            for chip in ("2711", "2712"):
                self.write(self.upstream / f"firmware-{chip}/default/pieeprom-test.bin", version + "\n")
            self.git(self.upstream, "add", ".")
            self.git(self.upstream, "commit", "-qm", version)
            self.git(self.upstream, "tag", f"apt/{version}")
        self.write(self.upstream / "firmware-2711/default/pieeprom-test.bin", "unreleased\n")
        self.git(self.upstream, "add", ".")
        self.git(self.upstream, "commit", "-qm", "unreleased master")
        self.git(self.upstream, "tag", "other/1.3-1")

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def run_cmd(self, *args, cwd=None, env=None, check=True):
        trace = (os.environ.get("PCP_RELEASE_TEST_VERBOSE") == "1"
                 and len(args) > 1 and args[0] == "bash"
                 and args[1] in (str(CHECK), str(PACKAGE)))
        if trace:
            print(f"\n[{self._testMethodName}] Running {Path(args[1]).name}"
                  f" {' '.join(args[2:])} (isolated fixtures)", flush=True)
            self.print_release_state("Before")
        result = subprocess.run(args, cwd=cwd, env=env, check=False, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if trace:
            print(f"Script exit status: {result.returncode}", flush=True)
            for label, output in (("stdout", result.stdout), ("stderr", result.stderr)):
                if output:
                    print(f"{label}:\n{output.rstrip()}", flush=True)
            self.print_release_state("After")
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, args, output=result.stdout, stderr=result.stderr)
        return result

    def print_release_state(self, label):
        print(f"{label}:", flush=True)
        for title, repo, pattern in (("Upstream fixture tags", self.upstream, "*"),
                                     ("Local pCP release tags", self.repo, "v*-pCP")):
            tags = self.git(repo, "tag", "--list", pattern, "--sort=version:refname")
            print(f"  {title}:", flush=True)
            for tag in tags.splitlines():
                commit = self.git(repo, "rev-parse", "--short", f"{tag}^{{commit}}")
                print(f"    {tag} -> {commit}", flush=True)
        print("  Simulated GitHub releases:", flush=True)
        for tag, release in json.loads(self.state.read_text()).items():
            status = "draft" if release["draft"] else "published"
            print(f"    {tag}: {status}, latest={release.get('latest', False)}",
                  flush=True)
            if "package" in release:
                print(f"      Package fixture content: {release['package']!r}",
                      flush=True)

    def git(self, cwd, *args):
        return self.run_cmd("git", *args, cwd=cwd).stdout.strip()

    def configure(self, cwd):
        self.git(cwd, "config", "user.name", "Test")
        self.git(cwd, "config", "user.email", "test@example.invalid")

    def check_releases(self, env=None, check=True):
        return self.run_cmd("bash", str(CHECK), cwd=self.repo, env=env or self.env, check=check)

    def test_multiple_tags_are_released_in_order_from_their_own_commits(self):
        self.check_releases()
        state = json.loads(self.state.read_text())
        self.assertEqual(list(state), ["v1.0-1-pCP", "v1.1-1-pCP", "v1.2-1-pCP"])
        for version in ("1.1-1", "1.2-1"):
            tag = f"v{version}-pCP"
            self.assertFalse(state[tag]["draft"])
            self.assertEqual(state[tag]["package"], f'VERSION="{version}-pCP"\n{version}\n')
            self.assertEqual(self.git(self.repo, "show", f"{tag}:firmware-2711/default/pieeprom-test.bin"), version)
            self.run_cmd("git", "merge-base", "--is-ancestor", f"upstream-apt/{version}", tag, cwd=self.repo)
        self.assertNotIn("v0.9-1-pCP", self.git(self.repo, "tag", "--list"))
        self.assertNotIn("unreleased", state["v1.2-1-pCP"]["package"])
        self.check_releases()
        self.assertEqual(json.loads(self.state.read_text()), state)

    def test_retry_resumes_draft_before_processing_next_version(self):
        env = self.env | {"FAIL_PUBLISH": "v1.1-1-pCP"}
        self.assertNotEqual(self.check_releases(env, check=False).returncode, 0)
        state = json.loads(self.state.read_text())
        self.assertTrue(state["v1.1-1-pCP"]["draft"])
        self.assertNotIn("v1.2-1-pCP", state)
        self.check_releases()
        state = json.loads(self.state.read_text())
        self.assertFalse(state["v1.1-1-pCP"]["draft"])
        self.assertFalse(state["v1.2-1-pCP"]["draft"])

    def test_manual_historical_draft_does_not_become_latest(self):
        self.check_releases()
        state = json.loads(self.state.read_text())
        state["v1.1-1-pCP"]["draft"] = True
        self.state.write_text(json.dumps(state))
        self.run_cmd("bash", str(PACKAGE), "v1.1-1-pCP", cwd=self.repo, env=self.env)
        state = json.loads(self.state.read_text())
        self.assertFalse(state["v1.1-1-pCP"]["latest"])

    def test_retry_after_tag_push_before_release_creation(self):
        env = self.env | {"FAIL_CREATE": "v1.1-1-pCP"}
        self.assertNotEqual(self.check_releases(env, check=False).returncode, 0)
        self.assertIn("v1.1-1-pCP", self.git(self.repo, "tag", "--list"))
        self.assertNotIn("v1.1-1-pCP", json.loads(self.state.read_text()))
        self.check_releases()
        state = json.loads(self.state.read_text())
        self.assertFalse(state["v1.1-1-pCP"]["draft"])
        self.assertFalse(state["v1.2-1-pCP"]["draft"])

    def test_releases_sharing_an_upstream_commit(self):
        self.git(self.upstream, "tag", "apt/1.3-1", "apt/1.2-1")
        self.check_releases()
        state = json.loads(self.state.read_text())
        self.assertEqual(state["v1.3-1-pCP"]["package"],
                         'VERSION="1.3-1-pCP"\n1.2-1\n')

    def test_divergent_upstream_release_stops_before_tagging(self):
        self.git(self.upstream, "tag", "apt/1.3-1", "apt/1.0-1")
        result = self.check_releases(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not descend", result.stderr)
        self.assertNotIn("v1.3-1-pCP", self.git(self.repo, "tag", "--list"))


if __name__ == "__main__":
    unittest.main()
