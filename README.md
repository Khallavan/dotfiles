# Dotfiles

¡Bienvenido a mi repositorio de dotfiles! Aquí mantengo mi configuración personal para el sistema, terminal, y herramientas de desarrollo.

## 🛠 Qué incluye

Este repositorio gestiona la configuración de las siguientes herramientas:

- **Zsh:** Configuración del shell a través de `.zshrc`.
- **Git:** Configuraciones y alias globales en `.gitconfig`.
- **Tmux:** Multiplexor de terminal con sesión principal persistente y tema Gruvbox.
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

### ¿Qué hace el script `install.sh`?

1. Verifica si **GNU Stow** está instalado (y lo instala vía `dnf` o `brew` si es necesario).
2. Utiliza **GNU Stow** para crear enlaces simbólicos (symlinks) de tus paquetes de configuración (`zsh`, `git`, `tmux`) en tu directorio `home` (`~`).
3. Instala los paquetes, aplicaciones y extensiones de VS Code definidos en el `Brewfile` utilizando Homebrew.
4. Configura **Zsh** como tu shell predeterminado.
5. Muestra recordatorios útiles para reinstalar herramientas globales de Node.js, Rust y Python.

## 📦 Herramientas Globales Adicionales

El script de instalación no instala automáticamente los paquetes globales de otros ecosistemas para evitar conflictos. Sin embargo, puedes consultar los siguientes archivos en este repositorio para ver qué herramientas están recomendadas e instalarlas manualmente:

- `npm_globals.txt` (Para herramientas de Node.js instaladas vía npm)
- `cargo_globals.txt` (Para herramientas de Rust instaladas vía Cargo)
- `uv_tools.txt` (Para herramientas de Python instaladas vía uv)

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo [LICENSE](LICENSE) para más detalles.
