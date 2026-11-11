set -u
echo "HOST: $(hostname)"
for d in /root/.hermes /root/.dsh /home/kams/.hermes /home/kams/.dsh /root/.local/share/opencode /root/.config/opencode; do
  if [ -d "$d" ]; then
    echo "DIR $d $(du -sh "$d" 2>/dev/null | cut -f1)"
  fi
done
echo "--- state.db files ---"
find / -name state.db -path "*hermes*" -not -path "*/node_modules/*" 2>/dev/null | head -12
echo "--- dsh session stores ---"
find / -type d -name "sessions" -path "*dsh*" 2>/dev/null | head -8
echo "--- opencode session dirs ---"
find / -type d -name "storage" -path "*opencode*" 2>/dev/null | head -8
