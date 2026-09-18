import os
import pty
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT / "install.sh"
CORE = ("stow", "git", "zsh", "tmux")


class InstallerHarness(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        shutil.copy2(INSTALLER, self.checkout / "install.sh")
        for directory, filename in (("zsh", ".zshrc"), ("tmux", ".tmux.conf")):
            (self.checkout / directory).mkdir()
            (self.checkout / directory / filename).touch()
        (self.checkout / "Brewfile").touch()
        self.fake_bin = self.root / "bin"
        self.fake_bin.mkdir()
        self.log = self.root / "commands.log"
        self.release = self.root / "os-release"
        self.release.write_text("ID=debian\n")
        # Deliberately allowlist: inherited BASH_ENV, ENV, functions, and PATH are excluded.
        self.env = {
            "HOME": str(self.home),
            "PATH": str(self.fake_bin),
            "FAKE_LOG": str(self.log),
            "FAKE_BIN": str(self.fake_bin),
            "FIXTURE": str(self.release),
            "TERM": "xterm",
            "LC_ALL": "C",
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def fake(self, name, body="exit 0"):
        path = self.fake_bin / name
        path.write_text(
            "#!/bin/sh\nprintf '%s %s\\n' \"${0##*/}\" \"$*\" >> \"$FAKE_LOG\"\n"
            + body + "\n"
        )
        path.chmod(0o755)

    def fake_core(self):
        for name in CORE:
            self.fake(name)

    def fake_dependency_manager(self, name, exit_code=0):
        body = (
            "for dependency in stow git zsh tmux; do\n"
            "  printf '#!/bin/sh\\nexit 0\\n' > \"$FAKE_BIN/$dependency\"\n"
            "  /bin/chmod +x \"$FAKE_BIN/$dependency\"\n"
            "done\n"
            f"exit {exit_code}"
        )
        self.fake(name, body)

    def fake_nonroot_sudo(self):
        self.fake("id", "printf '1000\\n'")
        self.fake("sudo", "exec \"$@\"")

    def reset_manager_case(self):
        for name in (*CORE, "apt-get", "dnf", "pacman", "sudo", "id", "ln"):
            (self.fake_bin / name).unlink(missing_ok=True)
        canonical = self.home / "dotfiles"
        if canonical.is_symlink():
            canonical.unlink()

    def fixture_main_command(self):
        return (
            ". ./install.sh; "
            "resolve_package_manager() { detect_package_manager \"$FIXTURE\"; }; "
            "main"
        )

    def run_installer(self, *args, input=None, timeout=3):
        return subprocess.run(
            ["/bin/bash", "install.sh", *args], cwd=self.checkout, env=self.env,
            input=input, text=True, capture_output=True, timeout=timeout,
        )

    def run_pty(self, answers=b"", timeout=3, fixture=True, process_sigint=False,
                process_signal=None, command=None):
        command = command or (self.fixture_main_command() if fixture else "exec /bin/bash install.sh")
        master, slave = pty.openpty()
        process = subprocess.Popen(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            stdin=slave, stdout=slave, stderr=slave, close_fds=True,
        )
        os.close(slave)
        try:
            if answers:
                os.write(master, answers)
            if process_sigint:
                time.sleep(0.05)
                os.kill(process.pid, signal.SIGINT)
            if process_signal is not None:
                time.sleep(0.05)
                os.kill(process.pid, process_signal)
            output = bytearray()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                readable, _, _ = select.select([master], [], [], 0.05)
                if readable:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        break
                if process.poll() is not None:
                    break
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
            return process.returncode, output.decode(errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    def logged(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_help_and_non_tty_have_no_external_effects(self):
        result = self.run_installer("--help")
        self.assertEqual(0, result.returncode)
        self.assertIn("Usage:", result.stdout)
        result = self.run_installer()
        self.assertEqual(2, result.returncode)
        self.assertIn("interactive terminal", result.stderr)
        self.assertEqual("", self.logged())

    def test_checkout_validation_and_foreign_paths_are_rejected(self):
        (self.checkout / "tmux" / ".tmux.conf").unlink()
        result = self.run_installer()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Invalid dotfiles checkout", result.stderr)
        (self.checkout / "tmux" / ".tmux.conf").touch()
        foreign = self.home / "foreign"
        foreign.mkdir()
        canonical = self.home / "dotfiles"
        canonical.symlink_to(foreign)
        result = self.run_installer()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match", result.stderr)
        canonical.unlink()
        canonical.symlink_to(self.home / "missing")
        result = self.run_installer()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not a valid checkout path", result.stderr)

    def test_parser_handles_quoted_values_precedence_and_fallback(self):
        cases = {
            "ID='ubuntu'\nID_LIKE='arch'\n": "apt-get",
            "ID=unknown\nID_LIKE='debian ubuntu'\n": "apt-get",
            "ID=cachyos\nID_LIKE=debian\n": "pacman",
        }
        for content, expected in cases.items():
            with self.subTest(content=content):
                self.release.write_text(content)
                result = subprocess.run(
                    ["/bin/bash", "-c", ". ./install.sh; detect_package_manager \"$1\"", "bash", str(self.release)],
                    cwd=self.checkout, env=self.env, text=True, capture_output=True,
                )
                self.assertEqual(expected, result.stdout.strip())
        self.release.write_text("ID=unknown\nID_LIKE='arch debian'\n")
        result = subprocess.run(
            ["/bin/bash", "-c", ". ./install.sh; detect_package_manager \"$1\"", "bash", str(self.release)],
            cwd=self.checkout, env=self.env, text=True, capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)

    def test_each_native_manager_uses_one_grouped_prompt(self):
        cases = (("ID=ubuntu\n", "apt-get", "apt-get install -y"),
                 ("ID=fedora\n", "dnf", "dnf install -y"),
                 ("ID=cachyos\n", "pacman", "pacman -S --needed"))
        for release, manager, invocation in cases:
            with self.subTest(manager=manager):
                self.reset_manager_case()
                self.release.write_text(release)
                self.fake_dependency_manager(manager)
                self.fake_nonroot_sudo()
                self.fake("ln", "exec /bin/ln \"$@\"")
                code, output = self.run_pty(b"y\ny\nn\nn\n")
                self.assertEqual(0, code, output)
                self.assertEqual(1, output.count("Install missing dependencies using"))
                self.assertIn(f"sudo {invocation} stow git zsh tmux", self.logged())
                self.assertNotIn("-Sy", self.logged())

    def test_root_does_not_require_sudo(self):
        self.release.write_text("ID=ubuntu\n")
        self.fake_dependency_manager("apt-get")
        self.fake("id", "printf '0\\n'")
        self.fake("ln", "exec /bin/ln \"$@\"")
        code, output = self.run_pty(b"y\ny\nn\nn\n")
        self.assertEqual(0, code, output)
        self.assertIn("apt-get install -y stow git zsh tmux", self.logged())
        self.assertNotIn("sudo", self.logged())

    def test_nonroot_without_sudo_and_manager_failure_do_not_link(self):
        self.release.write_text("ID=fedora\n")
        self.fake_dependency_manager("dnf")
        self.fake("id", "printf '1000\\n'")
        code, output = self.run_pty(b"y\n", timeout=5)
        self.assertNotEqual(0, code)
        self.assertIn("sudo is unavailable", output)
        self.assertFalse((self.home / "dotfiles").exists())

        self.fake("sudo", "exec \"$@\"")
        self.fake_dependency_manager("dnf", exit_code=9)
        code, output = self.run_pty(b"y\n")
        self.assertNotEqual(0, code)
        self.assertFalse((self.home / "dotfiles").exists())

    def test_canonical_symlink_failure_stops_dependent_steps_and_summary_is_truthful(self):
        self.fake_core()
        self.fake("ln", "exit 17")
        code, output = self.run_pty(b"y\nn\nn\n")
        self.assertNotEqual(0, code)
        self.assertIn("failed: canonical checkout", output)
        self.assertNotIn("applied: canonical checkout", output)
        self.assertNotIn("stow ", self.logged())
        self.assertFalse((self.home / "dotfiles").exists())

    def test_canonical_checkout_is_created_once_and_matching_paths_are_reused(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        code, output = self.run_pty(b"y\nn\nn\n")
        self.assertEqual(0, code, output)
        canonical = self.home / "dotfiles"
        self.assertTrue(canonical.is_symlink())
        self.assertEqual(self.checkout.resolve(), canonical.resolve())
        self.log.unlink()
        code, output = self.run_pty(b"n\nn\n")
        self.assertEqual(0, code, output)
        self.assertNotIn("Create", output)
        self.assertIn("stow -n -v", self.logged())
        self.assertNotIn("stow -d", self.logged().replace("stow -n -v", ""))

        canonical.unlink()
        shutil.move(self.checkout, canonical)
        self.checkout = canonical
        self.log.unlink(missing_ok=True)
        code, output = self.run_pty(b"n\nn\n")
        self.assertEqual(0, code, output)
        self.assertNotIn("Create", output)
        self.assertIn("stow -n -v", self.logged())
        self.assertNotIn("stow -d", self.logged().replace("stow -n -v", ""))

    def test_missing_selected_manager_rejects_before_consent_or_commands(self):
        self.release.write_text("ID=fedora\n")
        code, output = self.run_pty()
        self.assertNotEqual(0, code)
        self.assertIn("dnf is unavailable", output)
        self.assertNotIn("Install missing dependencies", output)
        self.assertEqual("", self.logged())
        self.assertFalse((self.home / "dotfiles").exists())

    def test_zero_exit_manager_without_core_commands_fails_without_linking(self):
        self.release.write_text("ID=fedora\n")
        self.fake("dnf")
        self.fake_nonroot_sudo()
        code, output = self.run_pty(b"y\n")
        self.assertNotEqual(0, code)
        self.assertIn("still missing", output)
        self.assertFalse((self.home / "dotfiles").exists())

    def test_declined_grouped_dependencies_have_no_external_effects(self):
        self.release.write_text("ID=ubuntu\n")
        self.fake("apt-get")
        code, output = self.run_pty(b"n\n")
        self.assertNotEqual(0, code)
        self.assertIn("cancelled", output.lower())
        self.assertEqual("", self.logged())
        self.assertFalse((self.home / "dotfiles").exists())

    def test_foreign_canonical_directory_is_preserved(self):
        canonical = self.home / "dotfiles"
        canonical.mkdir()
        marker = canonical / "keep"
        marker.write_text("unchanged")
        result = self.run_installer()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("does not match", result.stderr)
        self.assertEqual("unchanged", marker.read_text())
        self.assertEqual("", self.logged())

    def test_eof_and_sigint_cancel_without_external_effects(self):
        self.release.write_text("ID=ubuntu\n")
        self.fake("apt-get")
        code, output = self.run_pty(b"\x04")
        self.assertNotEqual(0, code)
        self.assertIn("cancelled", output.lower())
        self.assertEqual("", self.logged())
        code, output = self.run_pty(process_sigint=True)
        self.assertNotEqual(0, code)
        self.assertIn("cancelled", output.lower())
        self.assertEqual("", self.logged())

    def test_stow_group_is_previewed_before_one_confirmed_mutation(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        self.fake("stow", "case \" $* \" in *\" -n \"*) exit 0;; esac")
        code, output = self.run_pty(b"y\ny\nn\nn\n")
        self.assertEqual(0, code, output)
        calls = self.logged()
        stow_calls = [line for line in calls.splitlines() if line.startswith("stow ")]
        self.assertEqual([
            f"stow -n -v -d {self.checkout} -t {self.home} zsh tmux",
            f"stow -d {self.checkout} -t {self.home} zsh tmux",
        ], stow_calls)

    def test_stow_conflict_prevents_the_entire_group_mutation(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        self.fake("stow", "case \" $* \" in *\" -n \"*) exit 2;; esac")
        code, output = self.run_pty(b"y\nn\nn\n")
        self.assertNotEqual(0, code)
        self.assertIn("Stow preview found conflicts", output)
        stow_calls = [line for line in self.logged().splitlines() if line.startswith("stow ")]
        self.assertEqual([f"stow -n -v -d {self.checkout} -t {self.home} zsh tmux"], stow_calls)

    def test_optional_prompt_eof_stops_dependent_steps(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        code, output = self.run_pty(b"y\nn\n\x04")
        self.assertNotEqual(0, code)
        self.assertIn("input ended", output.lower())
        self.assertNotIn("git clone", self.logged())

    def test_term_signal_cancel_without_external_effects(self):
        self.release.write_text("ID=ubuntu\n")
        self.fake("apt-get")
        code, output = self.run_pty(process_signal=signal.SIGTERM)
        self.assertNotEqual(0, code)
        self.assertIn("cancelled", output.lower())
        self.assertEqual("", self.logged())

    def test_existing_tpm_under_symlinked_parent_is_rejected_before_validation(self):
        foreign = self.root / "foreign-tmux"
        target = foreign / "plugins" / "tpm"
        target.mkdir(parents=True)
        marker = target / "foreign"
        marker.write_text("keep")
        (self.home / ".tmux").symlink_to(foreign)
        self.fake("git")
        command = ". ./install.sh; restore_tpm || exit $?"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="", text=True, capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("TPM parent contains a symlink", result.stderr)
        self.assertNotIn("Existing TPM target is invalid", result.stderr)
        self.assertEqual("keep", marker.read_text())

    def test_tpm_mkdir_failure_stops_before_clone(self):
        self.fake("mkdir", "exit 8")
        self.fake("git")
        command = ". ./install.sh; restore_tpm || exit $?"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="y\ny\n", text=True, capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("TPM directory", result.stderr)
        self.assertNotIn("git clone", self.logged())
        self.assertFalse((self.home / ".tmux").exists())

    def test_tpm_required_directory_is_created_only_after_second_consent(self):
        self.fake("git", "if [ \"$1\" = clone ]; then exit 9; fi")
        command = ". ./install.sh; restore_tpm"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="y\nn\n", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Create required TPM directory", result.stdout)
        self.assertFalse((self.home / ".tmux").exists())
        self.assertNotIn("git clone", self.logged())

    def test_successful_tpm_clone_requires_consent_and_uses_official_origin(self):
        parent = self.home / ".tmux" / "plugins"
        parent.mkdir(parents=True)
        self.fake("git", "if [ \"$1\" = clone ]; then /bin/mkdir -p \"$3/bin\"; : > \"$3/tpm\"; : > \"$3/bin/install_plugins\"; fi")
        command = ". ./install.sh; restore_tpm"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="y\n", text=True, capture_output=True,
        )
        target = parent / "tpm"
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((target / "tpm").is_file())
        self.assertTrue((target / "bin" / "install_plugins").is_file())
        self.assertIn(f"git clone https://github.com/tmux-plugins/tpm {target}", self.logged())

    def test_valid_existing_tpm_is_idempotent_without_clone(self):
        target = self.home / ".tmux" / "plugins" / "tpm"
        (target / "bin").mkdir(parents=True)
        (target / "tpm").touch()
        (target / "bin" / "install_plugins").touch()
        self.fake("git", "case \"$*\" in *\"rev-parse --is-inside-work-tree\"*) printf 'true\\n';; *\"remote get-url origin\"*) printf 'https://github.com/tmux-plugins/tpm\\n';; esac")
        command = ". ./install.sh; restore_tpm"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("git clone", self.logged())

    def test_dangling_tpm_target_is_preserved_without_clone(self):
        plugins = self.home / ".tmux" / "plugins"
        plugins.mkdir(parents=True)
        target = plugins / "tpm"
        target.symlink_to(self.root / "missing-tpm")
        self.fake("git")
        command = ". ./install.sh; restore_tpm || exit $?"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="", text=True, capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("Existing TPM target is invalid", result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertNotIn("git clone", self.logged())

    def test_tpm_clone_failure_is_reported_without_applied_claim(self):
        parent = self.home / ".tmux" / "plugins"
        parent.mkdir(parents=True)
        self.fake("git", "exit 9")
        command = ". ./install.sh; status=0; restore_tpm || status=$?; print_summary; exit $status"
        result = subprocess.run(
            ["/bin/bash", "-c", command], cwd=self.checkout, env=self.env,
            input="y\n", text=True, capture_output=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("failed: TPM clone", result.stdout)
        self.assertNotIn("applied: TPM", result.stdout)
        self.assertFalse((parent / "tpm").exists())

    def test_invalid_existing_tpm_is_preserved_without_clone(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        target = self.home / ".tmux" / "plugins" / "tpm"
        target.mkdir(parents=True)
        marker = target / "foreign"
        marker.write_text("keep")
        code, output = self.run_pty(b"y\nn\n")
        self.assertNotEqual(0, code)
        self.assertIn("Existing TPM target is invalid", output)
        self.assertEqual("keep", marker.read_text())
        self.assertNotIn("git clone", self.logged())

    def test_optional_tpm_cancel_and_eof_are_nonzero_without_mutation(self):
        self.fake_core()
        for answer, expected in (("cancel\n", ""), ("", "input ended")):
            with self.subTest(answer=answer):
                result = subprocess.run(
                    ["/bin/bash", "-c", ". ./install.sh; restore_tpm"], cwd=self.checkout,
                    env=self.env, input=answer, text=True, capture_output=True,
                )
                self.assertNotEqual(0, result.returncode)
                self.assertIn(expected, result.stderr)
                self.assertFalse((self.home / ".tmux").exists())
                self.assertNotIn("git clone", self.logged())

    def test_brew_failure_is_summarized_without_skipping_later_optional_work(self):
        self.fake_core()
        self.fake("ln", "exec /bin/ln \"$@\"")
        self.fake("brew", "exit 7")
        self.fake("id", "case \"$1\" in -un) printf 'fixture-user\\n';; *) printf '1000\\n';; esac")
        self.fake("getent", "printf 'fixture-user:x:1000:1000::/home/fixture:/bin/bash\\n'")
        self.fake("chsh")
        shells = self.root / "shells"
        shells.write_text(f"{self.fake_bin}/zsh\n")
        self.env["FIXTURE_SHELLS"] = str(shells)
        command = (
            ". ./install.sh; resolve_package_manager() { detect_package_manager \"$FIXTURE\"; }; "
            "shells_file() { printf '%s\\n' \"$FIXTURE_SHELLS\"; }; main"
        )
        code, output = self.run_pty(b"y\nn\nn\ny\ny\n", command=command)
        self.assertNotEqual(0, code)
        self.assertIn("Homebrew bundle failed", output)
        self.assertIn("Summary", output)
        self.assertIn("failed: Homebrew bundle", output)
        self.assertIn("applied: login shell", output)
        self.assertIn(f"chsh -s {self.fake_bin / 'zsh'}", self.logged())

    def test_shell_helpers_use_account_database_and_eligible_absolute_zsh(self):
        self.fake("zsh")
        self.fake("id", "case \"$1\" in -un) printf 'fixture-user\\n';; *) printf '1000\\n';; esac")
        self.fake("getent", "printf 'fixture-user:x:1000:1000::/home/fixture:/bin/bash\\n'")
        shells = self.root / "shells"
        shells.write_text(f"{self.fake_bin}/zsh\n")
        command = (
            ". ./install.sh; shells_file() { printf '%s\\n' \"$FIXTURE_SHELLS\"; }; "
            "discover_eligible_zsh"
        )
        env = {**self.env, "FIXTURE_SHELLS": str(shells), "SHELL": "/not/the/login-shell"}
        result = subprocess.run(["/bin/bash", "-c", command], cwd=self.checkout,
                                env=env, text=True, capture_output=True)
        self.assertEqual(str(self.fake_bin / "zsh"), result.stdout.strip(), result.stderr)
        result = subprocess.run(
            ["/bin/bash", "-c", ". ./install.sh; current_login_shell"], cwd=self.checkout,
            env=env, text=True, capture_output=True,
        )
        self.assertEqual("/bin/bash", result.stdout.strip())
        self.fake("chsh")
        command = (
            ". ./install.sh; shells_file() { printf '%s\\n' \"$FIXTURE_SHELLS\"; }; "
            "configure_login_shell"
        )
        result = subprocess.run(["/bin/bash", "-c", command], cwd=self.checkout,
                                env=env, input="y\n", text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn(f"chsh -s {self.fake_bin / 'zsh'}", self.logged())

    def shell_config_command(self):
        return (
            ". ./install.sh; shells_file() { printf '%s\\n' \"$FIXTURE_SHELLS\"; }; "
            "status=0; configure_login_shell || status=$?; print_summary; exit $status"
        )

    def shell_fixture(self, login_shell="/bin/bash"):
        self.fake("zsh")
        self.fake("id", "case \"$1\" in -un) printf 'fixture-user\\n';; *) printf '1000\\n';; esac")
        self.fake("getent", f"printf 'fixture-user:x:1000:1000::/home/fixture:{login_shell}\\n'")
        shells = self.root / "shells"
        shells.write_text(f"{self.fake_bin}/zsh\n")
        self.env["FIXTURE_SHELLS"] = str(shells)

    def test_shell_missing_account_lookup_is_safe(self):
        self.shell_fixture()
        (self.fake_bin / "getent").unlink()
        result = subprocess.run(
            ["/bin/bash", "-c", self.shell_config_command()], cwd=self.checkout,
            env=self.env, input="", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Account lookup via getent/id is unavailable", result.stderr)
        self.assertIn("skipped: login shell", result.stdout)

    def test_shell_missing_chsh_is_safe(self):
        self.shell_fixture()
        result = subprocess.run(
            ["/bin/bash", "-c", self.shell_config_command()], cwd=self.checkout,
            env=self.env, input="", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("chsh is unavailable", result.stderr)
        self.assertIn("skipped: login shell", result.stdout)

    def test_shell_ineligible_zsh_is_skipped(self):
        self.fake("zsh")
        shells = self.root / "shells"
        shells.write_text("/bin/zsh\n")
        self.env["FIXTURE_SHELLS"] = str(shells)
        result = subprocess.run(
            ["/bin/bash", "-c", self.shell_config_command()], cwd=self.checkout,
            env=self.env, input="", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("not an absolute executable listed", result.stderr)
        self.assertIn("skipped: login shell", result.stdout)

    def test_shell_already_current_is_idempotent_without_chsh(self):
        self.shell_fixture(login_shell=str(self.fake_bin / "zsh"))
        result = subprocess.run(
            ["/bin/bash", "-c", self.shell_config_command()], cwd=self.checkout,
            env=self.env, input="", text=True, capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("applied: login shell already zsh", result.stdout)
        self.assertNotIn("chsh", self.logged())

    def test_shell_decline_and_failure_are_reported(self):
        for answer, chsh_body, expected_code, expected_text in (
            ("n\n", "exit 0", 0, "skipped: login shell"),
            ("y\n", "exit 9", 1, "failed: login shell"),
        ):
            with self.subTest(answer=answer):
                self.shell_fixture()
                self.fake("chsh", chsh_body)
                result = subprocess.run(
                    ["/bin/bash", "-c", self.shell_config_command()], cwd=self.checkout,
                    env=self.env, input=answer, text=True, capture_output=True,
                )
                self.assertEqual(expected_code, result.returncode, result.stderr)
                self.assertIn(expected_text, result.stdout)
                if answer == "n\n":
                    self.assertNotIn("chsh -s", self.logged())


if __name__ == "__main__":
    unittest.main()
