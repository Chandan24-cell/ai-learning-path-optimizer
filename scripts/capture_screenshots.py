"""Capture anonymized local screenshots of onboarding and learning screens."""

from __future__ import annotations

import os
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "docs" / "images"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    with tempfile.TemporaryDirectory(prefix="learning-path-screenshots-") as temp_dir:
        database = Path(temp_dir) / "screenshots.db"
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "development",
                "APP_SECRET": secrets.token_urlsafe(48),
                "DATABASE_URL": f"sqlite:///{database}",
                "ALLOWED_ORIGINS": f"http://127.0.0.1:{port}",
            }
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.content",
                "import",
                str(ROOT / "content" / "mathematics"),
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
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors: list[str] = []
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.on(
                    "response",
                    lambda response: (
                        errors.append(f"HTTP {response.status}: {response.url}")
                        if response.status >= 500
                        else None
                    ),
                )
                page.on("pageerror", lambda error: errors.append(str(error)))
                base_url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if server.poll() is not None:
                        raise RuntimeError("Screenshot server exited before becoming ready")
                    try:
                        if page.request.get(f"{base_url}/health", timeout=500).ok:
                            break
                    except PlaywrightError:
                        time.sleep(0.2)
                else:
                    raise TimeoutError("Screenshot server did not become ready")

                page.goto(base_url, wait_until="networkidle")
                page.screenshot(path=IMAGE_DIR / "sign-in.png", full_page=True)
                page.locator('.tab[data-tab="register"]').click()
                username = "capture_" + secrets.token_hex(8)
                password = secrets.token_urlsafe(18)
                page.locator("#reg-user").fill(username)
                page.locator("#reg-pass").fill(password)
                page.locator("#register-button").click()
                try:
                    page.locator("#app-view").wait_for(state="visible", timeout=10_000)
                except PlaywrightError as exc:
                    raise RuntimeError(
                        "Screenshot account registration failed: "
                        + page.locator("#auth-msg").inner_text()
                    ) from exc
                page.wait_for_timeout(500)
                if page.locator("#auth-view").is_visible():
                    raise RuntimeError(
                        "Screenshot account registration failed: "
                        + page.locator("#auth-msg").inner_text()
                    )
                if errors:
                    raise AssertionError(f"Browser errors after registration: {errors}")
                page.locator("#user-label").evaluate(
                    "element => element.textContent = 'Signed in as learner'"
                )
                onboarding = page.locator("#onboarding-card")
                onboarding.wait_for(state="visible", timeout=10_000)
                page.screenshot(path=IMAGE_DIR / "onboarding.png", full_page=True)
                page.locator("#profile-country").select_option(index=0)
                page.locator("#profile-language").select_option(index=0)
                page.locator("#profile-education-level").select_option(index=0)
                page.locator("#profile-institution-type").select_option(index=0)
                page.locator("#profile-grade-year").fill("Grade 10")
                page.locator("#profile-field").fill("Mathematics")
                page.locator("#profile-goal").select_option(index=0)
                page.locator("#profile-weekly-time").fill("3")
                page.locator("#profile-style").select_option(index=0)
                page.locator("#profile-experience").select_option(index=0)
                page.locator("#profile-consent").check()
                page.locator("#save-profile-button").click()
                onboarding.wait_for(state="hidden", timeout=10_000)
                page.locator("#diagnostic-card").wait_for(state="visible", timeout=30_000)
                page.locator("#start-diagnostic").click()
                questions = page.locator("#quiz-questions .question")
                questions.first.wait_for(timeout=10_000)
                if questions.count() != 6:
                    raise AssertionError("Mathematics diagnostic should contain six questions")
                page.screenshot(path=IMAGE_DIR / "diagnostic.png", full_page=True)
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
                page.locator("#top-rec button[data-action]").wait_for(timeout=30_000)
                page.screenshot(path=IMAGE_DIR / "dashboard.png", full_page=True)
                page.locator("#top-rec button[data-action]").click()
                quiz_questions = page.locator("#quiz-questions .question")
                quiz_questions.first.wait_for(timeout=10_000)
                page.screenshot(path=IMAGE_DIR / "quiz.png", full_page=True)
                for index in range(quiz_questions.count()):
                    page.locator(f'input[name="q{index}"]').first.check()
                page.locator("#submit-activity").click()
                page.locator("#history-table tbody tr").first.wait_for(timeout=15_000)
                browser.close()
                if errors:
                    raise AssertionError(f"Browser console errors: {errors}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
    print(f"Screenshots saved to {IMAGE_DIR}")


if __name__ == "__main__":
    main()
