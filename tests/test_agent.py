"""Exercise the bounded Gemini/Gateway loop using real SDK message models."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

from google.genai import types
import pytest

from app.agent import generate_answer


ORDER_TOOL = {
    'name': 'skillscentral__get_order',
    'description': 'Read one fictional order.',
    'input_schema': {'type': 'object', 'properties': {'order_id': {'type': 'string'}}, 'required': ['order_id']},
    'annotations': {'readOnlyHint': True},
}


def response(*, text=None, calls=(), tokens_in=0, tokens_out=0, thoughts=0):
    parts = [types.Part.from_function_call(name=name, args=args) for name, args in calls]
    if text is not None:
        parts.append(types.Part.from_text(text=text))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role='model', parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=tokens_in, candidates_token_count=tokens_out, thoughts_token_count=thoughts),
    )


class FakeModels:
    def __init__(self, responses):
        self.responses, self.calls = iter(responses), []
    def generate_content(self, **kwargs):
        # Snapshot the history before the caller appends the next tool response.
        self.calls.append(deepcopy(kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class FakeIris:
    def __init__(self, tools=None, result=None, failure=None):
        self.available = [deepcopy(ORDER_TOOL)] if tools is None else tools
        self.result = result or {'data': {'order_id': 'SC-1001', 'status': 'shipped', 'fictional': True}, 'is_error': False, 'upstream_id': 'upstream-demo'}
        self.failure = failure
        self.calls, self.searches, self.recorded_usage = [], [], []
    def gateway_search(self, query, limit):
        self.searches.append((query, limit))
        return self.available
    def gateway_call(self, name, arguments):
        self.calls.append((name, arguments))
        if self.failure:
            raise self.failure
        return deepcopy(self.result)
    @contextmanager
    def model_span(self, model):
        yield SimpleNamespace(set_attribute=lambda *args: None)
    def record_model_usage(self, span, tokens_in, tokens_out):
        self.recorded_usage.append((tokens_in, tokens_out))


@pytest.fixture
def run(monkeypatch):
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    monkeypatch.setenv('DEMO_INPUT_USD_PER_MILLION', '1')
    monkeypatch.setenv('DEMO_OUTPUT_USD_PER_MILLION', '5')
    def invoke(responses, iris=None, usage=None, message="Find my order SC-1001", prompt=None, procedures=None):
        models = FakeModels(responses)
        iris = iris or FakeIris()
        usage = {} if usage is None else usage
        steps, warnings = [], []
        answer = generate_answer(SimpleNamespace(models=models), iris, 'Published fictional return procedure.', message if prompt is None else prompt, message, [{'key': 'skillscentral-track-order'}], steps, warnings, usage, procedures=procedures)
        return SimpleNamespace(answer=answer, models=models, iris=iris, usage=usage, steps=steps, warnings=warnings)
    return invoke


def test_allowed_discovered_readonly_tool_runs_through_gateway_and_all_model_tokens_accumulate(run):
    result = run([
        response(calls=[('skillscentral__get_order', {'order_id': 'SC-1001'})], tokens_in=13, tokens_out=4, thoughts=2),
        response(text='Your fictional order is shipped.', tokens_in=21, tokens_out=8, thoughts=1),
    ])
    assert result.iris.calls == [('skillscentral__get_order', {'order_id': 'SC-1001'})]
    assert result.answer['answer'] == 'Your fictional order is shipped.'
    assert result.answer['input_tokens'] == result.usage['input_tokens'] == 34
    assert result.answer['output_tokens'] == result.usage['output_tokens'] == 15
    assert result.usage['estimated_cost'] == pytest.approx((34 + 15 * 5) / 1_000_000)
    assert result.iris.recorded_usage == [(13, 6), (21, 9)]
    assert result.answer['tool_calls'][0]['upstream_id'] == 'upstream-demo'
    assert result.models.calls[0]['config'].automatic_function_calling.disable is True
    assert [decl.name for decl in result.models.calls[0]['config'].tools[0].function_declarations] == ['skillscentral__get_order']
    history = result.models.calls[1]['contents']
    assert history[-1].parts[0].function_response.name == 'skillscentral__get_order'
    assert history[-1].parts[0].function_response.response['fictional'] is True
    assert [step['name'] for step in result.steps].count('Gemini tool selection') == 1


@pytest.mark.parametrize('tool_name,tools', [
    ('delete_customer', [ORDER_TOOL]),
    ('skillscentral__get_loyalty_profile', [ORDER_TOOL]),
    ('skillscentral__get_order', [{**ORDER_TOOL, 'annotations': {'readOnlyHint': False}}]),
    ('skillscentral__get_order', [{**ORDER_TOOL, 'annotations': {}}]),
])
def test_unknown_unexposed_or_nonreadonly_tool_is_never_executed(run, tool_name, tools):
    result = run([
        response(calls=[(tool_name, {'order_id': 'SC-1001'})], tokens_in=5, tokens_out=2),
        response(text='Please provide an approved workflow.', tokens_in=7, tokens_out=3),
    ], iris=FakeIris(tools=deepcopy(tools)))
    assert result.iris.calls == []
    assert result.answer['tool_calls'] == []
    tool_response = result.models.calls[1]['contents'][-1].parts[0].function_response
    assert tool_response.name == tool_name
    assert tool_response.response['error'] == 'This tool was not discovered and is not allowed.'
    declarations = result.models.calls[0]['config'].tools
    if declarations:
        assert tool_name not in [decl.name for decl in declarations[0].function_declarations]


def test_usage_survives_gateway_failure_after_paid_model_selection(run):
    usage = {'input_tokens': 0, 'output_tokens': 0, 'estimated_cost': 0.0}
    iris = FakeIris(failure=RuntimeError('Gateway unavailable'))
    with pytest.raises(RuntimeError, match='Gateway unavailable'):
        run([response(calls=[('skillscentral__get_order', {'order_id': 'SC-1001'})], tokens_in=19, tokens_out=4, thoughts=3)], iris=iris, usage=usage)
    assert usage['input_tokens'] == 19
    assert usage['output_tokens'] == 7
    assert usage['estimated_cost'] == pytest.approx((19 + 7 * 5) / 1_000_000)
    assert iris.recorded_usage == [(19, 7)]


def test_usage_survives_later_model_failure_after_successful_tool_call(run):
    usage = {}
    iris = FakeIris()
    with pytest.raises(RuntimeError, match='Model unavailable'):
        run([
            response(calls=[('skillscentral__get_order', {'order_id': 'SC-1001'})], tokens_in=11, tokens_out=3),
            RuntimeError('Model unavailable'),
        ], iris=iris, usage=usage)
    assert iris.calls == [('skillscentral__get_order', {'order_id': 'SC-1001'})]
    assert usage['input_tokens'] == 11
    assert usage['output_tokens'] == 3
    assert usage['estimated_cost'] == pytest.approx((11 + 3 * 5) / 1_000_000)


def test_long_chat_uses_bounded_gateway_query_without_truncating_model_input(run):
    class StrictGateway(FakeIris):
        def gateway_search(self, query, limit):
            if len(query) > 200:
                raise ValueError("Gateway search query exceeds its 200-character limit")
            return super().gateway_search(query, limit)
    message = "  Find fictional order SC-1001. " + "Please consider these customer-provided details. " * 8 + "TAIL_FACT_MUST_REACH_MODEL  "
    full_prompt = "Earlier conversation context.\nuser: " + message
    iris = StrictGateway()
    result = run([response(text='The fictional order needs review.', tokens_in=50, tokens_out=10)], iris=iris, message=message, prompt=full_prompt)
    assert len(message) > 200
    assert iris.searches == [(message.strip()[:200], 5)]
    assert result.warnings == []
    assert result.models.calls[0]['contents'][0].parts[0].text == full_prompt
    assert 'TAIL_FACT_MUST_REACH_MODEL' in result.models.calls[0]['contents'][0].parts[0].text
    assert result.models.calls[0]['config'].tools[0].function_declarations[0].name == ORDER_TOOL['name']


def test_structured_gateway_failure_reaches_model_as_error_and_step_as_warning(run):
    iris = FakeIris(result={'data': {'reason': 'Fictional order not found', 'order_id': 'SC-9999'}, 'is_error': True, 'upstream_id': 'upstream-demo'})
    result = run([
        response(calls=[('skillscentral__get_order', {'order_id': 'SC-9999'})], tokens_in=8, tokens_out=3),
        response(text='I could not find that fictional order. Please check the reference.', tokens_in=12, tokens_out=7),
    ], iris=iris)
    delivered = result.models.calls[1]['contents'][-1].parts[0].function_response.response
    assert delivered['error'] == 'The Gateway tool reported a failure.'
    assert delivered['tool_result']['reason'] == 'Fictional order not found'
    tool_steps = [step for step in result.steps if step['name'].startswith('Gateway tool:')]
    assert tool_steps[0]['status'] == 'warning'
    assert result.answer['tool_calls'][0]['result']['error'] == delivered['error']
    assert result.usage['input_tokens'] == 20
    assert result.usage['output_tokens'] == 10


@pytest.mark.parametrize('batches', [[4], [2, 2]])
def test_tool_budget_covers_entire_turn_and_every_requested_call_gets_a_response(run, batches):
    replies = []
    offset = 0
    for count in batches:
        replies.append(response(calls=[('skillscentral__get_order', {'order_id': f'SC-{offset + i}'}) for i in range(count)], tokens_in=10, tokens_out=4))
        offset += count
    replies.append(response(text='I checked three fictional orders; please narrow the remaining request.', tokens_in=15, tokens_out=8))
    result = run(replies)
    assert len(result.iris.calls) == 3
    assert len(result.answer['tool_calls']) == 3
    assert result.iris.calls[-1][1]['order_id'] == 'SC-2'
    for index, count in enumerate(batches):
        history = result.models.calls[index + 1]['contents']
        answers = history[-1].parts
        assert len(answers) == count
        assert all(part.function_response.name == ORDER_TOOL['name'] for part in answers)
    last_tool_responses = result.models.calls[len(batches)]['contents'][-1].parts
    assert last_tool_responses[-1].function_response.response['error'] == 'The three-tool limit for this turn has been reached.'
    assert result.usage['input_tokens'] == len(batches) * 10 + 15
    assert result.usage['output_tokens'] == len(batches) * 4 + 8


def test_nonobject_structured_tool_data_becomes_a_valid_function_response_object(run):
    iris = FakeIris(result={'data': [{'store_id': 'SEA-01', 'available': 3}], 'is_error': False})
    result = run([
        response(calls=[('skillscentral__get_order', {'order_id': 'SC-1001'})], tokens_in=8, tokens_out=3),
        response(text='The fictional tool returned one result.', tokens_in=12, tokens_out=7),
    ], iris=iris)
    delivered = result.models.calls[1]['contents'][-1].parts[0].function_response.response
    assert delivered == {'value': [{'store_id': 'SEA-01', 'available': 3}]}


@pytest.mark.parametrize('window,version,expected', [(30, 3, False), (45, 4, True)])
def test_gateway_fixture_return_uses_published_numeric_policy_without_second_model_call(run, window, version, expected):
    from test_policy import fixture, procedure
    iris = FakeIris(result={'data': fixture(38), 'is_error': False, 'upstream_id': 'upstream-demo'})
    result = run([
        response(calls=[('skillscentral__get_order', {'order_id': 'SC-1001'})], tokens_in=13, tokens_out=4, thoughts=2),
        RuntimeError('A second model call must not override the verified numeric assessment'),
    ], iris=iris, procedures=[procedure(window, version)])
    assert len(result.models.calls) == 1
    assert result.iris.calls == [('skillscentral__get_order', {'order_id': 'SC-1001'})]
    assert result.answer['assessment']['eligible_for_review'] is expected
    assert result.answer['assessment']['published_window_days'] == window
    assert result.answer['assessment']['purchase_age_days'] == 38
    assert result.usage['input_tokens'] == 13
    assert result.usage['output_tokens'] == 6
    assert any(step['name'] == 'Published policy calculation' for step in result.steps)
    assert 'No return authorization or refund has been issued' in result.answer['answer']
