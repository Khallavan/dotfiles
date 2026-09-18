# Keep user-specific paths portable and unique, including paths with spaces.
typeset -U path
_prepend_path() {
	[[ -n "$1" ]] || return 0
	path=("$1" "${path[@]}")
}

_prepend_path "$HOME/.local/bin"
_prepend_path "$HOME/.opencode/bin"

# Prefer an explicit Homebrew prefix, then user-local or shared Linuxbrew.
if [[ -n ${HOMEBREW_PREFIX:-} ]]; then
	_prepend_path "$HOMEBREW_PREFIX/bin"
elif [[ -d "$HOME/.linuxbrew/bin" ]]; then
	_prepend_path "$HOME/.linuxbrew/bin"
elif [[ -d /home/linuxbrew/.linuxbrew/bin ]]; then
	_prepend_path /home/linuxbrew/.linuxbrew/bin
fi

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

# Zinit is optional. Never clone or bootstrap a missing plugin manager at startup.
ZINIT_HOME="${ZINIT_HOME:-$XDG_DATA_HOME/zinit/zinit.git}"
if [[ -r "$ZINIT_HOME/zinit.zsh" ]] && source "$ZINIT_HOME/zinit.zsh" 2>/dev/null; then
	if (( $+functions[zinit] )); then
		zinit light zsh-users/zsh-syntax-highlighting 2>/dev/null
		zinit light zsh-users/zsh-completions 2>/dev/null
		zinit light zsh-users/zsh-autosuggestions 2>/dev/null
		zinit light Aloxaf/fzf-tab 2>/dev/null

		zinit snippet OMZL::git.zsh 2>/dev/null
		zinit snippet OMZP::git 2>/dev/null
		zinit snippet OMZP::sudo 2>/dev/null
		if command -v dnf >/dev/null 2>&1; then
			zinit snippet OMZP::dnf 2>/dev/null
		fi
		zinit snippet OMZP::uv 2>/dev/null
		zinit snippet OMZP::command-not-found 2>/dev/null
	fi
fi

# Completion works with or without Zinit.
typeset -i _completion_initialized=0
if autoload -Uz compinit && compinit 2>/dev/null; then
	_completion_initialized=1
fi
if (( _completion_initialized )) && (( $+functions[zinit] )); then
	zinit cdreplay -q 2>/dev/null
fi
unset _completion_initialized

# oh-my-posh is optional and only runs with a readable configuration file.
if command -v oh-my-posh >/dev/null 2>&1; then
	_oh_my_posh_config="${OH_MY_POSH_CONFIG:-}"
	if [[ -z "$_oh_my_posh_config" ]]; then
		if [[ -f "$HOME/dotfiles/pure.omp.json" && -r "$HOME/dotfiles/pure.omp.json" ]]; then
			_oh_my_posh_config="$HOME/dotfiles/pure.omp.json"
		elif [[ -f "${XDG_CONFIG_HOME:-$HOME/.config}/oh-my-posh/pure.omp.json" && -r "${XDG_CONFIG_HOME:-$HOME/.config}/oh-my-posh/pure.omp.json" ]]; then
			_oh_my_posh_config="${XDG_CONFIG_HOME:-$HOME/.config}/oh-my-posh/pure.omp.json"
		fi
	fi
	if [[ -n "$_oh_my_posh_config" && -f "$_oh_my_posh_config" && -r "$_oh_my_posh_config" ]]; then
		if _oh_my_posh_init="$(oh-my-posh init zsh --config "$_oh_my_posh_config" 2>/dev/null)"; then
			eval "$_oh_my_posh_init" 2>/dev/null || :
		fi
	fi
	unset _oh_my_posh_config _oh_my_posh_init
fi

# Keybindings
bindkey -e

bindkey '^p' history-search-backward
bindkey '^n' history-search-forward
bindkey '^[w' kill-region

# History
HISTSIZE=5000
HISTFILE="$HOME/.zsh_history"
SAVEHIST=$HISTSIZE
HISTDUP=erase

setopt appendhistory
setopt sharehistory
setopt hist_ignore_space
setopt hist_ignore_all_dups
setopt hist_save_no_dups
setopt hist_ignore_dups
setopt hist_find_no_dups

# Completion styling
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Za-z}'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
zstyle ':completion:*' menu no
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'ls --color $realpath'
zstyle ':fzf-tab:complete:__zoxide_z:*' fzf-preview 'ls --color $realpath'

# Aliases
alias ls='ls --color'
alias c='clear'
if command -v eza >/dev/null 2>&1; then
	alias ll='eza -la --icons=auto --group-directories-first --git -a'
else
	alias ll='ls -la'
fi
if command -v nvim >/dev/null 2>&1; then
	alias vim='nvim'
elif command -v vim >/dev/null 2>&1; then
	alias vim="${commands[vim]}"
elif command -v vi >/dev/null 2>&1; then
	alias vim='vi'
fi

# Shell integrations are optional and must tolerate older tool versions.
if command -v fzf >/dev/null 2>&1; then
	if _fzf_init="$(fzf --zsh 2>/dev/null)"; then
		eval "$_fzf_init" 2>/dev/null || :
	fi
	unset _fzf_init
fi

if command -v zoxide >/dev/null 2>&1; then
	if _zoxide_init="$(zoxide init --cmd cd zsh 2>/dev/null)"; then
		eval "$_zoxide_init" 2>/dev/null || :
	fi
	unset _zoxide_init
fi

# fnm
_prepend_path "$XDG_DATA_HOME/fnm"
if command -v fnm >/dev/null 2>&1; then
	if _fnm_env="$(fnm env --use-on-cd --shell zsh 2>/dev/null)"; then
		eval "$_fnm_env" 2>/dev/null || :
	fi
	unset _fnm_env
fi

# bun completions and binaries
BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
export BUN_INSTALL
_prepend_path "$BUN_INSTALL/bin"
if [[ -r "$BUN_INSTALL/_bun" ]]; then
	source "$BUN_INSTALL/_bun" 2>/dev/null || :
fi

# pnpm
PNPM_HOME="${PNPM_HOME:-$XDG_DATA_HOME/pnpm}"
export PNPM_HOME
_prepend_path "$PNPM_HOME"
_prepend_path "$PNPM_HOME/bin"

# Keep user-local executables ahead of package-manager shims.
_prepend_path "$HOME/.local/bin"

# Auto-start tmux in the main session
if command -v tmux >/dev/null 2>&1; then
	if [[ -o interactive ]] && [[ -z "$TMUX" ]] && [[ "$TERM" != "dumb" ]]; then
		tmux attach-session -t main 2>/dev/null || exec tmux new-session -s main
	fi
fi
