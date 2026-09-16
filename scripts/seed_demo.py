from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Protocol, TypeAlias, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
Record: TypeAlias = dict[str, Json]
SUPPORTED = frozenset(
    {
        "$pageview",
        "$pageleave",
        "$autocapture",
        "$identify",
        "$groupidentify",
        "signed_up",
        "logged_in",
        "logged_out",
        "uploaded_file",
        "downloaded_file",
        "deleted_file",
        "shared_file_link",
    }
)
REGIONS = {
    "us": ("https://us.i.posthog.com", "https://us.posthog.com"),
    "eu": ("https://eu.i.posthog.com", "https://eu.posthog.com"),
}
SCHEMA_VERSION = 1
MAX_BATCH_BYTES = 1_000_000


def object_value(value: Json) -> Record:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def string_value(value: Json) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a nonempty string")
    return value


def encode(value: Json) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def timestamp(value: str) -> dt.datetime:
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() != dt.timedelta():
        raise ValueError("Use an explicit UTC timestamp, for example 2026-09-16T12:00:00Z")
    return result


def app_origin(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("App origin must be an http(s) URL without credentials")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("App origin must not include a path, query, or fragment")
    return f"{parts.scheme}://{parts.netloc}"


def write_json(path: Path, value: Json) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encode(value) + b"\n")
    temporary.replace(path)


class SimEvent(Protocol):
    event: str
    distinct_id: str
    timestamp: dt.datetime
    properties: Record


class SimPerson(Protocol):
    in_product_id: str
    name: str
    past_events: list[SimEvent]


class MatrixSource:
    def __init__(self, checkout: Path) -> None:
        self.checkout = checkout.resolve()
        self.logic = self.checkout / "products/demo/backend/logic"
        if not self.logic.is_dir():
            raise ValueError("PostHog checkout does not contain products/demo/backend/logic")

    def revision(self) -> Record:
        revision = subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], text=True).strip()
        fingerprint = hashlib.sha256()
        for file in sorted(self.logic.rglob("*.py")):
            fingerprint.update(str(file.relative_to(self.logic)).encode())
            fingerprint.update(file.read_bytes())
        return {"revision": revision, "matrix_sha256": fingerprint.hexdigest()}

    @staticmethod
    def reject_database_access(*args: object, **kwargs: object) -> object:
        raise RuntimeError("Matrix export must not read or write a database")

    def simulate(self, seed: str, end: dt.datetime, days: int, clusters: int) -> list[SimPerson]:
        sys.path.insert(0, str(self.checkout))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "posthog.settings")
        os.environ["TEST"] = "1"
        os.environ["OPT_OUT_CAPTURE"] = "1"
        django = importlib.import_module("django")
        connections = importlib.import_module("django.db").connections
        with ExitStack() as stack:
            for connection in connections.all():
                stack.enter_context(connection.execute_wrapper(self.reject_database_access))
            django.setup()
            matrix_class = importlib.import_module(
                "products.demo.backend.logic.products.hedgebox.matrix"
            ).HedgeboxMatrix
            matrix = matrix_class(seed, now=end, days_past=days, days_future=0, n_clusters=clusters)
            matrix.simulate()
            return cast(list[SimPerson], matrix.people)


