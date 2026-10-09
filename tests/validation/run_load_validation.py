from __future__ import annotations

import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil
import requests

ROOT = Path(__file__).resolve().parents[2]
LOCUST = Path(sys.executable).with_name("locust")
PASSWORD = "Validation-Load-Password-2026"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(env: dict[str, str], port: int, server_log: Path) -> subprocess.Popen:
    child_env = {**env, "PORT": str(port)}
    with server_log.open("ab") as output:
        return subprocess.Popen(
            [sys.executable, str(ROOT / "tests/validation/load_server.py")],
            cwd=ROOT,
            env=child_env,
            stdout=output,
            stderr=subprocess.STDOUT,
        )


def _wait_ready(base_url: str, server: subprocess.Popen, timeout: float = 90) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("Temporary validation server exited")
        try:
            if requests.get(f"{base_url}/health", timeout=1).ok:
                return
        except requests.RequestException:
            time.sleep(0.2)
    raise TimeoutError("Temporary validation server did not become ready")


def _stop_server(server: subprocess.Popen) -> None:
    server.terminate()
    try:
        server.wait(timeout=8)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=8)


def _read_stats(prefix: Path) -> dict[str, object]:
    stats_path = Path(f"{prefix}_stats.csv")
    rows = list(csv.DictReader(stats_path.open(encoding="utf-8", newline="")))
    total = next((row for row in rows if row["Name"] == "Aggregated"), rows[-1])
    requests_count = int(total["Request Count"])
    failures = int(total["Failure Count"])
    failure_path = Path(f"{prefix}_failures.csv")
    failure_rows = (
        list(csv.DictReader(failure_path.open(encoding="utf-8", newline="")))
        if failure_path.exists()
        else []
    )
    return {
        "requests": requests_count,
        "failures": failures,
        "error_rate_percent": round(100.0 * failures / requests_count, 4)
        if requests_count
        else None,
        "requests_per_second": float(total["Requests/s"]),
        "median_ms": float(total["Median Response Time"]),
        "p95_ms": float(total["95%"]),
        "failure_types": [
            {"error": row["Error"], "occurrences": int(row["Occurrences"])} for row in failure_rows
        ],
        "endpoints": [
            {
                "name": row["Name"],
                "requests": int(row["Request Count"]),
                "failures": int(row["Failure Count"]),
                "requests_per_second": float(row["Requests/s"]),
                "median_ms": float(row["Median Response Time"]),
                "p95_ms": float(row["95%"]),
            }
            for row in rows
            if row["Name"] != "Aggregated" and int(row["Request Count"]) > 0
        ],
    }


