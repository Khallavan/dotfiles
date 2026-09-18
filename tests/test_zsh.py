import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZSHRC = ROOT / "zsh" / ".zshrc"
ZSH = shutil.which("zsh")


@unittest.skipUnless(ZSH, "zsh is required")
class ZshStartupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="zsh-test-")
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.shared_brew_bin = self.root / "shared-linuxbrew" / "bin"
        self.shared_brew_bin.mkdir(parents=True)
        self.zshrc = self.root / "zshrc"
        self.zshrc.write_text(
            ZSHRC.read_text().replace(
                "/home/linuxbrew/.linuxbrew/bin", str(self.shared_brew_bin)
            )
        )
        self.xdg_data = self.root / "data with spaces"
        self.xdg_config = self.root / "config with spaces"
        self.xdg_cache = self.root / "cache with spaces"
        self.log = self.root / "commands.log"
        self.env = {
            "HOME": str(self.home),
            "PATH": str(self.bin),
            "TERM": "dumb",
            "TMUX": "",
            "XDG_DATA_HOME": str(self.xdg_data),
            "XDG_CONFIG_HOME": str(self.xdg_config),
            "XDG_CACHE_HOME": str(self.xdg_cache),
            "ZDOTDIR": str(self.home),
            "FAKE_LOG": str(self.log),
            "LANG": "C",
            "LC_ALL": "C",
            "LOGNAME": "zsh-test",
            "USER": "zsh-test",
        }
        self.write_fake(
            "git",
            "printf '%s %s\\n' git \"$*\" >> \"$FAKE_LOG\"\nexit 97",
        )
        self.write_fake(
            "tmux",
            "printf '%s %s\\n' tmux \"$*\" >> \"$FAKE_LOG\"\nexit 97",
        )
        self.write_fake("vi", "exit 0")

    def tearDown(self):
        self.tempdir.cleanup()

    def write_fake(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)
        return path

    def write_simple_fake(self, name, output="", error="", status=0):
        body = ["printf '%s %s\\n' \"$0\" \"$*\" >> \"$FAKE_LOG\""]
        if error:
            body.append(f"printf '%s\\n' {shlex.quote(error)} >&2")
        if output:
            body.append(f"printf '%s\\n' {shlex.quote(output)}")
        body.append(f"exit {status}")
        return self.write_fake(name, "\n".join(body))

    def write_fake_zinit(self):
        zinit_home = self.xdg_data / "zinit" / "zinit.git"
        zinit_home.mkdir(parents=True)
        (zinit_home / "zinit.zsh").write_text(
            "zinit() {\n"
            "  if [[ \"$1\" == light && \"$2\" == zsh-users/zsh-completions && -n \"${FAKE_COMPLETION_DIR:-}\" ]]; then\n"
            "    fpath=(\"$FAKE_COMPLETION_DIR\" $fpath)\n"
            "  elif [[ \"$1\" == cdreplay ]]; then\n"
            "    if (( $+functions[compdef] )); then\n"
            "      printf 'zinit cdreplay completion=ready\\n' >> \"$FAKE_LOG\"\n"
            "    else\n"
            "      printf 'zinit cdreplay completion=missing\\n' >> \"$FAKE_LOG\"\n"
            "    fi\n"
            "  else\n"
            "    printf 'zinit %s\\n' \"$*\" >> \"$FAKE_LOG\"\n"
            "  fi\n"
            "}\n"
        )
        return zinit_home

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def run_zsh(self, body="print -r -- READY", *, term=None, tmux=None):
        env = dict(self.env)
        if term is not None:
            env["TERM"] = term
        if tmux is not None:
            env["TMUX"] = tmux
        command = f"source {shlex.quote(str(self.zshrc))}; {body}"
        return subprocess.run(
            [ZSH, "-d", "-i", "-c", command],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
        )

    def test_bare_startup_is_clean_and_does_not_clone_or_start_tmux(self):
        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("READY", result.stdout)
        self.assertEqual("", result.stderr)
        self.assertNotIn("git ", self.calls())
        self.assertNotIn("tmux ", self.calls())

    def test_missing_tools_keep_sensible_editor_and_listing_aliases(self):
        result = self.run_zsh(
            "print -r -- \"LL=${aliases[ll]}\"; "
            "print -r -- \"VIM=${aliases[vim]}\""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("LL=ls -la", result.stdout)
        self.assertIn("VIM=vi", result.stdout)

    def test_paths_use_home_xdg_and_shared_brew_without_duplicates(self):
        home_bin = self.home / ".local" / "bin"
        fnm_bin = self.xdg_data / "fnm"
        pnpm_home = self.xdg_data / "pnpm"
        self.env["PATH"] = ":".join(
            [str(home_bin), str(fnm_bin), str(pnpm_home), str(self.bin)]
        )

        result = self.run_zsh("print -r -- \"PATH=$PATH\"")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        path_line = next(line for line in result.stdout.splitlines() if line.startswith("PATH="))
        shell_path = path_line.removeprefix("PATH=").split(":")
        self.assertEqual(1, shell_path.count(str(home_bin)))
        self.assertEqual(1, shell_path.count(str(fnm_bin)))
        self.assertEqual(1, shell_path.count(str(pnpm_home)))
        self.assertEqual(1, shell_path.count(str(self.shared_brew_bin)))
        self.assertIn(str(self.home / ".opencode" / "bin"), shell_path)
        self.assertNotIn("/home/khallavan", path_line)
        self.assertNotIn("/home/linuxbrew", path_line)

    def test_shared_brew_fallback_is_usable_without_host_tools(self):
        shared_tool = self.shared_brew_bin / "shared-tool"
        shared_tool.write_text("#!/bin/sh\nexit 0\n")
        shared_tool.chmod(0o755)

        result = self.run_zsh(
            "print -r -- \"SHARED_TOOL=$(command -v shared-tool)\"; "
            "print -r -- \"PATH=$PATH\""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn(f"SHARED_TOOL={shared_tool}", result.stdout)
        self.assertNotIn("/home/linuxbrew", result.stdout)

    def test_final_local_bin_precedes_bun_bin(self):
        local_bin = self.home / ".local" / "bin"
        bun_bin = self.home / ".bun" / "bin"
        local_bin.mkdir(parents=True)
        bun_bin.mkdir(parents=True)
        for directory in (local_bin, bun_bin):
            tool = directory / "priority-tool"
            tool.write_text("#!/bin/sh\nexit 0\n")
            tool.chmod(0o755)

        result = self.run_zsh(
            "print -r -- \"TOOL=$(command -v priority-tool)\"; "
            "print -r -- \"PATH=$PATH\""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn(f"TOOL={local_bin / 'priority-tool'}", result.stdout)
        path_line = next(line for line in result.stdout.splitlines() if line.startswith("PATH="))
        shell_path = path_line.removeprefix("PATH=").split(":")
        self.assertLess(shell_path.index(str(local_bin)), shell_path.index(str(bun_bin)))

    def test_present_integrations_are_guarded_and_preserve_aliases(self):
        config = self.home / "dotfiles" / "pure.omp.json"
        config.parent.mkdir()
        config.write_text("{}")
        bun_completion = self.home / ".bun" / "_bun"
        bun_completion.parent.mkdir()
        bun_completion.write_text("typeset -g BUN_COMPLETION_LOADED=1\n")

        self.write_simple_fake("eza")
        self.write_simple_fake("nvim")
        self.write_simple_fake("bun")
        self.write_simple_fake("pnpm")
        self.write_simple_fake("fzf", output=":")
        self.write_simple_fake("zoxide", output=":")
        self.write_simple_fake("fnm", output="export FNM_TEST=1")
        self.write_fake(
            "oh-my-posh",
            "printf '%s %s\\n' oh-my-posh \"$*\" >> \"$FAKE_LOG\"\n"
            "[ \"$3\" = \"$EXPECTED_CONFIG\" ] || exit 11\n"
            "printf ':\\n'",
        )
        self.env["EXPECTED_CONFIG"] = str(config)

        result = self.run_zsh(
            "print -r -- \"LL=${aliases[ll]}\"; "
            "print -r -- \"VIM=${aliases[vim]}\"; "
            "print -r -- \"FNM=${FNM_TEST:-missing}\"; "
            "print -r -- \"BUN=${BUN_COMPLETION_LOADED:-missing}\""
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("eza", result.stdout)
        self.assertIn("nvim", result.stdout)
        self.assertIn("FNM=1", result.stdout)
        self.assertIn("BUN=1", result.stdout)
        calls = self.calls()
        self.assertIn("fzf --zsh", calls)
        self.assertIn("zoxide init --cmd cd zsh", calls)
        self.assertIn("oh-my-posh init zsh --config", calls)
        self.assertIn(str(config), calls)

    def test_old_fzf_zsh_mode_failure_is_silent_and_startup_continues(self):
        self.write_simple_fake("fzf", error="unsupported --zsh", status=2)

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("READY", result.stdout)
        self.assertEqual("", result.stderr)
        self.assertNotIn("unsupported --zsh", result.stderr)
        self.assertIn("fzf --zsh", self.calls())

    def test_oh_my_posh_requires_a_readable_config(self):
        self.write_simple_fake("oh-my-posh", output=":")

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertNotIn("oh-my-posh", self.calls())

    def test_missing_zinit_does_not_create_a_directory_or_clone(self):
        zinit_home = self.xdg_data / "zinit" / "zinit.git"

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(zinit_home.exists())
        self.assertNotIn("git ", self.calls())

    def test_existing_zinit_loads_plugins_but_skips_dnf_snippet_when_dnf_is_missing(self):
        self.write_fake_zinit()

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        calls = self.calls()
        self.assertIn("zinit light zsh-users/zsh-syntax-highlighting", calls)
        self.assertNotIn("OMZP::dnf", calls)

    def test_zinit_replay_requires_initialized_completion(self):
        self.write_fake_zinit()

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("zinit cdreplay completion=ready", self.calls())
        self.assertNotIn("zinit cdreplay completion=missing", self.calls())

    def test_compinit_discovers_zinit_completion_path(self):
        completion_dir = self.xdg_data / "zinit-completions"
        completion_dir.mkdir(parents=True)
        (completion_dir / "_zz_verify").write_text("#compdef zz_verify\n")
        self.env["FAKE_COMPLETION_DIR"] = str(completion_dir)
        self.write_fake_zinit()

        result = self.run_zsh(
            "(( ${+_comps[zz_verify]} )) && "
            "print -r -- ZINIT_COMPLETION_READY || "
            "print -r -- ZINIT_COMPLETION_MISSING"
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("ZINIT_COMPLETION_READY", result.stdout)

    def test_existing_zinit_loads_dnf_snippet_when_dnf_is_available(self):
        self.write_fake_zinit()
        self.write_simple_fake("dnf")

        result = self.run_zsh()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("zinit snippet OMZP::dnf", self.calls())

    def test_compinit_is_usable_without_zinit(self):
        result = self.run_zsh(
            "(( $+functions[compinit] )) && print -r -- COMPINIT_READY"
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertIn("COMPINIT_READY", result.stdout)

    def test_tmux_guard_skips_when_already_attached(self):
        result = self.run_zsh(term="xterm-256color", tmux="already-attached")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)
        self.assertNotIn("tmux ", self.calls())

    def test_startup_has_no_personal_paths_and_keeps_shared_brew_fallback(self):
        source = ZSHRC.read_text()

        self.assertNotIn("/home/khallavan", source)
        self.assertIn("/home/linuxbrew/.linuxbrew/bin", source)


if __name__ == "__main__":
    unittest.main()
