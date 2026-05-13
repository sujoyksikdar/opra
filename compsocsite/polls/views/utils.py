import json
import logging
import random
from functools import wraps

from appauth.models import *
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.template import RequestContext
from django.utils import timezone
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..models import *

# logger for cache
logger = logging.getLogger(__name__)

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


def block_code_users(redirect_url="/polls/regular_polls/code"):
    """To block code-based users from accessing certain views."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def sendMessage(request):
    if request.method == 'POST':
        message = request.POST["message"]
        name = request.POST["name"]
        email = request.POST["email"]
        if request.user.username != "":
            m1 = Message(text=message, timestamp=timezone.now(), user=request.user,
                        name=name, email=email)
            m1.save()
        else:
            m2 = Message(text=message, timestamp=timezone.now(), name=name, email=email)
            m2.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def mixtureAPI(request):
    context = RequestContext(request)
    if request.method == 'POST':
        votes = json.loads(request.GET['data'])
        m = len(votes[0])
        mixtures_pl1 = egmm_mixpl(votes, m, k=1, itr=10).tolist()
        mixtures_pl2 = egmm_mixpl(votes, m, k=2, itr=10).tolist()
        mixtures_pl3 = egmm_mixpl(votes, m, k=3, itr=10).tolist()
        return HttpResponse(
            json.dumps(mixtures_pl2),
            content_type="application/json"
        )


def mixtureAPI_test(request):
    context = RequestContext(request)
    return render(request, 'polls/api_test.html', context)


def get_polls(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        q = request.GET.get('term', '')
        polls = list(Question.objects.filter(question_owner=request.user,
                                                    m_poll=False,
                                                    question_text__icontains = q).order_by('-pub_date'))
        polls += list(request.user.poll_participated.filter(m_poll=False,
            question_text__icontains = q ).exclude(question_owner=request.user).order_by('-pub_date'))
        polls = polls[:20]
        results = []
        for poll in polls:
            poll_json = {}
            poll_json['id'] = poll.id
            poll_json['label'] = poll.question_text
            poll_json['value'] = poll.question_text
            if poll.question_desc:
                poll_json['desc'] = poll.question_text
            else:
                poll_json['desc'] = "None"
            poll_json['status'] = poll.status
            poll_json['curr_win'] = (poll.question_type == 1 and
                                    poll.status != 1 and poll.status != 3 and
                                    len(poll.response_set.all()) > 0)
            poll_json['type'] = poll.question_type
            if poll.question_type == 1 and poll.status == 3:
                poll_json['winner'] = poll.winner
            elif poll.question_type == 2 and poll.status == 3:
                poll_json['winner'] = ""
            poll_json['created'] = request.user == poll.question_owner
            poll_json['voter'] = request.user in poll.question_voters.all()
            results.append(poll_json)
        data = json.dumps(results)
    else:
        data = 'fail'
    mimetype = 'application/json'
    return HttpResponse(data, mimetype)


def test_server(request):
    m = Message(timestamp=timezone.now(),text="test")
    m.save()
    return HttpResponse("success")


def delete_messages(request):
    Message.objects.all().delete()
    return HttpResponse("success")


def get_num_responses(request):
    result = ""
    resps = Response.objects.filter(user__id__range=(237,647))
    result += str(len(resps)) + "\n"
    return HttpResponse(result)


def recommend_ranking(k):
    try:
        dataset = json.loads(RandomUtilityPool.objects.get(id=3).data)
        rankings = random.sample(dataset,k)
        candidates = [i[1] for i in rankings[0]]
        borda_scores = dict()
        for c in candidates:
            borda_scores[c] = 0
        for r in rankings:
            for i in range(len(r)):
                borda_scores[r[i][1]] += len(r)-i-1
        k = list(borda_scores.keys())
        v = list(borda_scores.values())
        v_with_index = [(v[i],i) for i in range(len(v))]
        v_with_index.sort(reverse=True)
        sorted_k = [k[i[1]] for i in v_with_index]
        return sorted_k
    except:
        return None
