import copy
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

from seed_demo import (
    Dataset,
    HttpClient,
    Importer,
    digest,
    encode,
    write_json,
)


class FakeClient(HttpClient):
    def __init__(self, token="phc_example", fail_batch=None, acknowledgement=None):
        self.token = token
        self.fail_batch = fail_batch
        self.acknowledgement = acknowledgement if acknowledgement is not None else {"status": 1}
        self.batches = []
        self.query_result = {"results": []}
        self.identity_result = {"results": []}

    def request(self, url, body=None, bearer=None):
        if "/api/projects/" in url and body is None:
            return {"id": 123, "api_token": self.token}
        if "/query/" in url:
            return self.identity_result if "SELECT distinct_id" in body["query"]["query"] else self.query_result
        self.batches.append(copy.deepcopy(body))
        if len(self.batches) == self.fail_batch:
            raise RuntimeError("simulated interruption")
        return self.acknowledgement


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "dataset"
        self.spec = {
            "seed": "test",
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-01-15T00:00:00+00:00",
            "app_origin": "https://demo.example.com",
        }
        self.session = "019bc150-9c00-7000-8000-000000000001"
        self.person = SimpleNamespace(
            in_product_id="alice",
            name="Demo Person",
            past_events=[
                self.event(
                    "$pageview",
                    "anonymous",
                    {
                        "$current_url": "https://hedgebox.net/files/?sort=old",
                        "$host": "hedgebox.net",
                        "$session_id": self.session,
                        "$feature/old-experiment": "test",
                    },
                ),
                self.event(
                    "$identify",
                    "alice",
                    {"$anon_distinct_id": "anonymous", "$set": {"email": "generated@invalid.test"}},
                ),
                self.event(
                    "$groupidentify",
                    "alice",
                    {
                        "$group_type": "account",
                        "$group_key": "account-a",
                        "$group_set": {"name": "Demo account"},
                        "$groups": {"account": "account-a"},
                    },
                ),
                self.event(
                    "uploaded_file", "alice", {"$groups": {"account": "account-a"}, "$session_id": self.session}
                ),
                self.event("$exception", "alice", {}),
            ],
        )

    @staticmethod
    def event(name, identity, properties):
        return SimpleNamespace(
            event=name, distinct_id=identity, properties=properties, timestamp=dt.datetime(2026, 1, 2, tzinfo=dt.UTC)
        )

    def dataset(self, extra=0):
        self.person.past_events.extend(self.event("uploaded_file", "alice", {}) for _ in range(extra))
        dataset = Dataset.generate([self.person], self.spec, 1000)
        dataset.write(self.directory)
        return Dataset.load(self.directory)

    def test_export_preserves_identity_and_groups_without_unsupported_data(self):
        dataset = self.dataset()
        page, identify, group, upload = dataset.events
        self.assertEqual(identify["properties"]["$anon_distinct_id"], page["distinct_id"])
        self.assertEqual(identify["distinct_id"], upload["distinct_id"])
        self.assertEqual(group["properties"]["$group_key"], upload["properties"]["$groups"]["account"])
        self.assertEqual(page["properties"]["$session_id"], upload["properties"]["$session_id"])
        self.assertNotEqual(page["properties"]["$session_id"], self.session)
        self.assertEqual(page["properties"]["$current_url"], "https://demo.example.com/files/?sort=old")
        self.assertEqual(page["properties"]["$host"], "demo.example.com")
        self.assertNotIn("$feature/old-experiment", page["properties"])
        self.assertTrue(identify["properties"]["$set"]["email"].endswith("@example.com"))
        self.assertEqual(dataset.personas[0]["id"], identify["distinct_id"])
        self.assertEqual(dataset.personas[0]["account_id"], group["properties"]["$group_key"])
        self.assertEqual(
            set(dataset.manifest["counts"]["by_event"]), {"$pageview", "$identify", "$groupidentify", "uploaded_file"}
        )
        again = Dataset.generate([self.person], self.spec, 1000)
        self.assertEqual(dataset.events, again.events)

    def test_excludes_future_events_and_fails_instead_of_truncating(self):
        future = self.event("uploaded_file", "alice", {})
        future.timestamp = dt.datetime(2026, 1, 16, tzinfo=dt.UTC)
        self.person.past_events.append(future)
        self.assertEqual(len(Dataset.generate([self.person], self.spec, 100).events), 4)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            Dataset.generate([self.person], self.spec, 3)

    def test_rejects_corruption_and_does_not_overwrite_artifacts(self):
        dataset = self.dataset()
        with self.assertRaises(FileExistsError):
            dataset.write(self.directory)
        with (self.directory / "events.jsonl").open("ab") as stream:
            stream.write(b"{}\n")
        with self.assertRaisesRegex(ValueError, "checksum"):
            Dataset.load(self.directory)

    def test_rejects_orphan_identity_even_with_valid_checksums(self):
        dataset = self.dataset()
        dataset.events[1]["properties"]["$anon_distinct_id"] = "absent"
        data = b"".join(encode(event) + b"\n" for event in dataset.events)
        (self.directory / "events.jsonl").write_bytes(data)
        dataset.manifest["events_sha256"] = digest(data)
        write_json(self.directory / "manifest.json", dataset.manifest)
        with self.assertRaisesRegex(ValueError, "absent anonymous"):
            Dataset.load(self.directory)

    def test_rejects_mismatched_project_token_before_upload(self):
        dataset = self.dataset()
        client = FakeClient(token="phc_other")
        importer = Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", client)
        with self.assertRaisesRegex(ValueError, "do not match"):
            importer.upload()
        self.assertEqual(client.batches, [])
        self.assertFalse((self.directory / "upload-state.json").exists())

    def test_resume_replays_only_unacknowledged_batches(self):
        dataset = self.dataset(extra=250)
        client = FakeClient(fail_batch=2)
        importer = Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", client)
        with self.assertRaisesRegex(RuntimeError, "interruption"):
            importer.upload()
        state = json.loads((self.directory / "upload-state.json").read_text())
        self.assertEqual(state["next_event"], 200)
        resumed = FakeClient()
        Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", resumed).upload()
        self.assertEqual(resumed.batches[0], client.batches[1])
        self.assertTrue(resumed.batches[0]["historical_migration"])
        state_text = (self.directory / "upload-state.json").read_text()
        self.assertNotIn("phc_example", state_text)
        self.assertNotIn("phx_example", state_text)
        self.assertEqual(json.loads(state_text)["next_event"], 254)
        resumed.batches.clear()
        Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", resumed).upload()
        self.assertEqual(resumed.batches, [])

    def test_rejects_resume_on_changed_target_or_dataset(self):
        dataset = self.dataset()
        Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", FakeClient()).upload(limit=1)
        for region, mutate in [("eu", False), ("us", True)]:
            with self.subTest(region=region, mutate=mutate):
                copy_dataset = copy.deepcopy(dataset)
                if mutate:
                    copy_dataset.manifest["source"] = "changed"
                with self.assertRaisesRegex(ValueError, "another target or dataset"):
                    Importer(
                        copy_dataset, self.directory, 123, region, "phc_example", "phx_example", FakeClient()
                    ).upload()

    def test_does_not_advance_on_rejected_capture_response(self):
        dataset = self.dataset()
        client = FakeClient(acknowledgement={"status": 0})
        with self.assertRaisesRegex(RuntimeError, "did not acknowledge"):
            Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", client).upload()
        self.assertEqual(json.loads((self.directory / "upload-state.json").read_text())["next_event"], 0)

    def test_verification_requires_exact_counts_without_duplicate_uuids(self):
        dataset = self.dataset()
        client = FakeClient()
        importer = Importer(dataset, self.directory, 123, "us", "phc_example", "phx_example", client)
        self.assertFalse(importer.verify())
        client.query_result = {
            "results": [[name, count, count, "", ""] for name, count in dataset.manifest["counts"]["by_event"].items()]
        }
        anonymous = dataset.events[0]["distinct_id"]
        identified = dataset.events[1]["distinct_id"]
        account = dataset.personas[0]["account_id"]
        client.identity_result = {"results": [[anonymous, ["person-one"], []], [identified, ["person-one"], [account]]]}
        self.assertTrue(importer.verify())
        client.identity_result["results"][0][1] = ["different-person"]
        self.assertFalse(importer.verify())
        client.identity_result["results"][0][1] = ["person-one"]
        client.query_result["results"][0][2] = 0
        self.assertFalse(importer.verify())

    def test_http_retries_identical_body_and_hides_error_content(self):
        class Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, timeout):
                self.requests.append(request)
                if len(self.requests) == 1:
                    raise HTTPError(request.full_url, 503, "phc_secret", {}, io.BytesIO(b"phc_secret"))
                return io.BytesIO(b'{"status":1}')

        client = HttpClient(sleep=lambda _: None)
        client.opener = Opener()
        client.request("https://us.i.posthog.com/batch/", {"api_key": "phc_example", "batch": []})
        self.assertEqual(client.opener.requests[0].data, client.opener.requests[1].data)


if __name__ == "__main__":
    unittest.main()
