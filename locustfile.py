from locustfile import HttpUser, between, task


class RoiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task
    def predict(self):
        self.client.post(
            "/v1/predict",
            json={
                "major": "Computer Science",
                "institution_tier": "top_public",
                "region": "west",
                "institution_selectivity_pctile": 80,
                "had_internship": 1,
                "gpa": 3.5,
                "net_cost_usd": 30000
            },
        )
