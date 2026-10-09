from __future__ import annotations

import json
import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.3/axe.min.js"


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _download_axe(destination: Path) -> str | None:
    try:
        with urllib.request.urlopen(AXE_URL, timeout=20) as response:
            destination.write_bytes(response.read())
        return None
    except OSError as exc:
        return f"Could not download axe-core: {type(exc).__name__}: {exc}"


def _axe_violations(page, axe_path: Path, base_url: str) -> list[dict[str, object]] | None:
    page.route(
        "**/validation-axe.js",
        lambda route: route.fulfill(path=str(axe_path), content_type="application/javascript"),
    )
    page.add_script_tag(url=f"{base_url}/validation-axe.js")
    result = page.evaluate(
        """async () => {
          const report = await axe.run(document);
          return report.violations.map(item => ({
            id: item.id,
            impact: item.impact,
            description: item.description,
            nodes: item.nodes.length,
            examples: item.nodes.slice(0, 3).map(node => ({
              target: node.target,
              summary: node.failureSummary
            }))
          }));
        }"""
    )
    return result


def main() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    port = _port()
    password = secrets.token_urlsafe(18) + "Aa1!"
    with tempfile.TemporaryDirectory(prefix="learning-path-browser-validation-") as directory:
        temp = Path(directory)
        database = temp / "browser.db"
        env = {
            **os.environ,
            "APP_ENV": "development",
            "APP_SECRET": secrets.token_urlsafe(48),
            "DATABASE_URL": f"sqlite:///{database}",
            "ALLOWED_ORIGINS": "",
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
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        report: dict[str, object] = {"screenshots": {}, "axe": {}, "failure_modes": {}}
        axe_path = temp / "axe.min.js"
        report["axe_download_issue"] = _download_axe(axe_path)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text) if message.type == "error" else None
                    ),
                )
                base_url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError("Validation server exited before becoming ready")
                    try:
                        if page.request.get(f"{base_url}/health", timeout=500).ok:
                            break
                    except PlaywrightError:
                        time.sleep(0.2)
                else:
                    raise TimeoutError("Browser validation server did not become ready")

                readiness_started = time.monotonic()
                readiness = page.request.get(f"{base_url}/ready", timeout=120_000)
                report["first_model_readiness"] = {
                    "seconds": round(time.monotonic() - readiness_started, 3),
                    "status": readiness.status,
                    "body": readiness.json() if readiness.ok else readiness.text(),
                }
                if not readiness.ok:
                    raise RuntimeError(f"Readiness check failed: {readiness.text()}")

                page.goto(base_url, wait_until="networkidle")
                if report["axe_download_issue"] is None:
                    report["axe"]["sign_in"] = _axe_violations(page, axe_path, base_url)

                page.locator('.tab[data-tab="register"]').click()
                page.locator("#reg-user").fill("validation_browser")
                page.locator("#reg-pass").fill(password)
                page.locator("#register-button").click()
                try:
                    page.locator("#app-view").wait_for(state="visible", timeout=10_000)
                except PlaywrightError as exc:
                    raise RuntimeError(
                        "Browser validation registration failed: "
                        f"{page.locator('#auth-msg').inner_text()!r}; "
                        f"console_errors={errors!r}"
                    ) from exc
                page.locator("#profile-education-level").select_option("middle_school")
                page.locator("#profile-institution-type").select_option("self_study")
                page.locator("#profile-grade-year").fill("Year 7")
                page.locator("#profile-field").fill("General studies")
                page.locator("#profile-weekly-time").fill("3")
                page.locator("#profile-consent").check()
                page.locator("#save-profile-button").click()
                page.locator("#onboarding-card").wait_for(state="hidden", timeout=10_000)
                page.locator("#diagnostic-card").wait_for(state="visible", timeout=10_000)
                page.locator("#start-diagnostic").click()
                questions = page.locator("#quiz-questions .question")
                questions.first.wait_for(timeout=10_000)
                with sqlite3.connect(database) as connection:
                    correct_options = dict(
                        connection.execute(
                            "SELECT id, correct_option FROM questions WHERE diagnostic = 1"
                        )
                    )
                for index in range(questions.count()):
                    question_id = questions.nth(index).get_attribute("data-question-id")
                    if question_id not in correct_options:
                        raise AssertionError(f"Missing diagnostic answer for {question_id!r}")
                    page.locator(f'input[name="q{index}"]').nth(
                        correct_options[question_id]
                    ).check()
                page.locator("#submit-activity").click()
                page.locator("#diagnostic-card").wait_for(state="hidden", timeout=10_000)
                try:
                    page.locator("#top-rec button[data-action]").wait_for(timeout=10_000)
                except PlaywrightError as exc:
                    token = page.evaluate("localStorage.getItem('token')")
                    response = page.request.get(
                        f"{base_url}/api/subjects/mathematics/recommendations",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    raise RuntimeError(
                        "Registration did not reach recommendations: "
                        f"auth={page.locator('#auth-msg').inner_text()!r}, "
                        f"subject={page.locator('#subject-message').inner_text()!r}, "
                        f"dashboard={page.locator('#top-rec').inner_text()!r}, "
                        f"modal={page.locator('#modal-msg').inner_text()!r}, "
                        f"api={response.status} {response.text()!r}, "
                        f"console_errors={errors!r}"
                    ) from exc

                for name, width, height in (
                    ("phone", 390, 844),
                    ("tablet", 768, 1024),
                    ("desktop", 1440, 1000),
                ):
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(250)
                    dimensions = page.evaluate(
                        """() => ({
                          viewport: document.documentElement.clientWidth,
                          document: document.documentElement.scrollWidth,
                          body: document.body.scrollWidth
                        })"""
                    )
                    report["screenshots"][name] = {
                        "file": f"screenshots/{name}-dashboard.png",
                        "width": width,
                        "height": height,
                        "document_width": dimensions["document"],
                        "horizontal_overflow_px": max(
                            0, dimensions["document"] - dimensions["viewport"]
                        ),
                    }
                    page.screenshot(
                        path=str(SCREENSHOT_DIR / f"{name}-dashboard.png"), full_page=True
                    )

                if report["axe_download_issue"] is None:
                    report["axe"]["dashboard"] = _axe_violations(page, axe_path, base_url)

                page.locator("#top-rec button[data-action]").click()
                page.locator("#quiz-questions .question").first.wait_for(timeout=10_000)
                if report["axe_download_issue"] is None:
                    report["axe"]["quiz"] = _axe_violations(page, axe_path, base_url)
                page.screenshot(path=str(SCREENSHOT_DIR / "desktop-quiz.png"), full_page=True)
                page.locator("#cancel-activity").click()

                slow_started = time.monotonic()

                def delay_api(route) -> None:
                    time.sleep(0.75)
                    route.continue_()

                page.route("**/api/**", delay_api)
                page.reload(wait_until="networkidle", timeout=30_000)
                report["failure_modes"]["slow_api_reload_seconds"] = round(
                    time.monotonic() - slow_started, 3
                )
                page.unroute("**/api/**", delay_api)

                page.route(
                    "**/api/subjects/*/recommendations**",
                    lambda route: route.abort(),
                )
                page.reload(wait_until="networkidle")
                report["failure_modes"]["recommendation_api_failure"] = {
                    "top_recommendation_text": page.locator("#top-rec").inner_text(),
                    "visible_error_messages": page.locator('[role="alert"]').all_inner_texts(),
                }
                page.unroute("**/api/subjects/*/recommendations**")

                page.route("**/static/chart.umd.min.js", lambda route: route.abort())
                page.reload(wait_until="networkidle")
                report["failure_modes"]["chart_asset_failure"] = {
                    "page_errors": errors[-5:],
                    "chart_canvas_present": page.locator("#mastery-chart").count() > 0,
                    "chart_status_text": page.locator("#chart-status").inner_text(),
                    "top_recommendation_text": page.locator("#top-rec").inner_text(),
                }
                page.unroute("**/static/chart.umd.min.js")
                report["browser_console_errors"] = errors
                browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=8)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