class EventConverter:
    def __init__(self, seed_id: str, origin: str) -> None:
        self.seed_id = seed_id
        self.origin = app_origin(origin)
        self.host = urlsplit(origin).netloc

    def identity(self, kind: str, value: str) -> str:
        suffix = uuid.uuid5(uuid.NAMESPACE_URL, f"{self.seed_id}:{kind}:{value}").hex[:20]
        return f"hb-{self.seed_id}-{kind}-{suffix}"

    def session(self, value: str) -> str:
        original = uuid.UUID(value)
        if original.version != 7:
            raise ValueError("Matrix session IDs must be UUIDv7")
        salted = uuid.uuid5(uuid.NAMESPACE_URL, f"{self.seed_id}:session:{value}").int
        result = (original.int >> 80 << 80) | (7 << 76) | (salted & ((1 << 76) - 1))
        result = (result & ~(3 << 62)) | (2 << 62)
        return str(uuid.UUID(int=result))

    def normalize(self, value: Json, user_id: str, key: str = "") -> Json:
        if isinstance(value, dict):
            return {
                child: self.normalize(item, user_id, child)
                for child, item in value.items()
                if not child.startswith("$feature/")
                and child not in {"$active_feature_flags", "$group_0", "$group_1", "$group_2", "$group_3", "$group_4"}
            }
        if isinstance(value, list):
            return [self.normalize(item, user_id) for item in value]
        if isinstance(value, str):
            if key == "email":
                return f"{user_id}@example.com"
            if key in {"$referring_domain", "$initial_referring_domain"} and value == "hedgebox.net":
                return self.host
            if key in {"$device_id", "$anon_distinct_id", "$user_id", "distinct_id"}:
                return self.identity("user", value)
            if key in {"$session_id", "$window_id"}:
                return self.session(value)
            if key in {"$host", "$initial_host"} and value == "hedgebox.net":
                return self.host
            parts = urlsplit(value) if value.startswith(("https://", "http://")) else None
            if parts and parts.hostname == "hedgebox.net":
                target = urlsplit(self.origin)
                return urlunsplit((target.scheme, target.netloc, parts.path, parts.query, parts.fragment))
        return value

    def convert(self, person: SimPerson, event: SimEvent, ordinal: int) -> Record:
        user_id = self.identity("user", person.in_product_id)
        properties = object_value(self.normalize(event.properties, user_id))
        if "$groups" in properties:
            properties["$groups"] = {
                group: self.identity("account", string_value(key))
                for group, key in object_value(properties["$groups"]).items()
            }
        if event.event == "$groupidentify":
            properties["$group_key"] = self.identity("account", string_value(properties["$group_key"]))
        properties["demo_seed_id"] = self.seed_id
        properties["demo_synthetic"] = True
        properties["$geoip_disable"] = True
        properties["$process_person_profile"] = True
        if event.event == "$identify":
            traits = object_value(properties.get("$set", {}))
            traits.update({"email": f"{user_id}@example.com", "name": person.name, "demo_seed_id": self.seed_id})
            properties["$set"] = traits
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.seed_id}:{person.in_product_id}:{ordinal}"))
        return {
            "event": event.event,
            "distinct_id": self.identity("user", event.distinct_id),
            "timestamp": event.timestamp.astimezone(dt.UTC).isoformat(),
            "uuid": event_id,
            "properties": properties,
        }


