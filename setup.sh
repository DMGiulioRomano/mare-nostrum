#!/usr/bin/env zsh
# Setup una-tantum per granulation-studies.
# Idempotente: rieseguibile senza effetti collaterali.

set -e

ZSHRC="$HOME/.zshrc"
MARKER="# granulation-studies"

# ── direnv ────────────────────────────────────────────────────────────────────
if ! command -v direnv &>/dev/null; then
  echo "→ installo direnv..."
  if command -v brew &>/dev/null; then
    brew install direnv
  else
    echo "ERRORE: brew non trovato. Installa direnv manualmente: https://direnv.net"
    exit 1
  fi
fi

direnv allow "$(dirname "$0:A")"

# ── direnv hook (indipendente dal marker) ─────────────────────────────────────
if ! grep -qF 'eval "$(direnv hook zsh)"' "$ZSHRC" 2>/dev/null; then
  echo "→ aggiungo direnv hook a ~/.zshrc..."
  echo '\neval "$(direnv hook zsh)"' >> "$ZSHRC"
fi

# ── precmd per le completion (marcato, idempotente) ───────────────────────────
if grep -qF "$MARKER" "$ZSHRC" 2>/dev/null; then
  echo "→ completion hook già presente in ~/.zshrc, skip."
else
  echo "→ aggiungo completion hook a ~/.zshrc..."
  cat >> "$ZSHRC" <<'EOF'

autoload -Uz compinit && compinit -C

# granulation-studies
# Carica tutti i file locali dal repo quando direnv imposta GRANSTUDIES_ROOT.
# Il check su _granstudies_last_root evita di ricaricare ad ogni comando.
_granstudies_completion_precmd() {
  local cur="${GRANSTUDIES_ROOT:-}"
  [[ "$cur" == "${_granstudies_last_root:-}" ]] && return
  _granstudies_last_root="$cur"
  if [[ -n "$cur" && -d "$cur/.zsh_completions" ]]; then
    for f in "$cur"/.zsh_completions/_*(N); do
      source "$f"
    done
    compdef _make_with_study make
  fi
}
precmd_functions+=(_granstudies_completion_precmd)
EOF
fi

echo "✓ setup completato. Apri un nuovo terminale per attivare le completion."
