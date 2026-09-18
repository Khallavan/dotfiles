#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: ./install.sh' \
        '' \
        'Interactively validates this checkout, installs missing core dependencies, and' \
        'can link Zsh/Tmux, restore TPM or Homebrew packages, and change the login shell.' \
        'Do not run the whole installer with sudo; it requests privilege only for dependencies.'
}

APPLIED=()
SKIPPED=()
FAILED=()
PROMPT_RESULT=''
CHECKOUT_DIR=''

record_applied() { APPLIED+=("$1"); }
record_skipped() { SKIPPED+=("$1"); }
record_failed() { FAILED+=("$1"); }

print_summary() {
    local item
    printf '\nSummary\n'
    for item in "${APPLIED[@]}"; do printf 'applied: %s\n' "$item"; done
    for item in "${SKIPPED[@]}"; do printf 'skipped: %s\n' "$item"; done
    for item in "${FAILED[@]}"; do printf 'failed: %s\n' "$item"; done
}

cancel() {
    printf '\nInstallation cancelled by signal. Completed work is listed below.\n' >&2
    record_failed 'cancelled by signal'
    print_summary
    exit 130
}

# Sets PROMPT_RESULT to yes, no, cancel, or eof. Blank answers are explicit no.
ask_yes_no() {
    local prompt answer
    prompt=$1
    while true; do
        printf '%s [y/N] ' "$prompt"
        if ! IFS= read -r answer; then
            printf '\nInstallation cancelled: input ended.\n' >&2
            PROMPT_RESULT=eof
            return 2
        fi
        case "$answer" in
            y|Y|yes|YES) PROMPT_RESULT=yes; return 0 ;;
            n|N|no|NO|'') PROMPT_RESULT=no; return 1 ;;
            cancel|CANCEL) PROMPT_RESULT=cancel; return 2 ;;
            *) printf 'Please answer yes, no, or cancel.\n' ;;
        esac
    done
}

# The optional argument is a parser-only test seam. Main always supplies
# /etc/os-release, so environment variables cannot alter live detection.
detect_package_manager() {
    local release_file=${1:-/etc/os-release} id='' id_like='' key value line
    local family='' candidate token
    [ -r "$release_file" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ID=*|ID_LIKE=*)
                key=${line%%=*}; value=${line#*=}
                value=${value#\"}; value=${value%\"}
                value=${value#\'}; value=${value%\'}
                case "$key" in ID) id=$value ;; ID_LIKE) id_like=$value ;; esac
                ;;
        esac
    done < "$release_file"
    case "$id" in
        arch|cachyos) printf 'pacman\n'; return 0 ;;
        fedora|rhel|centos|rocky|almalinux) printf 'dnf\n'; return 0 ;;
        debian|ubuntu|linuxmint|pop) printf 'apt-get\n'; return 0 ;;
    esac
    for token in $id_like; do
        candidate=''
        case "$token" in
            arch|cachyos) candidate=pacman ;; fedora|rhel|centos|rocky|almalinux) candidate=dnf ;;
            debian|ubuntu|linuxmint|pop) candidate=apt-get ;;
        esac
        [ -n "$candidate" ] || continue
        if [ -n "$family" ] && [ "$family" != "$candidate" ]; then return 1; fi
        family=$candidate
    done
    [ -n "$family" ] || return 1
    printf '%s\n' "$family"
}

resolve_package_manager() { detect_package_manager /etc/os-release; }

validate_checkout() {
    local required
    for required in zsh/.zshrc tmux/.tmux.conf Brewfile; do
        if [ ! -f "$CHECKOUT_DIR/$required" ]; then
            printf 'Invalid dotfiles checkout: missing %s.\n' "$required" >&2
            return 1
        fi
    done
}

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@" || return 1
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@" || return 1
    else
        printf 'Administrator privileges are required; sudo is unavailable.\n' >&2
        return 1
    fi
}

require_package_manager() {
    local manager=$1
    command -v "$manager" >/dev/null 2>&1 || {
        printf 'Selected package manager %s is unavailable; dependencies were not installed.\n' "$manager" >&2
        return 1
    }
}

install_missing_dependencies() {
    local manager=$1; shift
    case "$manager" in
        apt-get)
            run_privileged apt-get install -y "$@" || return 1
            ;;
        dnf)
            run_privileged dnf install -y "$@" || return 1
            ;;
        pacman)
            run_privileged pacman -S --needed "$@" || return 1
            ;;
        *) return 1 ;;
    esac
}