class Dataset:
    def __init__(self, manifest: Record, events: list[Record], personas: list[Record]) -> None:
        self.manifest = manifest
        self.events = events
        self.personas = personas

    @staticmethod
    def counts(events: list[Record]) -> Record:
        distribution = Counter(string_value(event["event"]) for event in events)
        sessions = {object_value(event["properties"]).get("$session_id") for event in events} - {None}
        groups = {
            value
            for event in events
            for value in object_value(object_value(event["properties"]).get("$groups", {})).values()
        }
        users = {event["distinct_id"] for event in events if event["event"] == "$identify"}
        return {
            "events": len(events),
            "identified_users": len(users),
            "accounts": len(groups),
            "sessions": len(sessions),
            "by_event": dict(sorted(distribution.items())),
        }

    @classmethod
    def generate(cls, people: Iterable[SimPerson], spec: Record, max_events: int) -> Dataset:
        seed_id = digest(encode(spec))[:20]
        converter = EventConverter(seed_id, string_value(spec["app_origin"]))
        start = timestamp(string_value(spec["start"]))
        end = timestamp(string_value(spec["end"]))
        events: list[Record] = []
        personas: list[Record] = []
        for person in people:
            person_events = [
                converter.convert(person, event, ordinal)
                for ordinal, event in enumerate(person.past_events)
                if event.event in SUPPORTED and start <= event.timestamp <= end
            ]
            events.extend(person_events)
            if len(events) > max_events:
                raise ValueError(f"Dataset exceeds {max_events} events; use fewer clusters or days. No files written.")
            user_id = converter.identity("user", person.in_product_id)
            identified = any(
                event["event"] == "$identify" and event["distinct_id"] == user_id for event in person_events
            )
            accounts = [
                object_value(object_value(event["properties"]).get("$groups", {})).get("account")
                for event in person_events
            ]
            account_id = next((account for account in reversed(accounts) if account), None)
            if identified and account_id:
                plan = "personal/free"
                for event in person_events:
                    properties = object_value(event["properties"])
                    if event["event"] == "$groupidentify" and properties.get("$group_key") == account_id:
                        plan = str(object_value(properties.get("$group_set", {})).get("plan", plan))
                personas.append(
                    {
                        "id": user_id,
                        "name": person.name,
                        "email": f"{user_id}@example.com",
                        "account_id": account_id,
                        "demo_seed_id": seed_id,
                        "plan": plan,
                    }
                )
        events.sort(key=lambda event: string_value(event["timestamp"]))
        if not events or not personas:
            raise ValueError("Simulation produced no usable demo personas; increase clusters or days")
        manifest: Record = {
            "schema_version": SCHEMA_VERSION,
            "demo_seed_id": seed_id,
            "spec": spec,
            "counts": cls.counts(events),
        }
        return cls(manifest, events, sorted(personas, key=lambda person: string_value(person["id"])))

    def write(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=False)
        event_bytes = b"".join(encode(event) + b"\n" for event in self.events)
        persona_bytes = encode(cast(Json, self.personas)) + b"\n"
        self.manifest["events_sha256"] = digest(event_bytes)
        self.manifest["personas_sha256"] = digest(persona_bytes)
        (directory / "events.jsonl").write_bytes(event_bytes)
        (directory / "personas.json").write_bytes(persona_bytes)
        write_json(directory / "manifest.json", self.manifest)

    @classmethod
    def load(cls, directory: Path) -> Dataset:
        manifest = object_value(json.loads((directory / "manifest.json").read_bytes()))
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported dataset schema")
        event_bytes = (directory / "events.jsonl").read_bytes()
        persona_bytes = (directory / "personas.json").read_bytes()
        if digest(event_bytes) != manifest.get("events_sha256") or digest(persona_bytes) != manifest.get(
            "personas_sha256"
        ):
            raise ValueError("Dataset checksum mismatch; regenerate instead of editing seed files")
        events = [object_value(json.loads(line)) for line in event_bytes.splitlines() if line]
        raw_personas = json.loads(persona_bytes)
        if not isinstance(raw_personas, list):
            raise ValueError("Expected a persona array")
        personas = [object_value(persona) for persona in raw_personas]
        spec = object_value(manifest["spec"])
        seed_id = string_value(manifest["demo_seed_id"])
        if seed_id != digest(encode(spec))[:20]:
            raise ValueError("Dataset identity does not match generation options")
        start, end = timestamp(string_value(spec["start"])), timestamp(string_value(spec["end"]))
        app_origin(string_value(spec["app_origin"]))
        if not start < end <= dt.datetime.now(dt.UTC):
            raise ValueError("Dataset must contain only historical timestamps")
        previous = start
        identifiers: set[str] = set()
        distinct_ids: set[str] = set()
        declared_groups: set[str] = set()
        referenced_groups: set[str] = set()
        for event in events:
            event_time = timestamp(string_value(event["timestamp"]))
            if not previous <= event_time <= end or event.get("event") not in SUPPORTED:
                raise ValueError("Unsupported event or out-of-order/out-of-range timestamp")
            previous = event_time
            identifier = string_value(event["uuid"])
            uuid.UUID(identifier)
            if identifier in identifiers:
                raise ValueError("Duplicate event UUID")
            identifiers.add(identifier)
            user_id = string_value(event["distinct_id"])
            if not user_id.startswith(f"hb-{seed_id}-user-"):
                raise ValueError("Event identity is outside the dataset namespace")
            distinct_ids.add(user_id)
            props = object_value(event["properties"])
            if props.get("demo_seed_id") != seed_id or props.get("demo_synthetic") is not True:
                raise ValueError("Event is missing its synthetic dataset marker")
            if props.get("$session_id") and uuid.UUID(string_value(props["$session_id"])).version != 7:
                raise ValueError("Invalid session ID")
            for group in object_value(props.get("$groups", {})).values():
                if not string_value(group).startswith(f"hb-{seed_id}-account-"):
                    raise ValueError("Account identity is outside the dataset namespace")
                referenced_groups.add(string_value(group))
            if event["event"] == "$groupidentify":
                if props.get("$group_type") != "account":
                    raise ValueError("Only account groups are supported")
                group_key = string_value(props["$group_key"])
                if not group_key.startswith(f"hb-{seed_id}-account-"):
                    raise ValueError("Account identity is outside the dataset namespace")
                declared_groups.add(group_key)
        if not referenced_groups <= declared_groups:
            raise ValueError("Events reference an account without a group identify record")
        if not events or cls.counts(events) != manifest["counts"]:
            raise ValueError("Manifest counts do not match events")
        for event in events:
            anon = object_value(event["properties"]).get("$anon_distinct_id")
            if anon is not None and anon not in distinct_ids:
                raise ValueError("Identify event references an absent anonymous identity")
        for persona in personas:
            if persona["id"] not in distinct_ids or persona["demo_seed_id"] != seed_id:
                raise ValueError("Persona does not belong to this dataset")
            if persona["email"] != f"{persona['id']}@example.com":
                raise ValueError("Persona email must use the generated example.com address")
            if persona["account_id"] not in declared_groups:
                raise ValueError("Persona account does not belong to this dataset")
            if persona.get("plan") not in {"personal/free", "personal/pro", "business/standard", "business/enterprise"}:
                raise ValueError("Persona has an unsupported plan")
        return cls(manifest, events, personas)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


