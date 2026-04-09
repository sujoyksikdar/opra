from django.contrib.auth.models import User

from prefpy.mechanism import allocation

from .models import (
    AllocationQuestion,
    AllocationItem,
    AllocationResponse,
    AllocationDictionary,
    AllocationKeyValuePair,
    AllocationVoter,
)


# ── Utility functions (allocation-local copies, no polls dependency) ──────────

def categorizeResponses(response_set):
    """
    Split response_set into (latest_responses, previous_responses).
    latest_responses contains the most recent active response per user.
    """
    latest = {}
    previous = []
    for response in response_set:
        uid = response.user_id
        if uid not in latest:
            latest[uid] = response
        else:
            previous.append(response)
    return list(latest.values()), previous


def getPrefOrder(pref_order_str, question):
    """Parse a preference string into an ordered list of AllocationItems.

    Handles two formats produced by the voting JS:
      - String items: "item1", "item2", ... (1-indexed position)
      - Dict items:   {"name": "item<text>", "score": N, ...} (all score-based UIs)
    """
    if not pref_order_str:
        return []
    try:
        import json as _json
        pref_list = _json.loads(pref_order_str)
    except Exception:
        try:
            import ast
            pref_list = ast.literal_eval(pref_order_str)
        except Exception:
            return []

    item_set = list(question.allocationitem_set.all())
    item_by_text = {item.item_text: item for item in item_set}

    pref_order = []
    for sublist in pref_list:
        tier = []
        for item_ref in sublist:
            if isinstance(item_ref, dict):
                # Score-based UIs (budget, slider, star, twoCol, listUI, etc.)
                # name is "item<item_text>" set as the HTML element id
                name = item_ref.get("name", "")
                if isinstance(name, str) and name.startswith("item"):
                    text = name[4:]
                    if text in item_by_text:
                        tier.append(item_by_text[text])
            elif isinstance(item_ref, str) and item_ref.startswith("item"):
                # Legacy index-based format: "item1", "item2", ...
                try:
                    index = int(item_ref[4:]) - 1
                    if 0 <= index < len(item_set):
                        tier.append(item_set[index])
                except ValueError:
                    # Fallback: treat as item_text
                    text = item_ref[4:]
                    if text in item_by_text:
                        tier.append(item_by_text[text])
        if tier:
            pref_order.append(tier)
    return pref_order


def buildResponseDict(response, question, pref_order):
    """
    Build (and persist) an AllocationDictionary from a parsed preference order.
    Unranked items get sentinel rank 1000.
    """
    dictionary = AllocationDictionary(name=str(response.id), response=response)
    dictionary.save()

    ranked_items = set()
    rank = 1
    for tier in pref_order:
        for item in tier:
            dictionary[item] = rank
            ranked_items.add(item.id)
        rank += 1

    for item in question.allocationitem_set.all():
        if item.id not in ranked_items:
            dictionary[item] = 1000

    return dictionary


def interpretResponseDict(dictionary):
    """Replace sentinel rank 1000 with max_real_rank + 1."""
    real_ranks = [v for _, v in dictionary.items() if v != 1000]
    if not real_ranks:
        return dictionary
    replacement = max(real_ranks) + 1
    for item, rank in list(dictionary.items()):
        if rank == 1000:
            dictionary[item] = replacement
    return dictionary


# ── Allocation algorithm names ────────────────────────────────────────────────

def getAllocMethods():
    return [
        "Round Robin",
        "Maximum Nash Welfare",
        "Market",
        "MarketEq",
        "Leximin",
        "MNW Binary",
    ]


# ── Voter ordering pipeline ───────────────────────────────────────────────────

def getInitialAllocationOrder(question, latest_responses):
    if len(latest_responses) == 0:
        return

    counter = len(question.allocationitem_set.all())
    for user_response in list(reversed(latest_responses)):
        if counter == 0:
            return
        counter -= 1
        voter, created = AllocationVoter.objects.get_or_create(
            question=user_response.question, user=user_response.user
        )
        voter.response = user_response
        voter.save()


