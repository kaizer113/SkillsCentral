"""Customer-visible return decisions derive from published policy and fixture facts."""
from copy import deepcopy

import pytest

from app.policy import assess_fixture_return


def procedure(window=30, version=3, key='skillscentral-return-authorization'):
    return {'key': key, 'version': version, 'instructions': f'Fictional SkillsCentral demonstration procedure. The fictional return window is {window} calendar days from purchase. An unworn item with proof of purchase is eligible for review within that window. Final-sale and personalized items require a specialist.'}


def fixture(age=38):
    return {'fictional': True, 'found': True, 'as_of': '2026-11-05T12:00:00Z', 'data': {'order_id': 'SC-1001', 'purchase_age_days_at_fixture_time': age, 'proof_of_purchase': True, 'items': [{'reported_condition': 'unworn', 'final_sale': False, 'personalized': False}]}}


def test_38_day_purchase_is_outside_published_30_day_window():
    result = assess_fixture_return([procedure(30, 3)], fixture())
    assert result['eligible_for_review'] is False
    assert result['purchase_age_days'] == 38 and result['published_window_days'] == 30
    assert '38 > 30' in result['answer']
    assert 'standard eligibility is not met' in result['answer']
    assert 'specialist review' in result['answer'].lower()
    assert 'skillscentral-return-authorization v3' in result['answer']
    assert 'No return authorization or refund has been issued' in result['answer']


def test_same_purchase_becomes_eligible_for_review_only_with_published_45_day_procedure():
    result = assess_fixture_return([procedure(45, 4)], fixture())
    assert result['eligible_for_review'] is True
    assert result['published_window_days'] == 45
    assert '38 ≤ 45' in result['answer']
    assert 'skillscentral-return-authorization v4' in result['answer']
    assert '2026-11-05T12:00:00Z' in result['answer']
    assert 'assessment only' in result['answer']


@pytest.mark.parametrize('window,age,expected', [(12, 13, False), (15, 13, True), (30, 30, True), (30, 31, False), (90, 38, True)])
def test_decision_uses_provided_policy_window_and_fixture_age(window, age, expected):
    result = assess_fixture_return([procedure(window, 27)], fixture(age))
    assert result['eligible_for_review'] is expected
    assert result['published_window_days'] == window
    assert result['purchase_age_days'] == age
    assert result['version'] == 27


@pytest.mark.parametrize('field,value', [('proof_of_purchase', None), ('proof_of_purchase', False), ('proof_of_purchase', 'yes')])
def test_missing_or_unconfirmed_proof_never_approves_review(field, value):
    record = fixture(20)
    record['data'][field] = value
    result = assess_fixture_return([procedure(30)], record)
    assert result['eligible_for_review'] is None
    assert 'Confirm' in result['answer']


@pytest.mark.parametrize('missing', ['reported_condition', 'final_sale', 'personalized'])
def test_missing_item_facts_require_confirmation(missing):
    record = fixture(20)
    del record['data']['items'][0][missing]
    result = assess_fixture_return([procedure(30)], record)
    assert result['eligible_for_review'] is None
    assert 'Confirm' in result['answer']


@pytest.mark.parametrize('flag', ['final_sale', 'personalized'])
def test_excluded_items_require_specialist_even_within_window(flag):
    record = fixture(20)
    record['data']['items'][0][flag] = True
    result = assess_fixture_return([procedure(45)], record)
    assert result['eligible_for_review'] is False
    assert 'specialist review' in result['answer']


def test_missing_items_cannot_establish_eligibility():
    record = fixture(20)
    del record['data']['items']
    result = assess_fixture_return([procedure(30)], record)
    assert result['eligible_for_review'] is None


@pytest.mark.parametrize('age', [None, True, -1, '38', 38.0])
def test_unverified_purchase_age_prevents_numeric_policy_claim(age):
    assert assess_fixture_return([procedure()], fixture(age)) is None


@pytest.mark.parametrize('marker', ['fictional', 'found'])
@pytest.mark.parametrize('value', [False, None])
def test_unlabeled_real_or_missing_records_are_not_assessed(marker, value):
    record = fixture()
    if value is None:
        record.pop(marker)
    else:
        record[marker] = value
    assert assess_fixture_return([procedure()], record) is None


def test_unrelated_skill_or_unparseable_policy_cannot_supply_a_window():
    assert assess_fixture_return([procedure(45, key='skillscentral-track-order')], fixture()) is None
    assert assess_fixture_return([], fixture()) is None
    assert assess_fixture_return([{'key': 'skillscentral-return-authorization', 'version': 1, 'instructions': 'Ask a specialist. No numeric return window is published.'}], fixture()) is None


@pytest.mark.parametrize('marker', ['fictional', 'found'])
@pytest.mark.parametrize('value', ['false', 'true', 1])
def test_only_explicit_boolean_fixture_labels_allow_assessment(marker, value):
    record = fixture()
    record[marker] = value
    assert assess_fixture_return([procedure()], record) is None


@pytest.mark.parametrize('items', ['unworn', {'reported_condition': 'unworn'}, [None], [17]])
def test_malformed_item_records_cannot_approve_review(items):
    record = fixture(20)
    record['data']['items'] = items
    result = assess_fixture_return([procedure()], record)
    assert result['eligible_for_review'] is None
    assert 'Confirm' in result['answer']
