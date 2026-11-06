"""Verified redis-iris 1.0.1 adapters for the SkillsCentral demo.

The Iris services remain authoritative. This module never fabricates a successful
service response or substitutes a local catalog for remote discovery.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import httpx
import yaml
from redis_iris import AgentMemory, AgentPlaybooks, ContextGateway, IntentRouter, lens


class IrisIntegrationError(RuntimeError):
    """A service request failed; safe to present to the demo operator."""

    def __init__(self, product: str, operation: str, cause: Exception):
        self.product = product
        self.operation = operation
        self.status_code = getattr(cause, "status_code", None)
        message = str(cause)
        for name, value in os.environ.items():
            if value and len(value) > 12 and any(part in name for part in ("KEY", "TOKEN", "PASSWORD", "REDIS_URL")):
                message = message.replace(value, "[redacted]")
        super().__init__(f"{product} {operation} failed: {message[:900]}")


def jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return {name: jsonable(getattr(value, name)) for name in type(value).model_fields if getattr(value, name) is not None}
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(x) for x in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _parse_skill(content: str) -> tuple[dict[str, Any], str]:
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) == 3:
            header = yaml.safe_load(parts[1]) or {}
            return header, parts[2].strip() + "\n"
    raise ValueError("SKILL.md must have YAML frontmatter with a name and description")


def _package(skill: dict[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    """Create a deterministic one-directory Agent Skills ZIP and content metadata."""
    files: dict[str, bytes] = {}
    context: dict[str, Any] = {}
    if skill.get("path"):
        sidecar = Path(skill["path"]) / ".iris-playbook.json"
        if sidecar.exists():
            context = json.loads(sidecar.read_text())
    if skill.get("path") and not skill.get("content") and not skill.get("instructions"):
        directory = Path(skill["path"])
        raw = (directory / "SKILL.md").read_text()
        sidecar = directory / ".iris-playbook.json"
        if sidecar.exists():
            context = json.loads(sidecar.read_text())
        for file in sorted(directory.rglob("*")):
            if file.is_symlink():
                raise ValueError("Skill packages must not contain symbolic links")
            if file.is_file() and file.name != ".iris-playbook.json":
                files[file.relative_to(directory).as_posix()] = file.read_bytes()
    else:
        raw = skill.get("content", "")
        if not raw:
            name = skill.get("name") or skill.get("key")
            if not name or not skill.get("description"):
                raise ValueError("Skill name and description are required")
            raw = "---\n" + yaml.safe_dump({"name": name, "description": skill["description"]}, sort_keys=False) + "---\n\n" + skill.get("instructions", "")
        files["SKILL.md"] = raw.encode()
        for path, content in (skill.get("resources") or {}).items():
            safe = Path(path)
            if safe.is_absolute() or ".." in safe.parts:
                raise ValueError("Resource paths must stay inside the skill directory")
            files[path] = content.encode() if isinstance(content, str) else content
    header, _ = _parse_skill(raw)
    name = header.get("name", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        raise ValueError("Skill names must be lowercase hyphen-separated names, up to 64 characters")
    if not header.get("description"):
        raise ValueError("Skill description is required")
    key = skill.get("key") or name
    if not key.startswith("skillscentral-"):
        raise ValueError("This demo only writes skill keys beginning with skillscentral-")
    for field in ("intents", "attributes", "metadata"):
        if field in skill:
            context[field] = skill[field]
    context.setdefault("attributes", {}).setdefault("demo", "SkillsCentral")
    context.setdefault("metadata", {})
    if not isinstance(context["metadata"], dict):
        raise ValueError("Skill metadata must be an object")
    package = BytesIO()
    with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
        for path, contents in sorted(files.items()):
            info = ZipInfo(f"{name}/{path}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, contents)
    data = package.getvalue()
    digest = sha256(data + json.dumps({k: v for k, v in context.items() if k != "metadata"}, sort_keys=True).encode()).hexdigest()
    context["metadata"]["skillscentral_source_digest"] = digest
    return key, base64.b64encode(data).decode("ascii"), context, digest


class IrisServices:
    def __init__(self) -> None:
        env = dict(os.environ)
        env.setdefault("IRIS_AGENT_PLAYBOOKS_TIMEOUT", "15")
        env.setdefault("IRIS_INTENT_ROUTER_TIMEOUT", "10")
        self.playbook = AgentPlaybooks.from_env(env)
        content_env = dict(env)
        content_env["IRIS_AGENT_PLAYBOOKS_API_KEY"] = env.get("IRIS_AGENT_PLAYBOOKS_CONTENT_API_KEY") or env.get("IRIS_AGENT_PLAYBOOKS_API_KEY", "")
        self.authoring = AgentPlaybooks.from_env(content_env)
        self.router = IntentRouter.from_env(env)
        self.memory = AgentMemory.from_env(env, assistant_id="SkillsCentral")
        self.gateway = ContextGateway.from_env(env)
        lens.init(agent_id=os.getenv("IRIS_LENS_AGENT_ID", "SkillsCentral"))

    def _call(self, operation: str, fn, *, product: str = "Agent Playbooks"):
        try:
            return fn()
        except Exception as exc:
            raise IrisIntegrationError(product, operation, exc) from exc

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, fn in (("playbooks", self.playbook.client.get_playbook_health), ("intent_router", self.router.health)):
            try:
                data = jsonable(fn())
                ok = data.get("ok", data.get("status") == "READY")
                result[name] = {"status": "connected" if ok else "degraded", "details": data}
            except Exception as exc:
                result[name] = {"status": "error", "error": str(IrisIntegrationError(name, "health", exc))}
        state = lens.instrumentation()
        result["lens"] = {"status": "configured" if state.get("lens") == "on" else "error", "instrumentation": state, "stats": lens.stats(), "agent_id": os.getenv("IRIS_LENS_AGENT_ID", "SkillsCentral"), "instance_id": os.getenv("IRIS_LENS_INSTANCE_ID")}
        result["agent_memory"] = {"status": "configured" if os.getenv("IRIS_AGENT_MEMORY_URL") and os.getenv("IRIS_AGENT_MEMORY_API_KEY") else "configuration_missing", "store_id": os.getenv("IRIS_AGENT_MEMORY_STORE_ID"), "missing": [n for n in ("IRIS_AGENT_MEMORY_URL", "IRIS_AGENT_MEMORY_API_KEY") if not os.getenv(n)]}
        result["context_gateway"] = {"status": "configured" if os.getenv("IRIS_CONTEXT_GATEWAY_URL") and os.getenv("IRIS_CONTEXT_GATEWAY_API_KEY") else "configuration_missing", "gateway_id": os.getenv("IRIS_CONTEXT_GATEWAY_ID"), "missing": [n for n in ("IRIS_CONTEXT_GATEWAY_URL", "IRIS_CONTEXT_GATEWAY_API_KEY") if not os.getenv(n)], "note": "No upstreams are configured in the supplied Gateway."}
        if not result["agent_memory"]["missing"]:
            try:
                info = self.memory.health()
                result["agent_memory"].update({"status": "connected" if info.ok else "degraded", "details": jsonable(info)})
            except Exception as exc:
                result["agent_memory"].update({"status": "error", "error": str(IrisIntegrationError("Agent Memory", "health", exc))})
        if not result["context_gateway"]["missing"]:
            try:
                tools = self.gateway.tools()
                result["context_gateway"].update({"status": "connected", "tool_count": len(tools), "tools": [tool.name for tool in tools], "note": "Connected to the existing Gateway MCP endpoint."})
            except Exception as exc:
                result["context_gateway"].update({"status": "error", "error": str(IrisIntegrationError("Context Gateway", "tools/list", exc))})
        return result

    def memory_recall(self, message: str, user_id: str) -> dict[str, Any]:
        found = self._call("recall", lambda: self.memory.recall(message, owner=user_id), product="Agent Memory")
        return {"memories": jsonable(found.memories), "prompt": found.as_prompt()}

    @staticmethod
    def memory_session_id(user_id: str, session_id: str) -> str:
        # The service scopes sessions by ID; owner is a label, not an access check.
        # Hash both IDs to avoid two demo users accidentally sharing a transcript.
        material = f"{len(user_id)}:{user_id}:{session_id}"
        return "SkillsCentral-" + sha256(material.encode()).hexdigest()[:40]

    def memory_record(self, message: str, answer: str, user_id: str, session_id: str) -> dict[str, Any]:
        remote_session_id = self.memory_session_id(user_id, session_id)
        conversation = self.memory.conversation(owner=user_id, session_id=remote_session_id)
        user = self._call("record user", lambda: conversation.user(message), product="Agent Memory")
        assistant = self._call("record assistant", lambda: conversation.assistant(answer), product="Agent Memory")
        return {"user": jsonable(user), "assistant": jsonable(assistant), "session_id": session_id, "memory_session_id": remote_session_id}

    def memory_transcript(self, user_id: str, session_id: str) -> dict[str, Any]:
        transcript = self._call("transcript", lambda: self.memory.conversation(owner=user_id, session_id=self.memory_session_id(user_id, session_id)).transcript(), product="Agent Memory")
        return jsonable(transcript)

    def gateway_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        return jsonable(self._call("tools/list", lambda: self.gateway.tools(refresh=refresh), product="Context Gateway"))

    def gateway_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return jsonable(self._call("search tools", lambda: self.gateway.search(query, limit=limit), product="Context Gateway"))

    def gateway_call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._call("tools/call", lambda: self.gateway.call(name, arguments or {}), product="Context Gateway")
        value = jsonable(result)
        value["upstream_id"] = result.upstream_id
        value["original_name"] = result.original_name
        return value

    def _lookup(self, key: str) -> Any | None:
        ref = {"entry_id": key} if key.startswith("ent_") else {"entry_key": key}
        found = self._call("lookup", lambda: self.authoring.client.lookup_entries(references=[ref]))
        for item in found.items:
            hit = getattr(item, "found", None)
            if hit is not None:
                return hit.entry
        return None

    @staticmethod
    def _summary(entry: Any) -> dict[str, Any]:
        data = jsonable(entry)
        publication = data.get("publication")
        preview = (publication or {}).get("content", {})
        skill = preview.get("payload", {}).get("skill", {})
        return {"key": data.get("entry_key") or data["entry_id"], "entry_id": data["entry_id"], "latest_version": data.get("latest_version", data.get("latest", {}).get("version")), "published_version": (publication or {}).get("version"), "status": "published" if publication else "draft", "name": skill.get("name", skill.get("manifest", {}).get("name", data.get("entry_key", ""))), "description": skill.get("description", ""), "created_at": data.get("created_at"), "updated_at": data.get("updated_at"), "publication": publication}

    def list_skills(self, published: bool | None = None) -> list[dict[str, Any]]:
        items, cursor = [], None
        while True:
            page = self._call("list", lambda: self.authoring.client.list_skills(limit=50, cursor=cursor, published=published, sort_order="DESC"))
            items.extend(self._summary(entry) for entry in page.items)
            cursor = getattr(page, "next_cursor", None)
            if cursor is None:
                return items

    def get_skill(self, key: str, version: int | None = None) -> dict[str, Any]:
        entry = self._lookup(key)
        if entry is None:
            raise KeyError(f"No skill named {key}")
        state = self._call("get", lambda: self.authoring.client.get_skill(skill_id=entry.entry_id))
        target_version = version or state.latest_version
        value = self._call("get version", lambda: self.authoring.client.get_skill_version(skill_id=entry.entry_id, version=target_version))
        result = self._summary(state)
        result.update({"version": target_version, "content": jsonable(value.content), "content_digest": value.content_digest})
        payload = jsonable(value.content).get("payload", {}).get("skill", {})
        result.update({"name": payload.get("manifest", {}).get("name", result.get("name")), "description": payload.get("manifest", {}).get("description", result.get("description")), "instructions": payload.get("instructions", ""), "attributes": jsonable(value.content).get("attributes", {}), "metadata": jsonable(value.content).get("metadata", {})})
        return result

    def import_skill(self, skill: dict[str, Any]) -> dict[str, Any]:
        key, package, context, digest = _package(skill)
        entry = self._lookup(key)
        if entry is not None:
            latest = self._call("read latest", lambda: self.authoring.client.get_skill_version(skill_id=entry.entry_id, version=entry.latest.version))
            metadata = getattr(latest.content, "metadata", None) or {}
            if isinstance(metadata, dict) and metadata.get("skillscentral_source_digest") == digest:
                return {"key": key, "entry_id": entry.entry_id, "version": entry.latest.version, "status": "published" if entry.publication and entry.publication.version == entry.latest.version else "draft", "changed": False}
            created = self._call("append version", lambda: self.authoring.client.append_skill_version(skill_id=entry.entry_id, package_base64=package, content=context))
            version = created.version if isinstance(created.version, int) else created.version.version
            entry_id = entry.entry_id
        else:
            created = self._call("create", lambda: self.authoring.client.create_skill(entry_key=key, package_base64=package, content=context))
            version = created.version.version
            entry_id = created.entry.entry_id
        return {"key": key, "entry_id": entry_id, "version": version, "status": "draft", "changed": True}

    def publish(self, key: str, version: int | None = None) -> dict[str, Any]:
        self._assert_demo_key(key)
        entry = self._lookup(key)
        if entry is None:
            raise KeyError(f"No skill named {key}")
        value = self._call("publish", lambda: self.authoring.client.publish_skill(skill_id=entry.entry_id, version=version or entry.latest.version))
        return self._summary(value)

    def withdraw(self, key: str) -> dict[str, Any]:
        self._assert_demo_key(key)
        entry = self._lookup(key)
        if entry is None:
            raise KeyError(f"No skill named {key}")
        value = self._call("withdraw", lambda: self.authoring.client.withdraw_skill(skill_id=entry.entry_id))
        result = self._summary(value)
        result["status"] = "withdrawn"
        return result

    @staticmethod
    def _assert_demo_key(key: str) -> None:
        if not key.startswith("skillscentral-"):
            raise ValueError("This demo only changes skill keys beginning with skillscentral-")

    def versions(self, key: str) -> list[dict[str, Any]]:
        entry = self._lookup(key)
        if entry is None:
            raise KeyError(f"No skill named {key}")
        items, cursor = [], None
        while True:
            page = self._call("list versions", lambda: self.authoring.client.list_skill_versions(skill_id=entry.entry_id, limit=50, cursor=cursor))
            items.extend(jsonable(value) for value in page.items)
            cursor = getattr(page, "next_cursor", None)
            if cursor is None:
                return items

    def import_faq(self, faq: dict[str, Any], publish: bool = True) -> dict[str, Any]:
        key = faq.get("entryKey") or faq.get("key")
        if not key or not key.startswith("skillscentral-"):
            raise ValueError("This demo only writes FAQ keys beginning with skillscentral-")
        context = {"payload": {"faq": {"question": faq["question"], "answer": faq["answer"]}}, "attributes": faq.get("attributes", {"demo": "SkillsCentral"}), "intents": faq.get("intents", []), "metadata": faq.get("metadata", {})}
        entry = self._lookup(key)
        if entry is None:
            created = self._call("create FAQ", lambda: self.authoring.client.create_faq(entry_key=key, content=context))
            entry_id, version = created.entry.entry_id, created.version.version
            changed = True
        else:
            current = self._call("get FAQ version", lambda: self.authoring.client.get_faq_version(faq_id=entry.entry_id, version=entry.latest.version))
            current_faq = jsonable(current.content).get("payload", {}).get("faq", {})
            entry_id, version = entry.entry_id, entry.latest.version
            changed = current_faq != context["payload"]["faq"]
            if changed:
                created = self._call("append FAQ version", lambda: self.authoring.client.append_faq_version(faq_id=entry_id, content=context))
                version = created.version if isinstance(created.version, int) else created.version.version
        if publish:
            self._call("publish FAQ", lambda: self.authoring.client.publish_faq(faq_id=entry_id, version=version))
        return {"key": key, "entry_id": entry_id, "version": version, "changed": changed, "status": "published" if publish else "draft"}

    def discover(self, message: str, limit: int = 5) -> dict[str, Any]:
        found = self._call("discover", lambda: self.playbook.discover(message, limit=limit))
        entries = []
        for entry in found:
            entries.append({"key": entry.key, "entry_id": entry.entry_id, "type": entry.entry_type, "version": entry.version, "score": entry.score, "title": entry.title, "description": entry.skill.description if entry.skill else "", "answer": entry.faq.answer if entry.faq else None})
        return {"entries": entries, "prompt": found.as_prompt(), "truncated": found.truncated, "budget_truncated": found.budget_truncated, "uncovered": found.uncovered}

    def load_skill(self, key: str, version: int | None = None) -> dict[str, Any]:
        skill = self._call("load", lambda: self.playbook.skill(key, version=version))
        value = jsonable(skill)
        value.update({"key": skill.key, "prompt": skill.as_prompt()})
        return value

    def read_skill_resource(self, key: str, resource_id: str, version: int) -> dict[str, Any]:
        resource = self._call("read resource", lambda: self.playbook.skill_resource(key, resource_id, version=version))
        return {"text": resource.text, "mime_type": resource.mime_type}

    def match_intent(self, message: str) -> dict[str, Any]:
        # A service failure is reported; the caller retains its normal fallback.
        found = self._call("match", lambda: self.router.match(message), product="Intent Router")
        return {"matched": found.best is not None, "best": jsonable(found.best) if found.best else None, "items": jsonable(found.items), "fallback": found.best is None}

    def list_intents(self) -> list[dict[str, Any]]:
        return jsonable(self._call("list intents", self.router.intents, product="Intent Router"))

    @contextmanager
    def turn(self, session_id: str, user_id: str):
        with lens.turn(session_id, user_id=user_id) as turn:
            yield turn

    @contextmanager
    def model_span(self, model: str, skill_key: str | None = None):
        with lens.span("generate_content") as span:
            span.set_attribute("gen_ai.system", "vertex_ai")
            span.set_attribute("gen_ai.operation.name", "chat")
            span.set_attribute("gen_ai.request.model", model)
            if skill_key:
                span.set_attribute("skillscentral.skill_key", skill_key)
            yield span

    @staticmethod
    def record_model_usage(span: Any, input_tokens: int, output_tokens: int, estimated_cost: float | None = None) -> None:
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
        if estimated_cost is not None:
            span.set_attribute("skillscentral.estimated_cost_usd", estimated_cost)

    def lens_sessions(self, range_: str = "24h") -> dict[str, Any]:
        return self._lens_get("sessions", {"agentId": os.getenv("IRIS_LENS_AGENT_ID", "SkillsCentral"), "range": range_, "limit": 50})

    def lens_turn(self, trace_id: str) -> dict[str, Any]:
        return self._lens_get(f"turns/{trace_id}")

    def _lens_get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        endpoint = os.getenv("IRIS_LENS_ENDPOINT", "").rstrip("/")
        instance = os.environ["IRIS_LENS_INSTANCE_ID"]
        def request():
            response = httpx.get(f"{endpoint}/iris/data/v1beta1/lens/instances/{instance}/{path}", headers={"Authorization": f"Bearer {os.getenv('IRIS_LENS_API_KEY', '')}"}, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        return self._call("read", request, product="Lens")
