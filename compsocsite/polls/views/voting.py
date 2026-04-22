from appauth.models import *
from groups.models import *

from ..models import *

from.allocation import getPrefOrder

import json
import logging
from functools import wraps

from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

# logger for cache
logger = logging.getLogger(__name__)
from io import TextIOWrapper

active_polls = []

def block_code_users(redirect_url="/polls/regular_polls/code"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def deleteUserVotes(request, response_id):
    response = get_object_or_404(Response, pk=response_id)
    user = response.user
    question = response.question
    if user: 
        question.response_set.filter(user=user).update(active=0)
    else:
        question.response_set.filter(anonymous_id=response.anonymous_id).update(active=0)
    if not question.new_vote:
        question.new_vote = True
        question.save()
    messages.success(request, 'Your changes have been saved.')
    request.session['setting'] = 6
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def restoreUserVotes(request, response_id):
    response = get_object_or_404(Response, pk=response_id)
    user = response.user
    question = response.question
    if user: 
        question.response_set.filter(user=user, active=0).update(active=1)
    else:
        question.response_set.filter(anonymous_id=response.anonymous_id, active=0).update(active=1)
    request.session['setting'] = 7
    if not question.new_vote:
        question.new_vote = True
        question.save()
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def vote(request, question_id):
    print(">>> VOTE FUNCTION CALLED <<<")
    question = get_object_or_404(Question, pk=question_id)

    prevResponseCount = question.response_set.filter(user=request.user, active=1).count()
    # get the preference order

    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    behavior_string = request.POST["record_data"]
    if prefOrder == None:
        # the user must rank all preferences
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    # make Response object to store data
    comment = request.POST['comment']
    response = Response(question=question, user=request.user, timestamp=timezone.now(),
                        resp_str=orderStr, behavior_data=behavior_string, active=1)
    print("Received POST:")
    print("request.POST['pref_order'] =", request.POST.get('pref_order'))
    print("request.POST['record_data'] =", request.POST.get('record_data'))
    
    if comment != "":
        response.comment = comment
    print("About to save Response with:", response.__dict__)
    response.save()
    print("Saved response with active =", response.active)

    if question.related_class != None and request.user not in question.related_class.students.all():
        question.related_class.students.add(request.user)

    if question.related_class != None and request.user == question.related_class.teacher:
        formatted_order = sorted([i[4:] for i in prefOrder[0]])
        question.correct_answer = json.dumps(formatted_order)
        question.save()

    #enqueue
    #enqueue(getCurrentResult(question))

    #get current winner
    old_winner = OldWinner(question=question, response=response)
    old_winner.save()
    # notify the user that the vote has been saved/updated
    if prevResponseCount == 0:
        messages.success(request, 'Saved!')
    else:
        messages.success(request, 'Updated!')

    if question.open == 2 and request.user not in question.question_voters.all():
        question.question_voters.add(request.user.id)

    if not question.new_vote:
        question.new_vote = True
        question.save()

    return HttpResponseRedirect(reverse('polls:detail', args=(question.id,)))


def buildResponseDict(response, question, prefOrder):
    d = {}
    print(f"\n>>> buildResponseDict CALLED for Question ID: {question.id} <<<")
    print(f">>> prefOrder received: {prefOrder} <<<")

    if prefOrder is None:
        print(">>> prefOrder is None, returning empty dict <<<")
        return d
    # find ranking user gave for each item under the question
    item_num = 1
    print(f">>> Items in question: {question.item_set.all()} <<<")
    for item in question.item_set.all():
        print(f">>> Processing Item: {item} <<<")
        rank = 1
        #Flag for examining the case when new choices are added to poll after poll starts
        flag = True
        for l in prefOrder:
            string = "item" + str(item)
            # if string in l:
            print(f">>> Checking if '{string}' is in {l} <<<")
            if l[0].get("name") == string:
                d[item] = rank
                #If the item is found in preforder, the set flag to false
                flag = False
                print(f"    - Item '{item}' FOUND at Rank {rank}")
                break
            rank += 1
        if flag:
            d[item] = 1000
            print(f"    - Item '{item}' NOT FOUND. Assigning default rank 1000")
        # if arrayIndex == -1:
        #     # set value to lowest possible rank
        #     d[item] = question.item_set.all().count()
        # else:
        #     # add 1 to array index, since rank starts at 1
        #     rank = (prefOrder.index("item" + str(item))) + 1
        #     # add pref to response dict
        #     d[item] = rank
    print(f">>> Final mapped ranks for DB: {d} <<<\n")
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


def anonymousJoin(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    name = request.POST['name']
    request.session['anonymousvoter'] = name
    return HttpResponseRedirect(reverse('polls:detail', args=(question.id,)))


def anonymousVote(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    voter = "Anonymous"
    id = 0
    # check if the anonymous voter has voted before
    if 'anonymousname' in request.POST:
        voter = request.POST['anonymousname']
    if 'anonymousid' not in request.session:
        request.session['anonymousvoter'] = voter
        id = question.response_set.all().count() + 1
        request.session['anonymousid'] = id
    else:
        voter = request.session['anonymousvoter']
        id = request.session['anonymousid']
    # get the preference order
    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    if prefOrder == None:
        # the user must rank all preferences
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # make Response object to store data
    comment = request.POST['comment']
    response = Response(question=question, timestamp=timezone.now(),
                        anonymous_voter=voter, anonymous_id=id, resp_str=orderStr)
    if comment != "":
        response.comment = comment
    response.save()
    
    # find ranking student gave for each item under the question

    #get current winner
    old_winner = OldWinner(question=question, response=response)
    old_winner.save()
    if not question.new_vote:
        question.new_vote = True
        question.save()
    # notify the user that the vote has been updated
    messages.success(request, 'Saved!')
    return HttpResponseRedirect(reverse('polls:detail', args=(question.id,)))


def get_voters(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        q = request.GET.get('term', '')
        users = list(User.objects.filter(username__icontains=q))
        poll_id = request.GET.get('poll_id', '-1')
        if poll_id != '-1':
            exists = Question.objects.filter(pk=poll_id)[0].question_voters.all()
        else:
            exists = []
        ##Add get possible users from API
        results = []
        count = 0
        for user in users:
            if count == 20:
                break
            if user in exists:
                continue
            user_json = {}
            user_json['id'] = user.id
            user_json['label'] = user.username
            user_json['value'] = user.username
            results.append(user_json)
            count += 1
        data = json.dumps(results)
    else:
        data = 'fail'
    mimetype = 'application/json'
    return HttpResponse(data, mimetype)


from .allocation import *
from .home import *
from .poll_creation import *
from .poll_list import *
from .poll_management import *
from .poll_results import *
from .utils import *
from .voters import *
