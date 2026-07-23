# Load the user's real .zshenv (login/non-login both read this).
[ -r "${HERDR_JAIL_REAL_ZDOTDIR:-$HOME}/.zshenv" ] && source "${HERDR_JAIL_REAL_ZDOTDIR:-$HOME}/.zshenv"
