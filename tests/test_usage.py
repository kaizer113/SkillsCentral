"""Verify live usage allocation and user-scoped session storage."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_governance import app_env, skill_fixture


def test_history_spans_active_utc_days_and_preserves_full_coverage(app_env):
    timestamps = ['2026-11-03T23:59:59Z', '2026-11-04T00:00:01Z', '2026-11-06T15:00:00Z']
    for timestamp in timestamps:
        app_env.store.record_turn({'created_at': timestamp, 'skills': [], 'usage': {'input_tokens': 2, 'output_tokens': 1, 'estimated_cost': .000007}})
    data = app_env.client.get('/api/usage').json()
    assert [day['date'] for day in data['daily']] == ['2026-11-03', '2026-11-04', '2026-11-06']
    assert [day['turns'] for day in data['daily']] == [1, 1, 1]
    assert data['history'] == {
        'timezone': 'UTC', 'retained_turns': 3, 'retention_limit': 2000,
        'first_turn_at': timestamps[0], 'last_turn_at': timestamps[-1],
        'active_days': 3, 'chart_active_day_limit': 14, 'has_expiration': False,
    }
    assert data['summary']['turns'] == sum(day['turns'] for day in data['daily'])
    assert data['storage']['product'] == 'Redis Cloud'
    assert data['storage']['key'] == 'SkillsCentral:turns'
    assert data['storage']['data_type'] == 'list'
    assert data['storage']['write_commands'] == ['LPUSH', 'LTRIM']
    assert data['storage']['read_command'] == 'LRANGE'


def test_empty_history_has_no_implied_date_coverage(app_env):
    data = app_env.client.get('/api/usage').json()
    assert data['history']['retained_turns'] == data['history']['active_days'] == 0
    assert data['history']['first_turn_at'] is None
    assert data['history']['last_turn_at'] is None
    assert data['daily'] == []


def test_history_and_totals_cover_more_than_recent_trace_page(app_env):
    for index in range(105):
        app_env.store.record_turn({'created_at': '2026-11-05T12:00:00Z' if index == 0 else '2026-11-06T12:00:00Z', 'skills': [], 'usage': {}})
    data = app_env.client.get('/api/usage').json()
    assert len(data['traces']) == 100
    assert data['summary']['turns'] == data['history']['retained_turns'] == 105
    assert data['history']['first_turn_at'] == '2026-11-05T12:00:00Z'
    assert data['history']['active_days'] == 2
    assert sum(day['turns'] for day in data['daily']) == 105


def test_retention_removes_oldest_turns_when_count_limit_is_reached(app_env):
    from app.store import TURN_RETENTION_LIMIT
    for index in range(TURN_RETENTION_LIMIT + 3):
        app_env.store.record_turn({'created_at': '2026-11-06T12:00:00Z', 'sequence': index, 'skills': [], 'usage': {}})
    retained = app_env.store.turns()
    assert len(retained) == TURN_RETENTION_LIMIT
    assert retained[0]['sequence'] == TURN_RETENTION_LIMIT + 2
    assert retained[-1]['sequence'] == 3
    assert app_env.client.get('/api/usage').json()['history']['retained_turns'] == TURN_RETENTION_LIMIT


def test_skill_allocations_preserve_measured_turn_totals(app_env, tmp_path):
    first = app_env.skill
    second = skill_fixture(tmp_path, 'skillscentral-second-policy', 'Second policy')
    app_env.store.save_skill(second)
    app_env.store.record_turn({'created_at': '2026-11-05T12:00:00Z', 'mode': 'governed_agent', 'skills': [{'key': first['key']}, {'key': second['key']}], 'discovered': [{'key': first['key']}, {'key': second['key']}], 'usage': {'input_tokens': 17, 'output_tokens': 14, 'estimated_cost': .000087}})
    app_env.store.record_turn({'created_at': '2026-11-05T12:01:00Z', 'mode': 'approved_faq', 'skills': [], 'discovered': [], 'usage': {'input_tokens': 0, 'output_tokens': 0, 'estimated_cost': 0}})
    data = app_env.client.get('/api/usage').json()
    assert data['summary']['turns'] == 2
    assert data['summary']['faq_hits'] == 1
    assert data['summary']['skill_uses'] == 2
    assert sum(row['input_tokens'] for row in data['skills']) == data['summary']['input_tokens'] == 17
    assert sum(row['output_tokens'] for row in data['skills']) == data['summary']['output_tokens'] == 14
    assert sum(row['estimated_cost'] for row in data['skills']) == pytest.approx(data['summary']['estimated_cost'])
    assert data['summary']['total_tokens'] == 31
    assert 'illustrative' in data['methodology']


def test_discovery_without_loading_is_not_a_use(app_env):
    app_env.store.record_turn({'created_at': '2026-11-05T12:00:00Z', 'skills': [], 'discovered': [{'key': app_env.skill['key']}], 'usage': {'input_tokens': 0, 'output_tokens': 0, 'estimated_cost': 0}})
    row = app_env.client.get('/api/usage').json()['skills'][0]
    assert row['discoveries'] == 1
    assert row['uses'] == 0
    assert row['estimated_cost'] == 0


def test_chat_history_stays_scoped_to_user_for_same_session_id(app_env):
    app_env.store.save_session('alice', 'shared-label', [{'role': 'user', 'content': 'ALICE_PRIVATE_MARKER'}])
    response = app_env.client.post('/api/chat', json={'message': 'Return this jacket', 'user_id': 'bob', 'session_id': 'shared-label'})
    assert response.status_code == 200
    assert response.json()['mode'] == 'governed_agent'
    assert 'ALICE_PRIVATE_MARKER' not in str(app_env.model_calls[0]['contents'])
    assert app_env.store.session('alice', 'shared-label') == [{'role': 'user', 'content': 'ALICE_PRIVATE_MARKER'}]
    assert app_env.store.session('bob', 'shared-label')[0]['content'] == 'Return this jacket'
    assert all(key.startswith('SkillsCentral:') for key in app_env.store.r.values)


def test_agent_memory_remote_sessions_are_scoped_to_user():
    from app.integrations import IrisServices
    conversations = []
    class Conversation:
        def user(self, text): return {'saved': True}
        def assistant(self, text): return {'saved': True}
        def transcript(self): return {'turns': []}
    class Memory:
        def conversation(self, *, owner, session_id):
            conversations.append((owner, session_id))
            return Conversation()
    iris = IrisServices.__new__(IrisServices)
    iris.memory = Memory()
    alice = iris.memory_record('hello', 'answer', 'alice', 'same-browser-session')
    bob = iris.memory_record('hello', 'answer', 'bob', 'same-browser-session')
    iris.memory_transcript('alice', 'same-browser-session')
    assert alice['session_id'] == bob['session_id'] == 'same-browser-session'
    assert alice['memory_session_id'] != bob['memory_session_id']
    assert conversations[0][1] == conversations[2][1]
    assert conversations[0][1] != conversations[1][1]