ensure_dependencies() {
    local dependency manager missing=() missing_display
    for dependency in stow git zsh tmux; do command -v "$dependency" >/dev/null 2>&1 || missing+=("$dependency"); done
    [ "${#missing[@]}" -eq 0 ] && return 0
    manager=$(resolve_package_manager) || { printf 'Unsupported Linux distribution: cannot install %s.\n' "${missing[*]}" >&2; return 1; }
    require_package_manager "$manager" || return 1
    missing_display=${missing[*]}; missing_display=${missing_display// /, }
    printf 'Missing core dependencies: %s\n' "$missing_display"
    ask_yes_no "Install missing dependencies using $manager?" || {
        [ "$PROMPT_RESULT" != no ] && return 2
        printf 'Installation cancelled: dependencies were not installed.\n' >&2; return 1
    }
    install_missing_dependencies "$manager" "${missing[@]}" || return 1
    missing=()
    for dependency in stow git zsh tmux; do command -v "$dependency" >/dev/null 2>&1 || missing+=("$dependency"); done
    [ "${#missing[@]}" -eq 0 ] || { printf 'Dependencies are still missing after installation: %s.\n' "${missing[*]}" >&2; return 1; }
    record_applied "core dependencies ($missing_display)"
}

ensure_canonical_path_safe() {
    local canonical="$HOME/dotfiles" resolved
    if [ ! -e "$canonical" ] && [ ! -L "$canonical" ]; then return 0; fi
    resolved=$(cd -P "$canonical" 2>/dev/null && pwd) || { printf 'Canonical checkout %s exists but is not a valid checkout path; it will not be replaced.\n' "$canonical" >&2; return 1; }
    [ "$resolved" = "$CHECKOUT_DIR" ] || { printf 'Canonical checkout %s already exists but does not match this checkout; it will not be replaced.\n' "$canonical" >&2; return 1; }
}

ensure_canonical_checkout() {
    local canonical="$HOME/dotfiles"
    ensure_canonical_path_safe || return 1
    if [ -e "$canonical" ] || [ -L "$canonical" ]; then record_applied 'canonical checkout already correct'; return 0; fi
    ask_yes_no "Create $canonical as a symlink to this checkout?" || {
        [ "$PROMPT_RESULT" != no ] && return 2
        printf 'Installation cancelled: canonical checkout was not created.\n' >&2; return 1
    }
    if ! ln -s "$CHECKOUT_DIR" "$canonical"; then
        printf 'Failed to create canonical checkout %s; dependent steps were not run.\n' "$canonical" >&2
        record_failed "canonical checkout ($canonical)"
        return 1
    fi
    record_applied "canonical checkout ($canonical)"
    printf 'Created %s -> %s\n' "$canonical" "$CHECKOUT_DIR"
}

link_stow_group() {
    if ! stow -n -v -d "$CHECKOUT_DIR" -t "$HOME" zsh tmux; then
        printf 'Stow preview found conflicts; the zsh+tmux group was not changed.\n' >&2
        record_failed 'zsh+tmux link group (preview conflict)'
        return 1
    fi
    ask_yes_no 'Link the previewed zsh+tmux group into your HOME directory?' || {
        [ "$PROMPT_RESULT" != no ] && return 2
        record_skipped 'zsh+tmux link group'; return 0
    }
    stow -d "$CHECKOUT_DIR" -t "$HOME" zsh tmux || { record_failed 'zsh+tmux link group'; return 1; }
    record_applied 'zsh+tmux link group'
}

tpm_parent_is_safe() {
    [ ! -L "$HOME/.tmux" ] && [ ! -L "$HOME/.tmux/plugins" ]
}

valid_tpm() {
    local target=$1 origin
    [ -d "$target" ] && [ ! -L "$target" ] || return 1
    git -C "$target" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    origin=$(git -C "$target" remote get-url origin 2>/dev/null) || return 1
    [ "$origin" = 'https://github.com/tmux-plugins/tpm' ] && [ -f "$target/tpm" ] && [ -f "$target/bin/install_plugins" ]
}

restore_tpm() {
    local target="$HOME/.tmux/plugins/tpm" parent="$HOME/.tmux/plugins"
    if ! tpm_parent_is_safe; then
        printf 'TPM parent contains a symlink and will not be followed.\n' >&2
        record_failed 'TPM parent safety'
        return 1
    fi
    if [ -e "$target" ] || [ -L "$target" ]; then
        if valid_tpm "$target"; then record_applied 'TPM already valid'; return 0; fi
        printf 'Existing TPM target is invalid, foreign, dangling, or incomplete; it was not changed.\n' >&2
        record_failed 'TPM validation'; return 1
    fi
    ask_yes_no 'Clone optional TPM for tmux plugins?' || {
        [ "$PROMPT_RESULT" != no ] && return 2
        record_skipped 'TPM'; return 0
    }
    if [ ! -d "$parent" ]; then
        ask_yes_no "Create required TPM directory $parent?" || {
            [ "$PROMPT_RESULT" != no ] && return 2
            record_skipped 'TPM (directory not approved)'; return 0
        }
        if ! mkdir -p "$parent"; then
            printf 'Failed to create required TPM directory %s; TPM was not cloned.\n' "$parent" >&2
            record_failed 'TPM directory'
            return 1
        fi
    fi
    if ! git clone https://github.com/tmux-plugins/tpm "$target"; then
        printf 'TPM clone failed; the target was not applied.\n' >&2
        record_failed 'TPM clone'
        return 1
    fi
    record_applied 'TPM'
}

restore_brew() {
    command -v brew >/dev/null 2>&1 || { record_skipped 'Homebrew bundle (brew unavailable)'; return 0; }
    printf 'The Brewfile may contain Linux-unfriendly macOS apps or VS Code entries; review its output.\n'
    ask_yes_no 'Run optional Homebrew bundle now?' || {
        [ "$PROMPT_RESULT" != no ] && return 2
        record_skipped 'Homebrew bundle'; return 0
    }
    brew bundle --file "$CHECKOUT_DIR/Brewfile" || { printf 'Homebrew bundle failed; independent optional steps will continue.\n' >&2; record_failed 'Homebrew bundle'; return 1; }
    record_applied 'Homebrew bundle'
}

shells_file() { printf '%s\n' /etc/shells; }

discover_eligible_zsh() {
    local zsh_path shells line
    zsh_path=$(command -v zsh 2>/dev/null) || return 1
    case "$zsh_path" in /*) ;; *) return 1 ;; esac
    [ -x "$zsh_path" ] || return 1
    shells=$(shells_file)
    [ -r "$shells" ] || return 1
    while IFS= read -r line || [ -n "$line" ]; do [ "$line" = "$zsh_path" ] && { printf '%s\n' "$zsh_path"; return 0; }; done < "$shells"
    return 1
}

current_login_shell() {
    local account entry _ _ _ _ _ shell
    command -v getent >/dev/null 2>&1 || return 2
    account=$(id -un 2>/dev/null) || return 2
    entry=$(getent passwd "$account") || return 2
    IFS=: read -r _ _ _ _ _ _ shell <<EOF
$entry
EOF
    [ -n "$shell" ] && printf '%s\n' "$shell"
}

configure_login_shell() {
    local zsh_path current
    zsh_path=$(discover_eligible_zsh) || { printf 'Zsh is not an absolute executable listed in /etc/shells; login shell was not changed.\n' >&2; record_skipped 'login shell (ineligible zsh)'; return 0; }
    current=$(current_login_shell) || {
        if [ "$?" -eq 2 ]; then printf 'Account lookup via getent/id is unavailable; login shell was not changed.\n' >&2; fi
        record_skipped 'login shell (account lookup unavailable)'; return 0
    }
    [ "$current" = "$zsh_path" ] && { record_applied 'login shell already zsh'; return 0; }
    command -v chsh >/dev/null 2>&1 || { printf 'chsh is unavailable; login shell was not changed.\n' >&2; record_skipped 'login shell (chsh unavailable)'; return 0; }
    ask_yes_no "Change login shell for the current account from $current to $zsh_path?" || {
        [ "$PROMPT_RESULT" != no ] && return 2
        record_skipped 'login shell'; return 0
    }
    chsh -s "$zsh_path" || { record_failed 'login shell'; return 1; }
    record_applied 'login shell'
}

main() {
    local script_path script_dir status=0 result
    case "${1:-}" in -h|--help) usage; return 0 ;; '') ;; *) usage >&2; return 2 ;; esac
    script_path=${BASH_SOURCE[0]}; case "$script_path" in */*) script_dir=${script_path%/*} ;; *) script_dir=. ;; esac
    CHECKOUT_DIR=$(cd -P "$script_dir" && pwd)
    validate_checkout || return 1
    ensure_canonical_path_safe || return 1
    if [ ! -t 0 ] || [ ! -t 1 ]; then printf 'Error: an interactive terminal is required; no changes were made.\n' >&2; return 2; fi
    trap cancel INT TERM
    ensure_dependencies || { result=$?; record_failed 'core dependencies'; print_summary; return "$result"; }
    ensure_canonical_checkout || { result=$?; record_failed 'canonical checkout'; print_summary; return "$result"; }
    link_stow_group || { result=$?; [ "$result" -eq 2 ] && { record_failed 'cancelled at linking'; print_summary; return 2; }; status=1; }
    restore_tpm || { result=$?; [ "$result" -eq 2 ] && { record_failed 'cancelled at TPM'; print_summary; return 2; }; status=1; }
    restore_brew || { result=$?; [ "$result" -eq 2 ] && { record_failed 'cancelled at Homebrew'; print_summary; return 2; }; status=1; }
    configure_login_shell || { result=$?; [ "$result" -eq 2 ] && { record_failed 'cancelled at login shell'; print_summary; return 2; }; status=1; }
    print_summary
    return "$status"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
