#!/bin/bash
set -e

DOTFILES_DIR="$HOME/dotfiles"
echo "Starting dotfiles installation..."

# 0. Ensure GNU Stow is installed
if ! command -v stow &> /dev/null; then
    echo "GNU Stow is not installed. Attempting to install..."
    if command -v dnf &> /dev/null; then
        sudo dnf install -y stow
    elif command -v brew &> /dev/null; then
        brew install stow
    else
        echo "Error: Neither dnf nor brew found. Please install GNU Stow manually."
        exit 1
    fi
fi

# 1. Symlink configurations using GNU Stow
echo "Symlinking dotfiles using GNU Stow..."
cd "$DOTFILES_DIR"
stow zsh
stow git
stow tmux

# 2. Restore Homebrew packages
echo "Restoring Homebrew packages..."
if command -v brew &> /dev/null; then
    brew bundle --file="$DOTFILES_DIR/Brewfile"
else
    echo "Warning: Homebrew is not installed. Skipping 'brew bundle'."
    echo "Install Homebrew manually via: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
fi

# 3. Ensure Zsh is the default shell
echo "Setting Zsh as default shell..."
if [ "$SHELL" != "$(which zsh)" ]; then
    chsh -s "$(which zsh)"
else
    echo "Zsh is already the default shell."
fi

# 4. Reminders for other ecosystems
echo ""
echo "Note: Reinstall your global tools for Rust, Node, and uv."
echo "Check the following files in \$DOTFILES_DIR to see what you had installed:"
echo " - cargo_globals.txt (Rust)"
echo " - uv_tools.txt (Python/uv)"
echo " - npm_globals.txt (Node.js)"

echo ""
echo "Installation complete! Please restart your terminal."
