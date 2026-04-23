import logging
from functools import wraps

from appauth.models import *
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..email import EmailThread, setupEmail
from ..models import *
from ..utils import (getAllocMethods, getFinalAllocation,
                     getListPollAlgorithms, getPollWinner)

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


def deletePoll(request, question_id):
    """Delete a poll. Only poll owner can do this."""
    
    question = get_object_or_404(Question, pk=question_id)

    # check to make sure the current user is the owner
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))

    question.delete()
    return HttpResponseRedirect(reverse('polls:index'))


def quitPoll(request, question_id):
    """Voter opts out of a poll."""
    
    question = get_object_or_404(Question, pk=question_id)

    # notify the user if this option is checked
    if request.user.userprofile.emailDelete:
        email_class = EmailThread(request, question_id, 'remove')
        email_class.start()

    # remove from the voter list
    question.question_voters.remove(request.user)
    question.save()

    return HttpResponseRedirect(reverse('polls:regular_polls'))


def startPoll(request, question_id):
    """
    Called when poll owner starts a poll.
    
    After a poll starts, voters can vote at any time.
    However, poll owner cannot remove choices any more.
    """
    
    question = get_object_or_404(Question, pk=question_id)

    # check to make sure the owner started the poll
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))

    # set the poll to start
    question.status = 2
    question.save()

    # send notification email
    if question.emailStart:
        email_class = EmailThread(request, question_id, 'start')
        email_class.start()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def pausePoll(request, question_id):
    """
    Called when a poll is paused. 
    
    Owner can then add choices. Voters can no longer vote until poll resumes.
    """
    
    question = get_object_or_404(Question, pk=question_id)

    # check to make sure the owner paused the poll
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))

    # set the status to pause
    question.status = 4
    # get winner or allocation, and save it
    if question.question_type == 1 and question.response_set.filter(active=1).count() >= 1: #poll
        (question.winner, question.mixtures_pl1, question.mixtures_pl2,
        question.mixtures_pl3) = getPollWinner(question)
    question.save()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def resumePoll(request, question_id):
    """Resume a poll from paused state."""
    
    question = get_object_or_404(Question, pk=question_id)

    # check to make sure the owner resumed the poll
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))
    
    allItems = question.item_set.all()
    for item in allItems:
        if item.recently_added:
            item.recently_added = False
            item.save()
    # set the poll to start
    question.status = 2
    question.save()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def stopPoll(request, question_id):
    """
    Stop a poll.
    
    After the poll stops, voters cannot vote. Final results will be available.
    """
    
    question = get_object_or_404(Question, pk=question_id)

    # check to make sure the owner stopped the poll
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))

    # set the status to stop
    question.status = 3
    # get winner or allocation, and save it
    if question.question_type == 1: #poll
        (question.winner, question.mixtures_pl1, question.mixtures_pl2,
        question.mixtures_pl3) = getPollWinner(question)
    elif question.question_type == 2: #allocation
        getFinalAllocation(question)
    question.save()

    if question.emailStart:
        email_class = EmailThread(request, question_id, 'stop')
        email_class.start()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def setInitialSettings(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # map the 1-based dropdown index (1..6) to the actual bits (1,2,4,8,16,32)
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32, 7: 64}

    # 1) read the single dropdown selection ("pollpreferences")
    #    for question_type==1 => regular poll; for question_type==2 => allocation method
    #    store the actual bit in question.poll_algorithm
    selected_idx = int(request.POST.get("pollpreferences", "1"))
    question.poll_algorithm = BIT_MAP.get(selected_idx, 1)  # default to bit=1 if out-of-range

    # 2) optional fields: display_pref, display_user_info, creator_pref
    if "viewpreferences" in request.POST:
        question.display_pref = request.POST["viewpreferences"]
    if "viewuserinfo" in request.POST:
        question.display_user_info = request.POST["viewuserinfo"]
    if "creatorpreferences" in request.POST:
        question.creator_pref = request.POST["creatorpreferences"]

    # 3) accessibility
    openstring = request.POST.get("openpoll", "anon")
    signup_string = request.POST.get("selfsignup", "allow")

    # 4) read ui checkboxes
    uilist = request.POST.getlist("ui")
    question.twocol_enabled = ("twocol" in uilist)
    question.onecol_enabled  = ("onecol" in uilist)
    question.slider_enabled  = ("slider" in uilist)
    question.star_enabled    = ("star" in uilist)
    question.yesno_enabled   = ("yesno" in uilist)
    question.yesno2_enabled  = ("yesno2" in uilist)
    question.budgetUI_enabled   = ("BUI_slider" in uilist)
    question.ListUI_enabled     = ("LUI" in uilist)
    question.infiniteBudgetUI_enabled = ("IBUI" in uilist)

    # count how many ui are selected
    question.ui_number = sum([
        question.twocol_enabled,
        question.onecol_enabled,
        question.slider_enabled,
        question.star_enabled,
        question.yesno_enabled,
        question.yesno2_enabled,
        question.budgetUI_enabled,
        question.ListUI_enabled,
        question.infiniteBudgetUI_enabled
    ])

    # 5) if question_type == 1 (regular poll), set vote_rule
    if question.question_type == 1:
        # question.poll_algorithm is already a bit
        locked_bit = question.poll_algorithm
        vr_sum = locked_bit
        for rule_str in request.POST.getlist("vr"):
            rule_val = int(rule_str)
            if rule_val != locked_bit:
                vr_sum += rule_val
        question.vote_rule = vr_sum

    # 6) set question.open => 0,1,2
    if openstring == "anon":
        question.open = 1
    elif openstring == "invite":
        question.open = 0
    else:
        question.open = 2

    # set question.allow_self_sign_up => 0 or 1
    question.allow_self_sign_up = 1 if signup_string == "allow" else 0

    # 7) for question_type == 2, handle allocation results + allocation algorithms
    #    by default, question.alloc_res_tables = 6 => bits 2 and 4 => items bundle + allocation table
    question.alloc_res_tables = 6
    if question.question_type == 2:
        # read which result tables are checked
        posted_tables = request.POST.getlist("alloc_res_tables")
        alloc_res_sum = 0
        for val_str in posted_tables:
            alloc_res_sum += int(val_str)
        question.alloc_res_tables = alloc_res_sum

        # read which allocation algorithms are checked
        # round robin => bit=1 is always included
        posted_algs = request.POST.getlist("alloc_algorithms")  # e.g. ["2","4","16"]
        alg_sum = 0
        for alg_str in posted_algs:
            alg_sum += int(alg_str)
        question.alloc_algorithms = alg_sum

    if "results_visible_after" in request.POST:
        raw_val = request.POST["results_visible_after"].strip()
        if raw_val:
            dt = parse_datetime(raw_val)
            question.results_visible_after = dt
        else:
            question.results_visible_after = None
    
    # 8) save changes
    question.save()

    # 9) redirect
    if question.question_type == 1:
        return HttpResponseRedirect(reverse("polls:regular_polls"))
    else:
        return HttpResponseRedirect(reverse("polls:allocation_tab"))