class HttpClient:
    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self.opener = build_opener(NoRedirects())
        self.sleep = sleep

    def request(self, url: str, body: Record | None = None, bearer: str | None = None) -> Json:
        payload = encode(body) if body is not None else None
        headers = {"Content-Type": "application/json", "User-Agent": "hedgebox-demo-seeder/1"}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        for attempt in range(4):
            try:
                request = Request(url, data=payload, headers=headers, method="POST" if body is not None else "GET")
                with self.opener.open(request, timeout=30) as response:
                    raw = response.read()
                return json.loads(raw)
            except HTTPError as error:
                if error.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(
                        f"HTTP {error.code} from {urlsplit(url).hostname}; response body omitted"
                    ) from None
                retry_after = error.headers.get("Retry-After", "")
                delay = min(float(retry_after), 30) if retry_after.isdigit() else 2**attempt
            except (URLError, TimeoutError, ConnectionError):
                if attempt == 3:
                    raise RuntimeError(
                        f"Network failure contacting {urlsplit(url).hostname}; retry with the same dataset"
                    ) from None
                delay = 2**attempt
            self.sleep(delay)
        raise RuntimeError("Request attempts exhausted")


class Importer:
    def __init__(
        self,
        dataset: Dataset,
        directory: Path,
        project_id: int,
        region: str,
        token: str,
        personal_key: str,
        client: HttpClient | None = None,
    ) -> None:
        if project_id < 1 or region not in REGIONS or not token or not personal_key:
            raise ValueError("Upload/verification requires a project ID, region, ingestion token, and personal API key")
        self.dataset, self.directory, self.project_id = dataset, directory, project_id
        self.ingest, self.api = REGIONS[region]
        self.token, self.personal_key = token, personal_key
        self.client = client or HttpClient()
        self.binding: Record = {
            "project_id": project_id,
            "region": region,
            "token_sha256": digest(token.encode()),
            "manifest_sha256": digest(encode(dataset.manifest)),
        }

    def validate_target(self) -> None:
        project = object_value(
            self.client.request(f"{self.api}/api/projects/{self.project_id}/", bearer=self.personal_key)
        )
        if project.get("id") != self.project_id or project.get("api_token") != self.token:
            raise ValueError("Project ID and ingestion token do not match; nothing uploaded")

    def payload(self, events: list[Record]) -> Record:
        return {"api_key": self.token, "historical_migration": True, "batch": cast(Json, events)}

    def upload(self, limit: int | None = None) -> None:
        with (self.directory / "upload.lock").open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Another uploader is using this dataset") from None
            self._upload(limit)

    def _upload(self, limit: int | None = None) -> None:
        self.validate_target()
        state_path = self.directory / "upload-state.json"
        next_event = 0
        if state_path.exists():
            state = object_value(json.loads(state_path.read_bytes()))
            if state.get("binding") != self.binding:
                raise ValueError("Upload state belongs to another target or dataset")
            value = state.get("next_event")
            if type(value) is not int or not 0 <= value <= len(self.dataset.events):
                raise ValueError("Invalid upload cursor")
            next_event = value
        write_json(state_path, {"binding": self.binding, "next_event": next_event})
        stop = len(self.dataset.events) if limit is None else min(len(self.dataset.events), next_event + limit)
        while next_event < stop:
            end = min(next_event + 200, stop)
            batch = self.dataset.events[next_event:end]
            while len(encode(self.payload(batch))) > MAX_BATCH_BYTES and len(batch) > 1:
                batch = batch[: len(batch) // 2]
            if len(encode(self.payload(batch))) > MAX_BATCH_BYTES:
                raise ValueError("A single event exceeds the upload size cap")
            response = self.client.request(f"{self.ingest}/batch/", self.payload(batch))
            if response != 1 and (not isinstance(response, dict) or response.get("status") != 1):
                raise RuntimeError("Capture did not acknowledge the batch; progress was not advanced")
            next_event += len(batch)
            write_json(state_path, {"binding": self.binding, "next_event": next_event})
            print(f"Accepted {next_event}/{len(self.dataset.events)} events")
        print("Upload checkpoint saved. Run verify after ingestion has processed the accepted events.")

    def verify(self) -> bool:
        self.validate_target()
        seed_id = string_value(self.dataset.manifest["demo_seed_id"])
        if not re.fullmatch("[0-9a-f]{20}", seed_id):
            raise ValueError("Invalid dataset ID")
        spec = object_value(self.dataset.manifest["spec"])
        start = timestamp(string_value(spec["start"])).strftime("%Y-%m-%d %H:%M:%S")
        end = (timestamp(string_value(spec["end"])) + dt.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        conditions = (
            f"timestamp >= toDateTime('{start}', 'UTC') AND timestamp <= toDateTime('{end}', 'UTC') "
            f"AND properties.demo_seed_id = '{seed_id}' AND properties.demo_synthetic = true"
        )
        query = (
            "SELECT event, count(), uniqExact(uuid), min(timestamp), max(timestamp) FROM events "
            f"WHERE {conditions} GROUP BY event"
        )
        result = object_value(
            self.client.request(
                f"{self.api}/api/projects/{self.project_id}/query/",
                {"query": {"kind": "HogQLQuery", "query": query}},
                self.personal_key,
            )
        )
        rows = result.get("results")
        if not isinstance(rows, list):
            raise RuntimeError("Query returned no synchronous results; retry verify later")
        actual: Record = {}
        duplicates = False
        for row in rows:
            if not isinstance(row, list) or len(row) < 5:
                raise RuntimeError("Unexpected verification response")
            actual[string_value(row[0])] = row[1]
            duplicates |= row[1] != row[2]
        expected = object_value(self.dataset.manifest["counts"])["by_event"]
        identities = object_value(
            self.client.request(
                f"{self.api}/api/projects/{self.project_id}/query/",
                {
                    "query": {
                        "kind": "HogQLQuery",
                        "query": "SELECT distinct_id, groupUniqArray(toString(person.id)), "
                        f"groupUniqArray(properties.$groups.account) FROM events WHERE {conditions} "
                        f"GROUP BY distinct_id LIMIT {len(self.dataset.events) + 1}",
                    }
                },
                self.personal_key,
            )
        ).get("results")
        expected_accounts: dict[str, set[str]] = {}
        aliases: list[tuple[str, str]] = []
        for event in self.dataset.events:
            identity = string_value(event["distinct_id"])
            expected_accounts.setdefault(identity, set())
            props = object_value(event["properties"])
            account = object_value(props.get("$groups", {})).get("account")
            if account:
                expected_accounts[identity].add(string_value(account))
            if props.get("$anon_distinct_id"):
                aliases.append((string_value(props["$anon_distinct_id"]), identity))
        persons: dict[str, str] = {}
        accounts: dict[str, set[str]] = {}
        if isinstance(identities, list):
            for row in identities:
                if (
                    not isinstance(row, list)
                    or len(row) != 3
                    or not isinstance(row[1], list)
                    or not isinstance(row[2], list)
                ):
                    raise RuntimeError("Unexpected identity verification response")
                identity = string_value(row[0])
                if len(row[1]) == 1 and row[1][0]:
                    persons[identity] = string_value(row[1][0])
                accounts[identity] = {string_value(value) for value in row[2] if value}
        identity_check = set(persons) == set(expected_accounts) and all(
            persons.get(anonymous) == persons.get(identified) for anonymous, identified in aliases
        )
        account_check = accounts == expected_accounts
        verified = actual == expected and not duplicates and identity_check and account_check
        report: Record = {
            "binding": self.binding,
            "verified": verified,
            "expected": expected,
            "actual": actual,
            "identities_verified": identity_check,
            "accounts_verified": account_check,
        }
        write_json(self.directory / "verification.json", report)
        print(json.dumps(report, indent=2))
        return verified


def load_environment(file: Path | None) -> Mapping[str, str]:
    values: dict[str, str] = {}
    if file:
        for line in file.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not re.fullmatch("[A-Z_][A-Z_0-9]*", key.strip()):
                raise ValueError("Environment file must contain simple KEY=value lines")
            values[key.strip()] = value.strip().strip("\"'")
    values.update(os.environ)
    return values


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Hedgebox history; upload only with an explicit command."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--posthog-repo", type=Path, required=True)
    generate.add_argument("--app-origin", type=app_origin, required=True)
    generate.add_argument("--end", type=timestamp, required=True)
    generate.add_argument("--seed", default="hedgebox-demo-v1")
    generate.add_argument("--days", type=positive, default=14)
    generate.add_argument("--clusters", type=positive, default=20)
    generate.add_argument("--max-events", type=positive, default=20_000)
    generate.add_argument("--output", type=Path, default=Path(".seed/demo"))
    validate = commands.add_parser("validate")
    validate.add_argument("--input", type=Path, default=Path(".seed/demo"))
    personas = commands.add_parser("export-personas")
    personas.add_argument("--input", type=Path, default=Path(".seed/demo"))
    personas.add_argument("--output", type=Path, default=Path("public/demo-personas.json"))
    personas.add_argument("--limit", type=positive, default=5)
    for command in ("upload", "verify"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--input", type=Path, default=Path(".seed/demo"))
        subparser.add_argument("--project-id", type=positive, required=True)
        subparser.add_argument("--region", choices=REGIONS, required=True)
        subparser.add_argument("--env-file", type=Path)
        if command == "upload":
            subparser.add_argument(
                "--limit", type=positive, help="Accept at most this many additional events, then checkpoint"
            )
    args = parser.parse_args()
    try:
        if args.command == "generate":
            if args.output.exists():
                raise ValueError("Output directory already exists; choose a new directory to preserve resume state")
            if args.end > dt.datetime.now(dt.UTC) or args.days > 90 or args.clusters > 25:
                raise ValueError("Use a past end time, at most 90 days, and at most 25 clusters")
            if os.environ.get("PYTHONHASHSEED") != "0":
                os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
            source = MatrixSource(args.posthog_repo)
            start = (args.end - dt.timedelta(days=args.days)).replace(hour=0, minute=0, second=0, microsecond=0)
            spec: Record = {
                "seed": args.seed,
                "start": start.isoformat(),
                "end": args.end.isoformat(),
                "days": args.days,
                "clusters": args.clusters,
                "app_origin": args.app_origin,
                "source": source.revision(),
                "converter_version": SCHEMA_VERSION,
                "converter_sha256": digest(Path(__file__).read_bytes()),
            }
            people = source.simulate(args.seed, args.end, args.days, args.clusters)
            dataset = Dataset.generate(people, spec, args.max_events)
            dataset.write(args.output)
            Dataset.load(args.output)
            print(json.dumps(dataset.manifest, indent=2))
            print(f"Generated locally in {args.output}. Nothing uploaded.")
            return 0
        dataset = Dataset.load(args.input)
        if args.command == "export-personas":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, cast(Json, dataset.personas[: args.limit]))
            print(f"Exported {min(args.limit, len(dataset.personas))} synthetic personas to {args.output}")
            return 0
        if args.command == "validate":
            print(json.dumps(dataset.manifest, indent=2))
            return 0
        environment = load_environment(args.env_file)
        importer = Importer(
            dataset,
            args.input,
            args.project_id,
            args.region,
            environment.get("NEXT_PUBLIC_POSTHOG_KEY", ""),
            environment.get("POSTHOG_PERSONAL_API_KEY", ""),
        )
        print(
            f"{args.command}: project {args.project_id}, {args.region.upper()}, dataset {dataset.manifest['demo_seed_id']}"
        )
        if args.command == "upload":
            importer.upload(args.limit)
            return 0
        return 0 if importer.verify() else 1
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Seeder: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
