set -u
echo "=== files containing token accounting keys (outside .dsh sessions) ==="
grep -rl "uncachedInputTokens\|cacheReadTokens" /root /home --include="*.json" --include="*.jsonl" 2>/dev/null \
  | grep -v "/.dsh/storages/" | head -20
echo "=== other session-ish stores ==="
find /root /home -maxdepth 6 -type d \( -name "sessions" -o -name "storage" -o -name "history" \) 2>/dev/null \
  | grep -viE "node_modules|/.git/|/.cache/|site-packages|/.nvm/" | head -20
echo "=== processes using an opencode endpoint ==="
ps -eo pid,etime,cmd 2>/dev/null | grep -iE "opencode|superagent|firstmate|mission" | grep -v grep | cut -c1-160 | head -12
echo "=== configs mentioning opencode.ai ==="
grep -rl "opencode.ai" /root/.config /root/.dsh /root/projects --include="*.json" --include="*.yaml" --include="*.yml" --include="*.toml" 2>/dev/null | head -12
