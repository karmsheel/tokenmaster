set -u
echo "=== homes ==="
ls -d /root /home/* 2>/dev/null
echo "=== candidate data roots ==="
for d in /root/.hermes /root/.dsh /root/.local/share/opencode /root/.config/opencode \
         /home/*/.hermes /home/*/.dsh /home/*/.local/share/opencode; do
  [ -d "$d" ] && echo "DIR $d $(du -sh "$d" 2>/dev/null | cut -f1)"
done
echo "=== opencode storage layout ==="
find /root /home -maxdepth 6 -type d -path "*opencode*" 2>/dev/null | grep -vi node_modules | head -20
echo "=== json/jsonl session-ish files under opencode dirs ==="
find /root/.local/share/opencode /home/*/.local/share/opencode -maxdepth 4 -type d 2>/dev/null | head -20
echo "=== dsh session stores (all homes) ==="
find /root /home -maxdepth 5 -type d -name sessions -path "*dsh*" 2>/dev/null | grep -v node_modules | head -10
echo "=== node process agents ==="
ps -eo pid,etime,cmd 2>/dev/null | grep -Ei "opencode|dsh|hermes" | grep -v grep | head -10
