"""Run the acceptance suite and persist UTF-8 output without PowerShell encoding changes."""
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
result=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=root,capture_output=True)
output=result.stdout.decode('utf-8',errors='replace')+result.stderr.decode('utf-8',errors='replace')
(root/'results').mkdir(exist_ok=True)
(root/'results/test_output.txt').write_text(output,encoding='utf-8')
print(output)
raise SystemExit(result.returncode)
