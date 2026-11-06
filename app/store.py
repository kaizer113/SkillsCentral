"""Small Redis-backed catalog and evidence store, scoped to SkillsCentral:."""
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self):
        url = os.environ["REDIS_URL"]
        if port := os.getenv("REDIS_TUNNEL_PORT"):
            parts = urlsplit(url)
            auth = parts.netloc.rsplit("@", 1)[0]
            url = urlunsplit((parts.scheme, f"{auth}@127.0.0.1:{int(port)}", parts.path, parts.query, parts.fragment))
        self.r = Redis.from_url(url, decode_responses=True, max_connections=20,
                                socket_connect_timeout=3, socket_timeout=5,
                                retry=Retry(NoBackoff(), 0), health_check_interval=30)
        self.prefix = os.getenv("REDIS_PREFIX", "SkillsCentral:")
        if self.prefix != "SkillsCentral:":
            raise ValueError("This demo must use the SkillsCentral: key prefix")

    def key(self, name):
        return self.prefix + name

    def get(self, name, default=None):
        raw = self.r.get(self.key(name))
        return json.loads(raw) if raw else default

    def put(self, name, value, ttl=None):
        self.r.set(self.key(name), json.dumps(value), ex=ttl)

    def skills(self):
        keys = self.r.zrange(self.key("catalog"), 0, -1)
        if not keys:
            return []
        records = self.r.mget([self.key("skill:" + k) for k in keys])
        return [json.loads(raw) for raw in records if raw]

    def skill(self, key):
        return self.get("skill:" + key)

    def save_skill(self, skill):
        pipe = self.r.pipeline(transaction=False)
        pipe.set(self.key("skill:" + skill["key"]), json.dumps(skill))
        pipe.zadd(self.key("catalog"), {skill["key"]: 0})
        pipe.execute()

    def event(self, action, detail, **extra):
        event = {"action": action, "detail": detail, "created_at": now(), **extra}
        pipe = self.r.pipeline(transaction=False)
        pipe.lpush(self.key("events"), json.dumps(event))
        pipe.ltrim(self.key("events"), 0, 199)
        pipe.execute()
        return event

    def events(self):
        return [json.loads(v) for v in self.r.lrange(self.key("events"), 0, 29)]

    def record_turn(self, turn):
        pipe = self.r.pipeline(transaction=False)
        pipe.lpush(self.key("turns"), json.dumps(turn))
        pipe.ltrim(self.key("turns"), 0, 1999)
        pipe.execute()

    def turns(self):
        return [json.loads(v) for v in self.r.lrange(self.key("turns"), 0, 1999)]

    def session(self, user_id, session_id):
        return self.get(f"session:{user_id}:{session_id}", [])

    def save_session(self, user_id, session_id, messages):
        self.put(f"session:{user_id}:{session_id}", messages[-12:], ttl=86400)
