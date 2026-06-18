#!/usr/bin/env sh
# sigma installer — clone sigma, wire the `sigma` launcher, register the plugin.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/navidgh66/sigma/main/installer/setup.sh | sh
#
# Non-interactive by design (works under `curl | sh`, which has no stdin).
# All interactive setup — domains, API keys, RTK — happens in `sigma onboard`.

set -eu

REPO_SLUG="navidgh66/sigma"
AUTHOR="Navid Ghayazi"
REPO_URL="https://github.com/${REPO_SLUG}.git"
INSTALL_DIR="${SIGMA_HOME:-$HOME/.sigma}"
BIN_DIR="$HOME/.local/bin"

# --- colors (degrade to empty on dumb terminals) -------------------------- #
if [ -t 1 ] && command -v tput >/dev/null 2>&1 && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
  C_CYAN="$(tput setaf 6)"; C_GREEN="$(tput setaf 2)"; C_YEL="$(tput setaf 3)"
  C_MAG="$(tput setaf 5)"; C_BLU="$(tput setaf 4)"
  C_DIM="$(tput dim)"; C_RST="$(tput sgr0)"; C_B="$(tput bold)"
else
  C_CYAN=""; C_GREEN=""; C_YEL=""; C_MAG=""; C_BLU=""; C_DIM=""; C_RST=""; C_B=""
fi

# Tiny "animation": a sparkle line that draws in if we have a TTY (else one print).
sparkle_line() {
  if [ -t 1 ]; then
    _s='. : ✦ ✧ ⋆ ✶ ✷ ✦ ✧ ⋆ ✦ · ✦ ⋆ ✧ ✦ ·'
    printf "  %s" "$C_MAG"
    for _c in $_s; do printf "%s " "$_c"; sleep 0.02 2>/dev/null || true; done
    printf "%s\n" "$C_RST"
  else
    printf "  %s✦ ⋆ ✧ ✦ ⋆ ✧ ✦ ⋆ ✧ ✦ ⋆ ✧%s\n" "$C_MAG" "$C_RST"
  fi
}

step() { printf "%s[%s/6]%s %s\n" "$C_DIM" "$1" "$C_RST" "$2"; }
ok()   { printf "      %s✓%s %s\n" "$C_GREEN" "$C_RST" "$1"; }
warn() { printf "      %s⚠%s %s\n" "$C_YEL" "$C_RST" "$1"; }

# --- banner ---------------------------------------------------------------- #
sparkle_line
printf "%s%s" "$C_MAG" "$C_B"
cat <<'LOGO'
        __     ✦              ⋆
   ✧   / _\ ___ _ __ ___   __ _    ✦
      \ \  / __| '_ ` _ \ / _` |        ✦
   ✦  _\ \ \__ \ | | | | | (_| |   ⋆
      \__/ |___/_| |_| |_|\__,_|   ✧      σ
LOGO
printf "%s" "$C_RST"
printf "   %s%s✦ sigma%s %s— personal AI workflow toolkit%s\n" "$C_B" "$C_CYAN" "$C_RST" "$C_DIM" "$C_RST"
printf "   %sby %s%s ⋆ %s%s%s\n" "$C_DIM" "$C_RST$C_B" "$AUTHOR" "$C_RST$C_DIM" "$REPO_SLUG" "$C_RST"
sparkle_line
printf "\n"

# --- 1. fetch -------------------------------------------------------------- #
step 1 "Fetching sigma…"
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only >/dev/null 2>&1 && ok "updated $INSTALL_DIR"
else
  git clone --quiet "$REPO_URL" "$INSTALL_DIR" && ok "cloned into $INSTALL_DIR"
fi

# --- 2. python ------------------------------------------------------------- #
step 2 "Checking Python (3.9+)…"
if ! command -v python3 >/dev/null 2>&1; then
  warn "python3 not found — install Python 3.9+ and re-run"
  exit 1
fi
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if python3 -c 'import sys;exit(0 if sys.version_info[:2]>=(3,9) else 1)'; then
  ok "Python $PYV"
else
  warn "Python $PYV is too old — sigma targets 3.9+"
  exit 1
fi

# --- 3. launcher ----------------------------------------------------------- #
step 3 "Wiring the launcher…"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/sigma" <<EOF
#!/usr/bin/env sh
exec python3 "$INSTALL_DIR/cli/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/sigma"
ok "installed $BIN_DIR/sigma"

# --- 4. deps hint ---------------------------------------------------------- #
step 4 "Checking runtime deps…"
if python3 -c 'import yaml, rich' >/dev/null 2>&1; then
  ok "pyyaml + rich present"
else
  warn "missing deps — run: python3 -m pip install pyyaml rich"
fi

# --- 5. Claude Code plugin (best-effort; skip cleanly if claude absent) ----- #
step 5 "Registering Claude Code plugin…"
if command -v claude >/dev/null 2>&1; then
  if claude plugin marketplace add "$INSTALL_DIR" >/dev/null 2>&1; then
    ok "marketplace added (sigma)"
  else
    warn "marketplace already added or add failed — skipping"
  fi
  if claude plugin install sigma@sigma >/dev/null 2>&1; then
    ok "plugin installed — slash commands ready next Claude Code restart"
  else
    warn "plugin install skipped (already installed, or run it yourself)"
  fi
else
  warn "claude CLI not found — install it, then: claude plugin marketplace add $REPO_SLUG"
fi

# --- 6. PATH --------------------------------------------------------------- #
step 6 "Finishing up…"
case ":$PATH:" in
  *":$BIN_DIR:"*) ok "$BIN_DIR already on PATH" ;;
  *) warn "add to PATH:  export PATH=\"\$PATH:$BIN_DIR\"" ;;
esac

# --- summary card ---------------------------------------------------------- #
sparkle_line
printf "%s%s  ✦ sigma is installed.%s\n" "$C_GREEN" "$C_B" "$C_RST"
printf "  %s•%s Finish setup (domains, API keys, RTK):  %ssigma onboard%s\n" "$C_CYAN" "$C_RST" "$C_B" "$C_RST"
printf "  %s•%s Health check anytime:                    %ssigma doctor%s\n" "$C_CYAN" "$C_RST" "$C_B" "$C_RST"
printf "  %s•%s In Claude Code:  type %s/research%s, %s/hermes%s, %s/board%s … (restart to load)\n" \
  "$C_CYAN" "$C_RST" "$C_B" "$C_RST" "$C_B" "$C_RST" "$C_B" "$C_RST"
printf "  %s☕ Tip:%s RTK (token saver) can be set up during %ssigma onboard%s\n" "$C_YEL" "$C_RST" "$C_B" "$C_RST"
printf "\n  Verify:  %ssigma --version%s\n\n" "$C_B" "$C_RST"
