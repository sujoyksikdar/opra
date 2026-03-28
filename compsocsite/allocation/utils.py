from django.contrib.auth.models import User

from polls.models import Question, Item, Response, Dictionary
from polls.utils import categorizeResponses, getPrefOrder, buildResponseDict, interpretResponseDict
from prefpy.mechanism import allocation


def getAllocMethods():
    return [
        "Round Robin",
        "Maximum Nash Welfare",
        "Market",
        "MarketEq",
        "Leximin",
        "MNW Binary"
    ]


def getInitialAllocationOrder(question, latest_responses):
    from .models import AllocationVoter
    if len(latest_responses) == 0:
        return

    counter = len(question.item_set.all())
    for user_response in list(reversed(latest_responses)):
        if counter == 0:
            return
        counter -= 1
        voter, created = AllocationVoter.objects.get_or_create(
            question=user_response.question, user=user_response.user)
        voter.response = user_response
        voter.save()
    return


def getCurrentAllocationOrder(question, latest_responses):
    from .models import AllocationVoter
    allocation_order = []
    if question.m_poll == True:
        multipoll = question.multipoll_set.all()[0]
        firstSubpoll = multipoll.questions.all()[0]
        allocation_order = firstSubpoll.allocationvoter_set.all()

        if len(allocation_order) == 0:
            getInitialAllocationOrder(question, latest_responses)
        else:
            for alloc_item in allocation_order:
                voter, created = AllocationVoter.objects.get_or_create(
                    question=question, user=alloc_item.user)
                voter.response = question.response_set.reverse().filter(user=alloc_item.user)[0]
                voter.save()
        allocation_order = question.allocationvoter_set.all()
    else:
        allocation_order = question.allocationvoter_set.all()
        if len(allocation_order) == 0 or len(allocation_order) != len(latest_responses):
            getInitialAllocationOrder(question, latest_responses)
            allocation_order = question.allocationvoter_set.all()

    return allocation_order


def getResponseOrder(allocation_order):
    from .models import AllocationVoter
    response_set = []
    for order_item in allocation_order:
        question = order_item.question
        user = order_item.user

        if question.response_set.reverse().filter(user=user, active=1).count() == 0:
            continue

        response = question.response_set.reverse().filter(user=user, active=1)[0]
        order_item.response = response
        order_item.save()
        response_set.append(response)
    return response_set


def assignAllocation(question, allocationResults):
    for username, item in allocationResults.items():
        currentUser = User.objects.filter(username=username).first()
        allocatedItem = question.item_set.get(item_text=item)
        mostRecentResponse = question.response_set.reverse().filter(user=currentUser, active=1)[0]
        mostRecentResponse.allocation = allocatedItem
        mostRecentResponse.save()
    return


def getFinalAllocation(question):
    response_set = question.response_set.filter(active=1).order_by('-timestamp')
    (latest_responses, previous_responses) = categorizeResponses(response_set)

    if len(latest_responses) == 0:
        return

    allocation_order = getCurrentAllocationOrder(question, latest_responses)
    response_set = getResponseOrder(allocation_order)

    item_set = latest_responses[0].question.item_set.all()
    itemList = [item.item_text for item in item_set]

    responseList = []
    for response in response_set:
        tempDict = {}
        if response.dictionary_set.all().count() > 0:
            dictionary = Dictionary.objects.get(response=response)
        else:
            dictionary = buildResponseDict(
                response, response.question,
                getPrefOrder(response.resp_str, response.question)
            )
        dictionary = interpretResponseDict(dictionary)
        for item, rank in dictionary.items():
            tempDict[item.item_text] = rank
        responseList.append((response.user.username, tempDict))

    allocationResults = allocation(question.poll_algorithm, itemList, responseList)
    assignAllocation(question, allocationResults)


def computeEnvyUptoEF1(preferences, allocated_items_with_values, preferences_with_values):
    envy_matrix = [[(0, 0) for j in range(len(preferences))] for i in range(len(preferences))]
    for i in range(len(allocated_items_with_values)):
        for j in range(len(allocated_items_with_values)):
            if i != j:
                envy, sum2 = getEnvy(
                    preferences_with_values[i], allocated_items_with_values[i],
                    preferences_with_values[j], allocated_items_with_values[j]
                )
                envy_matrix[i][j] = (envy, sum2)
                if envy_matrix[i][j][0] < 0:
                    ef1_val = getEF1(
                        preferences_with_values[i], allocated_items_with_values[i],
                        preferences_with_values[j], allocated_items_with_values[j]
                    )
                    if ef1_val == "EF1":
                        envy_matrix[i][j] = ("EF1", sum2)
            else:
                envy_matrix[i][j] = (0, 0)
    return envy_matrix


def getEnvy(pref1, allocated_items1, pref2, allocated_items2):
    sum1 = 0
    for item, val in allocated_items1:
        sum1 += val

    sum2 = 0
    for item1, val1 in allocated_items2:
        for item2, val2 in pref1:
            if item1 == item2:
                sum2 += val2

    return sum1 - sum2, sum2


def getEF1(pref1, allocated_items1, pref2, allocated_items2):
    for i in range(len(allocated_items2)):
        copy_allocated_items2 = allocated_items2.copy()
        copy_allocated_items2.remove(allocated_items2[i])

        sum1 = 0
        for item, val in allocated_items1:
            sum1 += val

        sum2 = 0
        for item1, val1 in copy_allocated_items2:
            for item2, val2 in pref1:
                if item1 == item2:
                    sum2 += val2

        EF1_val = sum1 - sum2
        if EF1_val >= 0:
            return "EF1"
    return "Not EF1"
