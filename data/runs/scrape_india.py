"""Background nationwide collection with a final export and durable logs."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[2]
os.chdir(root)
status_path = root / "data/runs/india_status.json"
status = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
try:
    scrape = subprocess.run([
        sys.executable, "-u", "-m", "arogio", "scrape", "hospitals",
        "--state", "all", "--city", "all", "--limit", "100000",
        "--kinds", "hospital,clinic,doctors",
        "--max-minutes", "720", "--local-ai", "--resume",
    ], env=env)
    status["scrape_exit_code"] = scrape.returncode
    export = subprocess.run([
        sys.executable, "-u", "-m", "arogio", "export", "dataset",
        "--output", "data/exports/india_hospitals_local_ai.json",
    ], env=env)
    status["export_exit_code"] = export.returncode
    status["status"] = "finished" if scrape.returncode == export.returncode == 0 else "failed"
except Exception as exc:
    status.update(status="failed", error=str(exc))
finally:
    status["finished_at"] = datetime.now(timezone.utc).isoformat()
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