def main() -> None:
    duration = int(os.environ.get("VALIDATION_LOAD_SECONDS", "30"))
    if duration < 10:
        raise ValueError("VALIDATION_LOAD_SECONDS must be at least 10")
    users_setting = os.environ.get("VALIDATION_LOAD_USERS")
    restart_50_mid_run = os.environ.get("VALIDATION_RESTART_50", "1").lower() not in {
        "0",
        "false",
        "no",
    }
    load_levels = (
        tuple(int(value) for value in users_setting.split(","))
        if users_setting
        else (
            10,
            50,
            100,
        )
    )
    if not load_levels or any(users not in {10, 50, 100} for users in load_levels):
        raise ValueError("VALIDATION_LOAD_USERS may contain only 10, 50, and 100")
    locust_executable = shutil.which(str(LOCUST)) or shutil.which("locust")
    if not locust_executable:
        raise SystemExit("Locust is not installed in this Python environment")

    results: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="learning-path-load-validation-") as directory:
        temp = Path(directory)
        database = temp / "validation.db"
        port = _port()
        base_url = f"http://127.0.0.1:{port}"
        secret = "load-validation-only-secret-long-enough-2026"
        server_log = temp / "server.log"
        env = {
            **os.environ,
            "APP_ENV": "development",
            "APP_SECRET": secret,
            "DATABASE_URL": f"sqlite:///{database}",
            "ALLOWED_ORIGINS": "",
            "VALIDATION_LOAD_TEST": "1",
        }
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        for pack_path in sorted((ROOT / "content").iterdir()):
            if pack_path.is_dir() and (pack_path / "content.json").exists():
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "app.content",
                        "import",
                        str(pack_path),
                    ],
                    cwd=ROOT,
                    env=env,
                    check=True,
                )

        server = _start_server(env, port, server_log)
        try:
            _wait_ready(base_url, server)
            # First metadata call forces the lazy model load in this server.
            first_request_ms = (
                requests.get(f"{base_url}/api/meta", timeout=90).elapsed.total_seconds() * 1000
            )
            process = psutil.Process(server.pid)
            peak_rss_mb = process.memory_info().rss / (1024 * 1024)
            probe_headers = {"X-Load-Test-ID": "restart-probe"}
            bootstrap = requests.post(
                f"{base_url}/api/auth/register",
                json={"username": "restart_probe", "password": PASSWORD},
                headers=probe_headers,
                timeout=10,
            )
            if bootstrap.status_code != 200:
                raise RuntimeError(f"Restart probe registration failed: {bootstrap.status_code}")
            probe_token = bootstrap.json()["token"]
            profile_response = requests.put(
                f"{base_url}/api/me/profile",
                headers={"Authorization": "Bearer " + probe_token},
                json={
                    "country": "IN",
                    "language": "English",
                    "education_level": "middle_school",
                    "institution_type": "self_study",
                    "grade_year": "Year 7",
                    "curriculum_program": None,
                    "field_of_study": "General studies",
                    "learning_goal": "skill",
                    "weekly_time_hours": 3,
                    "learning_style": "mixed",
                    "prior_experience": "new",
                    "consent": True,
                },
                timeout=10,
            )
            if profile_response.status_code != 200:
                raise RuntimeError(
                    "Restart probe profile failed: "
                    f"{profile_response.status_code} {profile_response.text}"
                )
            seed = requests.post(
                f"{base_url}/api/interaction",
                headers={"Authorization": f"Bearer {probe_token}"},
                json={"action": 0, "answers": [0, 0, 0], "duration": 1.0},
                timeout=30,
            )
            if seed.status_code != 200:
                raise RuntimeError(f"Restart probe history seed failed: {seed.status_code}")

            for users in load_levels:
                run_duration = int(os.environ.get(f"VALIDATION_LOAD_SECONDS_{users}", duration))
                if run_duration < 10:
                    raise ValueError(f"VALIDATION_LOAD_SECONDS_{users} must be at least 10")
                csv_prefix = temp / f"users-{users}"
                command = [
                    locust_executable,
                    "-f",
                    str(ROOT / "tests/validation/locustfile.py"),
                    "--headless",
                    "--host",
                    base_url,
                    "--users",
                    str(users),
                    "--spawn-rate",
                    str(max(2, users // 5)),
                    "--run-time",
                    f"{run_duration}s",
                    "--csv",
                    str(csv_prefix),
                    "--loglevel",
                    "INFO",
                ]
                log_path = temp / f"users-{users}.log"
                run = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=log_path.open("w", encoding="utf-8"),
                    stderr=subprocess.STDOUT,
                )
                restarted = False
                deadline = time.monotonic() + run_duration
                restart_at = time.monotonic() + run_duration / 2
                while run.poll() is None and time.monotonic() < deadline + 60:
                    try:
                        peak_rss_mb = max(
                            peak_rss_mb,
                            process.memory_info().rss / (1024 * 1024),
                        )
                    except psutil.Error:
                        pass
                    if (
                        users == 50
                        and restart_50_mid_run
                        and not restarted
                        and time.monotonic() >= restart_at
                    ):
                        _stop_server(server)
                        time.sleep(1.0)
                        server = _start_server(env, port, server_log)
                        _wait_ready(base_url, server)
                        process = psutil.Process(server.pid)
                        restarted = True
                    time.sleep(0.2)
                if run.poll() is None:
                    run.terminate()
                    run.wait(timeout=10)
                results[str(users)] = {
                    **_read_stats(csv_prefix),
                    "duration_seconds": run_duration,
                    "locust_exit_code": run.returncode,
                    "server_restarted_mid_run": restarted,
                }

                # Confirm a new login and saved history still work after the
                # 50-user run's forced server restart.
                if users == 50 and restarted:
                    login = requests.post(
                        f"{base_url}/api/auth/login",
                        json={"username": "restart_probe", "password": PASSWORD},
                        headers=probe_headers,
                        timeout=10,
                    )
                    history_count = None
                    if login.status_code == 200:
                        history = requests.get(
                            f"{base_url}/api/history?limit=20",
                            headers={
                                "Authorization": f"Bearer {login.json()['token']}",
                            },
                            timeout=10,
                        )
                        if history.status_code == 200:
                            history_count = len(history.json()["history"])
                    results["restart_data_check"] = {
                        "login_status": login.status_code,
                        "history_status": history.status_code if login.status_code == 200 else None,
                        "history_count": history_count,
                    }
            meta_mode = requests.get(f"{base_url}/api/meta", timeout=60).json()
            results["first_model_metadata_request_ms"] = round(first_request_ms, 3)
            results["peak_server_rss_mb"] = round(peak_rss_mb, 3)
            results["recommender_mode"] = meta_mode["recommender_mode"]
        finally:
            _stop_server(server)
        server_log_text = server_log.read_text(encoding="utf-8", errors="replace")
        locked_lines = [
            line for line in server_log_text.splitlines() if "database is locked" in line.lower()
        ]
        results["sqlite_database_locked_log_lines"] = len(locked_lines)
        server_log_lines = server_log_text.splitlines()
        error_indexes = [
            index for index, line in enumerate(server_log_lines) if "Exception in ASGI" in line
        ]
        error_blocks = []
        for position, index in enumerate(error_indexes):
            next_index = (
                error_indexes[position + 1]
                if position + 1 < len(error_indexes)
                else len(server_log_lines)
            )
            block = server_log_lines[index:next_index]
            error_blocks.append(block[-45:])
        results["server_error_log_excerpts"] = error_blocks[-2:]
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
