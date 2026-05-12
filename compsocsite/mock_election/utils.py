from functools import wraps
from django.shortcuts import redirect
import json


def block_code_users(redirect_url="/mock_election/regular_polls/code"):
    """To block code-based users from accessing certain views."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def categorizeResponses(all_responses):
    latest_responses = []
    previous_responses = []

    if len(all_responses) > 0:
        latest_responses.append(all_responses[0])

    others = all_responses[1:]

    for response1 in others:
        if response1.user == None:
            add = True
            for response2 in latest_responses:
                if response1.anonymous_voter and response2.anonymous_voter:
                    if response1.anonymous_id == response2.anonymous_id:
                        add = False
                        previous_responses.append(response1)
                        break
            if add:
                latest_responses.append(response1)
        else:
            add = True
            for response2 in latest_responses:
                if not response2.user == None:
                    if response1.user.username == response2.user.username:
                        add = False
                        previous_responses.append(response1)
                        break
            if add:
                latest_responses.append(response1)

    return (latest_responses, previous_responses)


def getPrefOrder(orderStr, question):
    if orderStr == "" or orderStr is None:
        return None
    if ";;|;;" in orderStr:
        current_array = orderStr.split(";;|;;")
        final_order = []
        length = 0
        for item in current_array:
            if item != "":
                curr = item.split(";;")
                final_order.append(curr)
                length += len(curr)
    else:
        final_order = json.loads(orderStr)
    return final_order


def buildResponseDict(response, question, prefOrder):
    d = {}
    if prefOrder is None:
        return d
    for item in question.mockelectionitem_set.all():
        rank = 1
        flag = True
        for l in prefOrder:
            string = "item" + str(item)
            if l[0].get("name") == string:
                d[item] = rank
                flag = False
                break
            rank += 1
        if flag:
            d[item] = 1000
    return d


def interpretResponseDict(dict):
    d = dict
    max = -1
    for k, v in d.items():
        if v > max and v != 1000:
            max = v
    for k, v in d.items():
        if v == 1000:
            d[k] = max + 1
    return d
