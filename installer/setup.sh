#!/usr/bin/env sh
# sigma installer — clone/symlink sigma into ~/.local/bin
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh

set -eu

REPO_URL="https://github.com/navidgh66/sigma.git"
INSTALL_DIR="${SIGMA_HOME:-$HOME/.sigma}"
BIN_DIR="$HOME/.local/bin"

echo "→ Installing sigma..."

# 1. Fetch the repo (clone or update)
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "  updating existing install at $INSTALL_DIR"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "  cloning into $INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 2. Check Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
  echo "  ✗ python3 not found. Install Python 3.10+ and re-run." >&2
  exit 1
fi

# 3. Wire the launcher
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/sigma" <<EOF
#!/usr/bin/env sh
exec python3 "$INSTALL_DIR/cli/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/sigma"

echo "✓ sigma installed to $BIN_DIR/sigma"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "  Add to PATH:  export PATH=\"\$PATH:$BIN_DIR\"" ;;
esac
echo "  Verify:  sigma --version"