def setPollingSettings(request, question_id):
    """
    Process the POST submission from _set_polling_settings.html and update the Question model
    with the chosen algorithms/bitmasks.
    """
    question = get_object_or_404(Question, pk=question_id)

    # Map the 1-based dropdown index to the actual bit:
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32, 7: 64}

    # 1) read the single dropdown selection ("pollpreferences")
    #    for question_type==1, that's the poll algorithm (1-based).
    #    for question_type==2, that's the allocation method (also 1-based).
    if 'pollpreferences' in request.POST:
        selected_idx = int(request.POST['pollpreferences'])
        # store the actual bit in question.poll_algorithm
        question.poll_algorithm = BIT_MAP.get(selected_idx, 1)  # default to 1 if out-of-range

    # 2) if question_type == 1 (regular poll), handle the visible algorithms bitmask (vote_rule)
    if question.question_type == 1:
        # the chosen poll_algorithm is already a bit (like 4 for "Market(EF1)")
        locked_bit = question.poll_algorithm
        posted_vr = request.POST.getlist('vr')  # e.g. ["1","4","8"]
        vr_sum = locked_bit
        for rule_str in posted_vr:
            rule_val = int(rule_str)
            # skip the locked bit (so we don't double-add it)
            if rule_val != locked_bit:
                vr_sum += rule_val
        question.vote_rule = vr_sum

    # 3) if question_type == 2 (allocation poll), handle:
    #    (a) "alloc_algorithms" => question.alloc_algorithms bitmask
    #    (b) "alloc_res_tables" => question.alloc_res_tables bitmask
    if question.question_type == 2:
        # 3a) read the posted "alloc_algorithms" checkboxes
        #     round robin (bit=1) is always included, so start with 1
        posted_alloc_algs = request.POST.getlist('alloc_algorithms')  # e.g. ["2","8","16"]
        alloc_algs_sum = 0
        for alg_str in posted_alloc_algs:
            alg_val = int(alg_str)
            alloc_algs_sum += alg_val
        question.alloc_algorithms = alloc_algs_sum

        # 3b) read the posted "alloc_res_tables" checkboxes
        #     e.g. 1 => "my preferences", 2 => "items bundle", etc.
        posted_res_tables = request.POST.getlist('alloc_res_tables')  # e.g. ["1","4"]
        alloc_res_sum = 0
        for table_str in posted_res_tables:
            table_val = int(table_str)
            alloc_res_sum += table_val
        question.alloc_res_tables = alloc_res_sum

    # 4) save changes
    question.save()

    # 5) success message and redirect
    messages.success(request, "Allocation/poll settings have been updated.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def setVisibilitySettings(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # set the visibility settings, how much information should be shown to the user
    # options range from showing everything (most visibility) to showing only the user's vote
    #   (least visibility)
    if "viewpreferences" in request.POST.keys(): question.display_pref = request.POST['viewpreferences']
    if "viewuserinfo" in request.POST.keys(): question.display_user_info = request.POST['viewuserinfo']
        
    creatorChoice = str(question.creator_pref)
    if 'creatorpreferences' in request.POST:
        creatorChoice = request.POST['creatorpreferences']
    if creatorChoice == "1":
        question.creator_pref = 1
    else:
        question.creator_pref = 2
    
    if "results_visible_after" in request.POST:
        raw_val = request.POST["results_visible_after"].strip()
        if raw_val:
            # parse "2025-09-26T14:30"
            dt = parse_datetime(raw_val)
            question.results_visible_after = dt
        else:
            question.results_visible_after = None


    question.save()
    request.session['setting'] = 10
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def show_polling_settings(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # base context
    ctx = {
        'question': question
    }

    # if question is a regular poll (type=1), we pass poll_algorithms + question.vote_rule
    if question.question_type == 1:
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['bools'] = question.vote_rule  # for the script
    else:
        # question_type == 2 => an allocation poll
        ctx['alloc_methods'] = getAllocMethods()
        ctx['bools'] = question.alloc_algorithms  # for the script

    # if question_type == 2, also pass the existing bitmask for which result-tables are selected
    if question.question_type == 2:
        ctx['selected_alloc_res_tables_sum'] = question.alloc_res_tables

    return render(request, 'polls/_set_polling_settings.html', ctx)


def changeType(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    openstring = request.POST['openpoll']
    if openstring == "anon":
        question.open = 1
    elif openstring == "invite":
        question.open = 0
    else:
        question.open = 2
    question.save()
    request.session['setting'] = 4
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def closePoll(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.open = 0
    question.save()
    request.session['setting'] = 4
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def uninvitedPoll(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.open = 2
    question.save()
    request.session['setting'] = 4
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def duplicatePoll(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    title = question.question_text
    desc = question.question_desc
    voters = question.question_voters.all()
    user = request.user
    items = question.item_set.all()
    new_question = Question(question_text=title, question_desc=desc,
                            pub_date=timezone.now(), question_owner=user,
                            display_pref=question.display_pref,
                            emailInvite=question.emailInvite,
                            emailDelete=question.emailDelete,
                            emailStart=question.emailStart,
                            emailStop=question.emailStop, creator_pref=question.creator_pref,
                            poll_algorithm=question.poll_algorithm,
                            question_type=question.question_type,
                            open=question.open,twocol_enabled=question.twocol_enabled,
                            onecol_enabled=question.onecol_enabled,
                            slider_enabled=question.slider_enabled,
                            star_enabled=question.star_enabled,
                            budgetUI_enabled = question.budgetUI_enabled,
                            ListUI_enabled = question.ListUI_enabled,
                            infiniteBudgetUI_enabled = question.infiniteBudgetUI_enabled,
                            yesno_enabled=question.yesno_enabled,
                            allowties=question.allowties,
                            vote_rule=question.vote_rule)
    new_question.save()
    new_question.question_voters.add(*voters)
    new_items = []
    for item in items:
        new_item = Item(question=new_question, item_text=item.item_text,
                        item_description=item.item_description, timestamp=timezone.now(),
                        image=item.image, imageURL=item.imageURL)
        new_item.save()
        new_items.append(new_item)
    new_question.item_set.add(*new_items)
    setupEmail(new_question)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def check_duplicate_sign_up(user, question):
    current_list = list(question.item_set.all())
    request_list = list(question.signuprequest_set.filter(status=1))
    for i in current_list:
        if str(user.id) == i.self_sign_up_user_id:
            return True
    for r in request_list:
        if user == r.user:
            return True
    return False


def approve_request(request, request_id):
    sign_up_request = get_object_or_404(SignUpRequest,pk=request_id)
    question = sign_up_request.question
    if question.status != 1 and question.status != 4:
        return HttpResponse("Please pause the poll first.")
    sign_up_request.status = 2
    sign_up_request.save()
    item_text = sign_up_request.item_name
    allChoices = question.item_set.all()
    for choice in allChoices:
        if item_text == choice.item_text:
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    recentlyAdded = False
    if question.status == 4:
        recentlyAdded = True
    new_choice = Item(question=question, item_text=item_text, timestamp=timezone.now(), recently_added=recentlyAdded, self_sign_up_user_id=str(sign_up_request.user.id))
    new_choice.save()
    request.session['setting'] = 9

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
