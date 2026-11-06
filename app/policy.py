"""Execute the numeric check in the fictional published return procedure."""
import re


def assess_fixture_return(procedures, fixture):
    procedure = next((p for p in procedures if p.get('key') == 'skillscentral-return-authorization'), None)
    if not procedure or fixture.get('fictional') is not True or fixture.get('found') is not True:
        return None
    window = re.search(r'fictional return window is (\d+) calendar days', procedure.get('instructions', ''), re.I)
    order = fixture.get('data')
    if not window or not isinstance(order, dict):
        return None
    age = order.get('purchase_age_days_at_fixture_time')
    if not isinstance(age, int) or isinstance(age, bool) or age < 0:
        return None
    days = int(window.group(1))
    if age > days:
        decision = f'The purchase is outside the standard return window ({age} > {days}). Specialist review is the next step; standard eligibility is not met.'
        eligible = False
    else:
        items = order.get('items') or []
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            items = []
        if any(i.get('final_sale') or i.get('personalized') for i in items):
            decision = 'The purchase is within the time window, but final-sale or personalized items require specialist review.'
            eligible = False
        elif items and order.get('proof_of_purchase') is True and all(i.get('reported_condition') == 'unworn' and i.get('final_sale') is False and i.get('personalized') is False for i in items):
            decision = f'The unworn purchase with proof of purchase is within the return window ({age} ≤ {days}) and is eligible for review.'
            eligible = True
        else:
            decision = 'The purchase is within the time window. Confirm the item condition, proof of purchase, and item exclusions before assessing eligibility.'
            eligible = None
    answer = f'For fictional order {order.get("order_id", "provided")}, the fixture purchase age is {age} days and the currently published return window is {days} calendar days. {decision}\n\nThis is an assessment only. No return authorization or refund has been issued. Source: {procedure["key"]} v{procedure["version"]}; fictional order snapshot as of {fixture.get("as_of", "the fixture timestamp")}.'
    return {'answer': answer, 'eligible_for_review': eligible, 'purchase_age_days': age, 'published_window_days': days, 'skill_key': procedure['key'], 'version': procedure['version']}
