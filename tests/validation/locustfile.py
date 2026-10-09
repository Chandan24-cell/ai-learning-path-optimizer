from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class LearnerFlow(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.username = f"load_{uuid.uuid4().hex[:24]}"
        self.password = "Validation-Load-Password-2026"
        self.client.headers.update({"X-Load-Test-ID": self.username})
        with self.client.post(
            "/api/auth/register",
            json={"username": self.username, "password": self.password},
            name="POST /api/auth/register",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"register returned {response.status_code}")
                self.auth_ready = False
                return
            self.access_token = response.json()["token"]
            response.success()
        with self.client.put(
            "/api/me/profile",
            headers={"Authorization": f"Bearer {self.access_token}"},
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
            name="PUT /api/me/profile",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"profile returned {response.status_code}")
                self.auth_ready = False
                return
            response.success()
        with self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
            name="POST /api/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login returned {response.status_code}")
                self.auth_ready = False
                return
            self.access_token = response.json()["token"]
            response.success()
        self.auth_ready = True

    @task
    def complete_learning_flow(self) -> None:
        if not getattr(self, "auth_ready", False):
            return
        headers = {"Authorization": f"Bearer {self.access_token}"}
        with self.client.get(
            "/api/recommend?top_k=5",
            headers=headers,
            name="GET /api/recommend",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"recommend returned {response.status_code}")
                return
            recommendations = response.json()["recommendations"]
            action = int(recommendations[0]["action"])
            response.success()

        with self.client.get(
            f"/api/quiz/{action}",
            headers=headers,
            name="GET /api/quiz/{action}",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"quiz returned {response.status_code}")
                return
            answers = [0] * len(response.json()["questions"])
            response.success()

        with self.client.post(
            "/api/interaction",
            headers=headers,
            json={"action": action, "answers": answers, "duration": 1.0},
            name="POST /api/interaction",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"interaction returned {response.status_code}")
                return
            response.success()

        with self.client.get(
            "/api/history?limit=20",
            headers=headers,
            name="GET /api/history",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"history returned {response.status_code}")
                return
            response.success()
