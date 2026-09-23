# Dotfiles

¡Bienvenido a mi repositorio de dotfiles! Aquí mantengo mi configuración personal para el sistema, terminal, y herramientas de desarrollo.

## 🛠 Qué incluye

Este repositorio gestiona la configuración de las siguientes herramientas:

- **Zsh:** Configuración del shell a través de `.zshrc`.
- **Herdr (opcional):** Multiplexor preferido si está instalado localmente; su configuración se enlaza desde `herdr/.config/herdr/config.toml` mediante Stow.
- **Tmux:** Multiplexor conservado como alternativa cuando Herdr no está disponible, con sesión principal persistente y tema Gruvbox.
- **Homebrew:** Gestión de paquetes de macOS/Linux y extensiones de VS Code a través de `Brewfile`.
- **Oh My Posh:** Tema de terminal (`pure.omp.json`).
- Listas de paquetes globales instalados para **Rust (Cargo)**, **Python (uv)**, y **Node.js (npm)**.

## 🚀 Instalación

Puedes instalar rápidamente estos dotfiles clonando el repositorio y ejecutando el script de instalación.

```bash
git clone https://github.com/tu-usuario/dotfiles.git ~/dotfiles
cd ~/dotfiles
chmod +x install.sh
./install.sh
```

### What does `install.sh` do?

1. Validates the checkout and detects Debian/Ubuntu, Fedora/RHEL, Arch, or CachyOS.
2. Offers one confirmed native package-manager operation for missing `stow`, `git`, `zsh`, and `tmux`.
3. Offers the canonical `~/dotfiles` symlink, then previews the complete Zsh/Tmux Stow group before any links are created.
4. Separately offers optional TPM, an already-installed Homebrew bundle, and an eligible login-shell change.
5. Prints a final summary of applied, skipped, and failed work. It never installs Homebrew or Herdr, overwrites conflicts, or runs `chsh` through `sudo`; Herdr setup is separate from this installer.

## Portable Linux installer

`./install.sh` is an English-only interactive installer for Debian/Ubuntu, Fedora/RHEL, Arch, and CachyOS. Run it from a valid checkout in a terminal; do **not** run the whole script with `sudo`.

```bash
./install.sh
```

The required core tools are `stow`, `git`, `zsh`, and `tmux`. When any are missing, the installer offers one confirmed native package-manager operation (`apt-get`, `dnf`, or `pacman`). It never installs Homebrew.

| Step | Safety behavior |
| --- | --- |
| Canonical checkout | Offers `~/dotfiles -> <current checkout>` only when absent; an existing foreign or dangling path is never replaced. |
| Zsh and Tmux links | Runs a read-only Stow preview for the complete `zsh` + `tmux` group before asking to link it to `HOME`. Conflicts prevent the whole group from changing; Stow does not adopt or overwrite files. |
| TPM | Optional. The installer creates `~/.tmux/plugins` only after confirmation and clones only the official TPM URL into an absent safe target. Existing targets must be the expected Git checkout or are left untouched. |
| Homebrew bundle | Optional and offered only if `brew` already exists. Brewfile entries can be unsuitable for Linux (for example macOS applications or VS Code entries); failures are reported in the final summary. |
| Login shell | Optional. The discovered absolute `zsh` must be listed in `/etc/shells`; the current account is looked up through `getent`/`id`, then `chsh` is separately confirmed without `sudo`. |

Every question accepts `yes`, `no`, or `cancel` through terminal interruption; blank means no. End-of-input or Ctrl-C stops dependent work with a nonzero result. The final summary distinguishes applied, skipped, and failed steps, so cancellation never implies that earlier changes were reverted.

Tests use a PTY, a temporary HOME, and fake tools. They exercise control flow and simulated Stow invocations; they do not claim real distribution, package-manager, network, `chsh`, or Stow integration verification. `herdr` remains deliberately deferred.

## Zsh portability and optional tools

The installer manages required tools and dotfile links; the shell configuration only detects optional tools that are already installed. It does not install optional tools or bootstrap Zinit.

`zsh/.zshrc` uses `$HOME` and XDG paths, keeps PATH entries unique, and continues without errors when `oh-my-posh`, `fzf`, `zoxide`, `fnm`, Bun, pnpm, `eza`, or Neovim is absent. A readable `pure.omp.json` is required for `oh-my-posh`; an `fzf` binary must also support `fzf --zsh`. Without `eza` or Neovim, `ll` and `vim` use conservative fallbacks. In an interactive terminal outside tmux or Herdr, Zsh starts Herdr when installed locally; otherwise it attaches to the tmux `main` session or creates it. The installer does not install Herdr or link its configuration; link `herdr/.config/herdr/config.toml` separately with Stow.

Zinit remains optional. An existing installation can load the configured plugins, but a missing installation is skipped without cloning or making a network request during shell startup. To enable it, install it manually before starting Zsh:

```bash
ZINIT_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/zinit/zinit.git"
mkdir -p "$(dirname "$ZINIT_HOME")"
git clone https://github.com/zdharma-continuum/zinit.git "$ZINIT_HOME"
```

## 🖥 Tmux

La configuración de tmux se instala con **GNU Stow** desde `tmux/.tmux.conf`.

Si quieres ver la guía completa de instalación, plugins, atajos y verificación, consulta:

- [TMUX_TUTORIAL.md](TMUX_TUTORIAL.md)

## 📦 Herramientas Globales Adicionales

El script de instalación no instala automáticamente los paquetes globales de otros ecosistemas para evitar conflictos. Sin embargo, puedes consultar los siguientes archivos en este repositorio para ver qué herramientas están recomendadas e instalarlas manualmente:

- `npm_globals.txt` (Para herramientas de Node.js instaladas vía npm)
- `cargo_globals.txt` (Para herramientas de Rust instaladas vía Cargo)
- `uv_tools.txt` (Para herramientas de Python instaladas vía uv)

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.