def getCurrentAllocationOrder(question, latest_responses):
    allocation_order = question.allocationvoter_set.all()
    if len(allocation_order) == 0 or len(allocation_order) != len(latest_responses):
        getInitialAllocationOrder(question, latest_responses)
        allocation_order = question.allocationvoter_set.all()
    return allocation_order


def getResponseOrder(allocation_order):
    response_set = []
    for order_item in allocation_order:
        question = order_item.question
        user = order_item.user

        if question.allocationresponse_set.reverse().filter(user=user, active=1).count() == 0:
            continue

        response = question.allocationresponse_set.reverse().filter(user=user, active=1)[0]
        order_item.response = response
        order_item.save()
        response_set.append(response)
    return response_set


def assignAllocation(question, allocationResults):
    for username, item_text in allocationResults.items():
        current_user = User.objects.filter(username=username).first()
        allocated_item = question.allocationitem_set.get(item_text=item_text)
        most_recent = question.allocationresponse_set.reverse().filter(user=current_user, active=1)[0]
        most_recent.allocation = allocated_item
        most_recent.save()


def getFinalAllocation(question):
    response_set = question.allocationresponse_set.filter(active=1).order_by('-timestamp')
    (latest_responses, _) = categorizeResponses(response_set)

    if len(latest_responses) == 0:
        return

    allocation_order = getCurrentAllocationOrder(question, latest_responses)
    response_set = getResponseOrder(allocation_order)

    item_set = latest_responses[0].question.allocationitem_set.all()
    item_list = [item.item_text for item in item_set]

    response_list = []
    for response in response_set:
        temp_dict = {}
        existing = AllocationDictionary.objects.filter(response=response)
        if existing.count() > 0:
            dictionary = existing.first()
        else:
            dictionary = buildResponseDict(
                response, response.question,
                getPrefOrder(response.resp_str, response.question)
            )
        dictionary = interpretResponseDict(dictionary)
        for item, rank in dictionary.items():
            temp_dict[item.item_text] = rank
        response_list.append((response.user.username, temp_dict))

    allocation_results = allocation(question.poll_algorithm, item_list, response_list)
    assignAllocation(question, allocation_results)


# ── Fairness metrics ──────────────────────────────────────────────────────────

def computeEnvyUptoEF1(preferences, allocated_items_with_values, preferences_with_values):
    envy_matrix = [[(0, 0) for _ in range(len(preferences))] for _ in range(len(preferences))]
    for i in range(len(allocated_items_with_values)):
        for j in range(len(allocated_items_with_values)):
            if i != j:
                envy, sum2 = getEnvy(
                    preferences_with_values[i], allocated_items_with_values[i],
                    preferences_with_values[j], allocated_items_with_values[j],
                )
                envy_matrix[i][j] = (envy, sum2)
                if envy_matrix[i][j][0] < 0:
                    ef1_val = getEF1(
                        preferences_with_values[i], allocated_items_with_values[i],
                        preferences_with_values[j], allocated_items_with_values[j],
                    )
                    if ef1_val == "EF1":
                        envy_matrix[i][j] = ("EF1", sum2)
            else:
                envy_matrix[i][j] = (0, 0)
    return envy_matrix


def getEnvy(pref1, allocated_items1, pref2, allocated_items2):
    sum1 = sum(val for _, val in allocated_items1)
    sum2 = sum(v2 for item1, _ in allocated_items2 for item2, v2 in pref1 if item1 == item2)
    return sum1 - sum2, sum2


def getEF1(pref1, allocated_items1, pref2, allocated_items2):
    for i in range(len(allocated_items2)):
        copy2 = allocated_items2.copy()
        copy2.pop(i)
        sum1 = sum(val for _, val in allocated_items1)
        sum2 = sum(v2 for item1, _ in copy2 for item2, v2 in pref1 if item1 == item2)
        if sum1 - sum2 >= 0:
            return "EF1"
    return "Not EF1"
