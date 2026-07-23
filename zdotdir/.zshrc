# herdr-jail ZDOTDIR .zshrc — loaded by the enforcing Herdr shell.
#
# Source the user's real interactive config FIRST (so mise/pyenv/PATH edits all
# run), THEN prepend our shim dir so agent shims outrank the real binaries no
# matter what the user's config did. Non-invasive: the user's files are read,
# never modified.
: "${HERDR_JAIL_REAL_ZDOTDIR:=$HOME}"
if [ -r "$HERDR_JAIL_REAL_ZDOTDIR/.zshrc" ]; then
  # Temporarily restore ZDOTDIR so the real .zshrc's own references resolve.
  _hj_zdotdir="$ZDOTDIR"
  ZDOTDIR="$HERDR_JAIL_REAL_ZDOTDIR"
  source "$HERDR_JAIL_REAL_ZDOTDIR/.zshrc"
  ZDOTDIR="$_hj_zdotdir"
  unset _hj_zdotdir
fi

# Now win the PATH race — prepend the shim dir last.
export PATH="${HERDR_JAIL_SHIM_DIR:-$HOME/.herdr-jail-shims}:$PATH"
export HERDR_JAIL_ENFORCED=1
