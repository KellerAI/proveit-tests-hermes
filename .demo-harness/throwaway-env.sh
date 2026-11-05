# Source (bash) to use a throwaway Hermes install. Isolated HOME + HERMES_HOME; never ~/.hermes.
# Default layout: <parent-of-repo>/throwaway-hermes/{home,hermes-home,venv}. Override with PROVEIT_THROWAWAY.
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THROWAWAY="${PROVEIT_THROWAWAY:-$(cd "$_here/../.." && pwd)/throwaway-hermes}"
export HOME="$THROWAWAY/home"
export HERMES_HOME="$THROWAWAY/hermes-home"
export XDG_CONFIG_HOME="$THROWAWAY/home/.config" XDG_DATA_HOME="$THROWAWAY/home/.local/share" XDG_CACHE_HOME="$THROWAWAY/home/.cache"
export PATH="$THROWAWAY/venv/bin:$PATH"
# No provider keys: the demo is scripted and must not spend.
unset OPENAI_API_KEY ANTHROPIC_API_KEY OPENROUTER_API_KEY NOUS_API_KEY
unset _here
