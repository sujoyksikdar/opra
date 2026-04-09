import ast
import csv
import io
import itertools
import json
import logging
import random
import secrets
import string
import threading

import numpy as np
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import RequestContext
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django import views

from prefpy.mechanism import (
    MechanismRoundRobinAllocation,
    MechanismMaximumNashWelfare,
    MechanismMarketAllocation,
    MechanismMarketEqAllocation,
    MechanismLeximinAllocation,
    MechanismMaximumNashWelfareBinary,
)
from prefpy.allocation_properties import is_po

from groups.models import Folder, Group

from .models import AllocationQuestion, AllocationItem, AllocationResponse, AllocationDictionary, AllocationVoter, AllocationCache, AllocationLoginCode, AllocationEmail, AllocationSignUpRequest
from .utils import (
    getAllocMethods,
    getPrefOrder,
    buildResponseDict,
    interpretResponseDict,
    categorizeResponses,
    getFinalAllocation,
    computeEnvyUptoEF1,
)

logger = logging.getLogger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────────────

def block_code_users(redirect_url="/allocations/allocation_tab/code"):
    from functools import wraps
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def isPrefReset(request):
    return request.GET.get('order', '') == "null"


def getCurrentSelectionAlloc(response):
    """Return current ranking as List[List[AllocationItem]] from an AllocationResponse."""
    existing = AllocationDictionary.objects.filter(response=response)
    if existing.count() > 0:
        d = existing.first()
        # If the cached dict has no ranked items (all 1000), it was built with the
        # old broken getPrefOrder. Delete it and rebuild with the fixed version.
        has_ranked = any(rank != 1000 for _, rank in d.items())
        if not has_ranked:
            d.delete()
            existing = AllocationDictionary.objects.none()

    if not existing.count():
        d = buildResponseDict(response, response.question,
                              getPrefOrder(response.resp_str, response.question))

    item_count = response.question.allocationitem_set.all().count()
    array = [[] for _ in range(item_count)]
    for item, rank in d.items():
        if rank != 1000:
            array[rank - 1].append(item)
    return array


def getUnrankedCandidatesAlloc(response):
    """Return items ranked 1000 (unranked) from an AllocationResponse."""
    existing = AllocationDictionary.objects.filter(response=response)
    if existing.count() > 0:
        d = existing.first()
    else:
        d = buildResponseDict(response, response.question,
                              getPrefOrder(response.resp_str, response.question))
    unranked = [item for item, rank in d.items() if rank == 1000]
    return unranked if unranked else None


def getSelectionListAlloc(response_list):
    return [(r, getCurrentSelectionAlloc(r)) for r in response_list]


def addPreferenceValueToRespAlloc(objs):
    for i in range(len(objs)):
        response, prefOrder = objs[i]
        behavior_data = json.loads(response.behavior_data)
        submitted_rankings = behavior_data.get("submitted_ranking", [])
        scores = set()
        for tier in submitted_rankings:
            for jsonObj in tier:
                if isinstance(jsonObj, dict) and "score" in jsonObj:
                    scores.add(jsonObj["score"])
        scores = sorted(list(scores))[-1::-1] if scores else []
        for j in range(min(len(scores), len(prefOrder))):
            prefOrder[j].insert(0, scores[j])
    return objs


# ── List / tab views ──────────────────────────────────────────────────────────

@method_decorator(block_code_users("/allocations/allocation_tab/code"), name="dispatch")
@method_decorator(login_required, name="dispatch")
class RegularAllocationView(views.generic.ListView):
    template_name = 'allocation/allocation_tab.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        return AllocationQuestion.objects.all().order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['folders'] = Folder.objects.filter(user=self.request.user).all()

        ctx['polls_created'] = list(
            AllocationQuestion.objects.filter(
                question_owner=self.request.user, m_poll=False
            ).order_by('-pub_date')
        )
        ctx['active_polls'] = list(AllocationQuestion.objects.all().order_by('-pub_date'))

        polls = self.request.user.allocation_participated.filter(m_poll=False)
        polls = polls.exclude(question_owner=self.request.user).order_by('-pub_date')
        ctx['polls_participated'] = list(polls)

        self.request.session['questionType'] = 2
        return ctx


class CodeAllocationView(views.generic.ListView):
    template_name = 'allocation/allocation_tab_code.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        qid = self.request.session.get('code_question_id')
        return AllocationQuestion.objects.filter(pk=qid).order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qid = self.request.session.get('code_question_id')
        ctx['folders'] = []
        ctx['polls_created'] = []
        ctx['active_polls'] = list(AllocationQuestion.objects.all().order_by('-pub_date'))
        ctx['polls_participated'] = list(AllocationQuestion.objects.filter(pk=qid))
        self.request.session['questionType'] = 2
        return ctx


# ── Creation wizard ───────────────────────────────────────────────────────────

def AllocationAddStep1(request):
    if request.method == 'POST':
        question_text = request.POST['questionTitle']
        question_desc = request.POST['desc']
        image_url = request.POST['imageURL']

        question = AllocationQuestion(
            question_text=question_text,
            question_desc=question_desc,
            pub_date=timezone.now(),
            question_owner=request.user,
            display_pref=request.user.userprofile.displayPref,
            emailInvite=request.user.userprofile.emailInvite,
            emailDelete=request.user.userprofile.emailDelete,
            emailStart=request.user.userprofile.emailStart,
            emailStop=request.user.userprofile.emailStop,
            creator_pref=1,
        )
        if request.FILES.get('docfile') is not None:
            question.image = request.FILES.get('docfile')
        elif image_url:
            question.imageURL = image_url
        question.save()
        return HttpResponseRedirect(reverse('allocation:AddStep2', args=(question.id,)))
    return render(request, 'allocation/add_step1.html', {})


@method_decorator(block_code_users("/allocations/allocation_tab/code"), name="dispatch")
class AllocationAddStep2View(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/add_step2.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.object.allocationitem_set.all()
        return ctx

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())


@method_decorator(block_code_users("/allocations/allocation_tab/code"), name="dispatch")
class AllocationAddStep3View(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/add_step3.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['users'] = User.objects.filter(userprofile__is_code_user=False)
        ctx['groups'] = Group.objects.all()
        ctx['recentCSVText'] = self.object.recentCSVText
        return ctx

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())


@method_decorator(block_code_users("/allocations/allocation_tab/code"), name="dispatch")
class AllocationAddStep4View(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/add_step4.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['alloc_methods'] = getAllocMethods()
        return ctx

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())


# ── Item (choice) management ──────────────────────────────────────────────────

def allocationAddChoice(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    item_text = request.POST['choice']
    image_url = request.POST['imageURL']

    if not item_text:
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    for choice in question.allocationitem_set.all():
        if item_text == choice.item_text:
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    recently_added = question.status == 4
    item = AllocationItem(
        question=question,
        item_text=item_text,
        timestamp=timezone.now(),
        recently_added=recently_added,
    )
    if request.FILES.get('docfile') is not None:
        item.image = request.FILES.get('docfile')
    elif image_url:
        item.imageURL = image_url
    item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationEditChoice(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    for item in question.allocationitem_set.all():
        new_text = request.POST["item" + str(item.id)]
        item_desc = request.POST["itemdescription" + str(item.id)]
        image_url = request.POST["imageURL" + str(item.id)]
        if item_desc:
            item.item_description = item_desc
        if request.FILES.get("docfile" + str(item.id)) is not None:
            item.image = request.FILES.get("docfile" + str(item.id))
        elif image_url:
            item.imageURL = image_url
        item.item_text = new_text
        item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationEditBasicInfo(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if "title" in request.POST:
        question.question_text = request.POST["title"]
    if "desc" in request.POST:
        question.question_desc = request.POST["desc"]
    uilist = request.POST.getlist('ui')
    question.twocol_enabled = "twocol" in uilist
    question.onecol_enabled = "onecol" in uilist
    question.slider_enabled = "slider" in uilist
    question.star_enabled = "star" in uilist
    question.yesno_enabled = "yesno" in uilist
    question.budgetUI_enabled = "BUI_slider" in uilist
    question.ListUI_enabled = "LUI" in uilist
    question.infiniteBudgetUI_enabled = "IBUI" in uilist
    question.ui_number = sum([
        question.twocol_enabled, question.onecol_enabled,
        question.slider_enabled, question.star_enabled,
        question.yesno_enabled, question.budgetUI_enabled,
        question.ListUI_enabled, question.infiniteBudgetUI_enabled,
    ])
    question.save()
    request.session['setting'] = 8
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationDeleteChoice(request, choice_id):
    item = get_object_or_404(AllocationItem, pk=choice_id)
    item.delete()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Voter management ──────────────────────────────────────────────────────────

def allocationAddVoter(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    all_new_usernames = []

    new_voters = request.POST.getlist('voters')
    for voter in new_voters:
        try:
            voter_obj = User.objects.get(username=voter)
            question.question_voters.add(voter_obj.id)
            all_new_usernames.append(voter)
        except User.DoesNotExist:
            pass

    new_groups = request.POST.getlist('groups')
    for group_name in new_groups:
        try:
            grp = Group.objects.get(name=group_name, owner=request.user)
            question.question_voters.add(*grp.members.all())
            all_new_usernames.extend([m.username for m in grp.members.all()])
        except Group.DoesNotExist:
            pass

    if all_new_usernames:
        existing = question.recentCSVText.split(',') if question.recentCSVText else []
        updated = list(set([e.strip() for e in existing if e.strip()] + all_new_usernames))
        question.recentCSVText = ','.join(updated)
        question.save()

    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationRemoveVoter(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if question.status != 1:
        messages.error(request, "Cannot remove voters after the allocation is started/paused.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    voters_to_remove_names = request.POST.getlist('voters')
    if not voters_to_remove_names:
        messages.warning(request, "No users selected for removal.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    users_to_remove = User.objects.filter(username__in=voters_to_remove_names)
    question.question_voters.remove(*users_to_remove)

    existing = question.recentCSVText.split(",") if question.recentCSVText else []
    updated = [e.strip() for e in existing if e.strip().lower() not in [u.lower() for u in voters_to_remove_names]]
    question.recentCSVText = ",".join(updated)
    question.save()

    messages.success(request, "Selected users have been removed from " + question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationRemoveGroupVoters(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    remove_groups = request.POST.getlist('groups')
    for group_name in remove_groups:
        for grp in Group.objects.all():
            if grp.owner == request.user and grp.name == group_name:
                for voter in grp.members.all():
                    if voter in question.question_voters.all():
                        question.question_voters.remove(voter.id)
    messages.success(request, "Selected groups have been removed from " + question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationSaveLatestCSV(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    recent_csv = request.POST.get('votersCSVText', '')
    question.recentCSVText = recent_csv
    question.save()
    # Add any registered users from the CSV
    if recent_csv:
        for uid in [x.strip() for x in recent_csv.split(',') if x.strip()]:
            try:
                voter_obj = User.objects.get(username=uid)
                question.question_voters.add(voter_obj.id)
            except User.DoesNotExist:
                pass
    messages.success(request, "Users have been added to " + question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


_ALLOC_CODE_SPECIALS = "!@#$%^&*()_+[]{}|;:,.<>?"

def _generate_allocation_code(length=10):
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice(_ALLOC_CODE_SPECIALS)
    pool = string.ascii_letters + string.digits + _ALLOC_CODE_SPECIALS
    rest = ''.join(secrets.choice(pool) for _ in range(length - 4))
    raw = list(upper + lower + digit + special + rest)
    secrets.SystemRandom().shuffle(raw)
    return ''.join(raw)


def allocationAddCodes(request, question_id):
    if request.method != 'POST':
        return HttpResponse(status=405)
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    try:
        count = int(request.POST.get('count', '25'))
    except ValueError:
        count = 25
    count = max(1, min(count, 100))

    from appauth.models import UserProfile
    created = 0
    attempts = 0
    while created < count and attempts < count * 10:
        attempts += 1
        code = _generate_allocation_code(10)
        try:
            lc = AllocationLoginCode.objects.create(question=question, code=code)
            uname = f"acode_{question.id}_{secrets.token_hex(4)}"
            u = User(username=uname, email="")
            u.set_unusable_password()
            u.is_active = True
            u.save()
            if not hasattr(u, 'userprofile'):
                UserProfile.objects.create(
                    user=u,
                    displayPref=1,
                    time_creation=timezone.now(),
                    salt="",
                    is_code_user=True,
                    code_source='allocation',
                )
            lc.user = u
            lc.save(update_fields=['user'])
            question.question_voters.add(u)
            created += 1
        except Exception:
            continue

    messages.success(request, f"Created {created} login codes.")
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationExportCodes(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    codes = question.login_codes.order_by('created_at').values_list('code', flat=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['code'])
    for c in codes:
        w.writerow([c])
    buf.seek(0)
    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="opra_alloc{question_id}_codes.csv"'
    return resp


def allocationDeleteUserVotes(request, response_id):
    response = get_object_or_404(AllocationResponse, pk=response_id)
    user = response.user
    question = response.question
    if user:
        question.allocationresponse_set.filter(user=user).update(active=0)
    request.session['setting'] = 6
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationRestoreUserVotes(request, response_id):
    response = get_object_or_404(AllocationResponse, pk=response_id)
    user = response.user
    question = response.question
    if user:
        question.allocationresponse_set.filter(user=user, active=0).update(active=1)
    request.session['setting'] = 7
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationSendEmailInvites(request, question_id):
    from django.core import mail as django_mail
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    recepients = request.POST.get('recepients', 'allVoters')
    mail_subject = request.POST.get('mailSubject', '').strip()
    mail_body = request.POST.get('mailBody', '').strip()
    csv_custom = request.POST.get('textAreaForCustomMails', '')
    custom_emails = [e.strip() for e in csv_custom.split(',') if e.strip()]

    registered_voters = list(question.question_voters.all())
    recent_csv = question.recentCSVText or ''
    csv_ids = [x.strip() for x in recent_csv.split(',') if x.strip()]
    reg_usernames = [u.username for u in registered_voters]
    unreg_ids = [uid for uid in csv_ids if uid not in reg_usernames]

    if recepients == 'regVotersOnly':
        recipients = [u.email for u in registered_voters if u.email]
    elif recepients == 'unregVotersOnly':
        recipients = unreg_ids
    elif recepients == 'customEmails':
        recipients = custom_emails
    else:
        recipients = [u.email for u in registered_voters if u.email] + unreg_ids

    if not recipients:
        messages.error(request, "No recipients found to send email.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    if not mail_subject or not mail_body:
        messages.error(request, "Email subject and body are required.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    try:
        django_mail.send_mail(
            subject=mail_subject,
            message=mail_body,
            from_email='opra@cs.binghamton.edu',
            recipient_list=recipients,
            fail_silently=True,
        )
        messages.success(request, "The Email has been sent to the recipients!")
    except Exception:
        messages.error(request, "Failed to send email. Please check your mail settings.")

    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def startAllocation(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('allocation:allocation_tab'))
    question.status = 2
    question.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def pauseAllocation(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('allocation:allocation_tab'))
    question.status = 4
    question.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def resumeAllocation(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('allocation:allocation_tab'))
    for item in question.allocationitem_set.all():
        if item.recently_added:
            item.recently_added = False
            item.save()
    question.status = 2
    question.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def stopAllocation(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('allocation:allocation_tab'))
    question.status = 3
    getFinalAllocation(question)
    question.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def deleteAllocation(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('allocation:allocation_tab'))
    question.delete()
    return HttpResponseRedirect(reverse('allocation:allocation_tab'))


# ── Settings ──────────────────────────────────────────────────────────────────

def allocationSetInitialSettings(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32}

    selected_idx = int(request.POST.get("pollpreferences", "1"))
    question.poll_algorithm = BIT_MAP.get(selected_idx, 1)

    if "viewpreferences" in request.POST:
        question.display_pref = request.POST["viewpreferences"]
    if "viewuserinfo" in request.POST:
        question.display_user_info = request.POST["viewuserinfo"]
    if "creatorpreferences" in request.POST:
        question.creator_pref = request.POST["creatorpreferences"]

    open_string = request.POST.get("openpoll", "anon")
    signup_string = request.POST.get("selfsignup", "allow")

    uilist = request.POST.getlist("ui")
    question.twocol_enabled = "twocol" in uilist
    question.onecol_enabled = "onecol" in uilist
    question.slider_enabled = "slider" in uilist
    question.star_enabled = "star" in uilist
    question.yesno_enabled = "yesno" in uilist
    question.budgetUI_enabled = "BUI_slider" in uilist
    question.ListUI_enabled = "LUI" in uilist
    question.infiniteBudgetUI_enabled = "IBUI" in uilist
    question.ui_number = sum([
        question.twocol_enabled, question.onecol_enabled,
        question.slider_enabled, question.star_enabled, question.yesno_enabled,
        question.budgetUI_enabled, question.ListUI_enabled,
        question.infiniteBudgetUI_enabled,
    ])

    posted_tables = request.POST.getlist("alloc_res_tables")
    question.alloc_res_tables = sum(int(v) for v in posted_tables) if posted_tables else 6

    posted_algs = request.POST.getlist("alloc_algorithms")
    question.alloc_algorithms = sum(int(v) for v in posted_algs)

    if "results_visible_after" in request.POST:
        raw = request.POST["results_visible_after"].strip()
        question.results_visible_after = parse_datetime(raw) if raw else None

    question.open = 1 if open_string == "anon" else (0 if open_string == "invite" else 2)
    question.allow_self_sign_up = 1 if signup_string == "allow" else 0

    question.save()
    return HttpResponseRedirect(reverse("allocation:allocation_tab"))


def allocationSetPollingSettings(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32}

    if 'pollpreferences' in request.POST:
        question.poll_algorithm = BIT_MAP.get(int(request.POST['pollpreferences']), 1)

    posted_algs = request.POST.getlist('alloc_algorithms')
    question.alloc_algorithms = sum(int(v) for v in posted_algs)

    posted_tables = request.POST.getlist('alloc_res_tables')
    question.alloc_res_tables = sum(int(v) for v in posted_tables)

    question.save()
    messages.success(request, "Allocation settings have been updated.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationSetVisibilitySettings(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if "viewpreferences" in request.POST:
        question.display_pref = request.POST['viewpreferences']
    if "viewuserinfo" in request.POST:
        question.display_user_info = request.POST['viewuserinfo']
    if "creatorpreferences" in request.POST:
        question.creator_pref = request.POST['creatorpreferences']
    results_visible_after = request.POST.get('results_visible_after', '').strip()
    if results_visible_after:
        from django.utils.dateparse import parse_datetime
        question.results_visible_after = parse_datetime(results_visible_after)
    else:
        question.results_visible_after = None
    question.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Poll info (settings page) ─────────────────────────────────────────────────

@method_decorator(block_code_users("/allocations/allocation_tab/code"), name="dispatch")
class AllocationPollInfoView(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/pollinfo.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        curr_question = self.object
        ctx['users'] = User.objects.filter(userprofile__is_code_user=False)
        ctx['items'] = curr_question.allocationitem_set.all()
        ctx['groups'] = Group.objects.all()
        ctx['alloc_methods'] = getAllocMethods()

        current_user_responses = curr_question.allocationresponse_set.filter(
            user=self.request.user, active=1
        ).order_by('-timestamp')
        if current_user_responses.count() > 0:
            ctx['user_latest_responses'] = getSelectionListAlloc([current_user_responses[0]])
            ctx['user_latest_responses'] = addPreferenceValueToRespAlloc(ctx['user_latest_responses'])

        ctx['user_previous_responses'] = getSelectionListAlloc(list(current_user_responses[1:]))
        ctx['user_previous_responses'] = addPreferenceValueToRespAlloc(ctx['user_previous_responses'])

        all_responses = curr_question.allocationresponse_set.filter(active=1).order_by('-timestamp')
        (latest, previous) = categorizeResponses(all_responses)
        ctx['latest_responses'] = addPreferenceValueToRespAlloc(getSelectionListAlloc(latest))
        ctx['previous_responses'] = addPreferenceValueToRespAlloc(getSelectionListAlloc(previous))

        deleted = curr_question.allocationresponse_set.filter(active=0).order_by('-timestamp')
        (latest_del, prev_del) = categorizeResponses(deleted)
        ctx['latest_deleted_resps'] = addPreferenceValueToRespAlloc(getSelectionListAlloc(latest_del))
        ctx['previous_deleted_resps'] = addPreferenceValueToRespAlloc(getSelectionListAlloc(prev_del))

        if curr_question.question_voters.all().count() > 0:
            ctx['progressPercentage'] = (len(latest) / curr_question.question_voters.all().count()) * 100

        ctx['selected_alloc_res_tables_sum'] = curr_question.alloc_res_tables
        ctx['recentCSVText'] = curr_question.recentCSVText
        ctx['request_list'] = curr_question.allocationsignuprequest_set.filter(status=1)

        from .email import setupAllocationEmail
        setupAllocationEmail(curr_question)
        if AllocationEmail.objects.filter(question=curr_question).count() > 0:
            ctx['emailInvite'] = AllocationEmail.objects.filter(question=curr_question, type=1)[0]
            ctx['emailDelete'] = AllocationEmail.objects.filter(question=curr_question, type=2)[0]
            ctx['emailStart'] = AllocationEmail.objects.filter(question=curr_question, type=3)[0]
            ctx['emailStop'] = AllocationEmail.objects.filter(question=curr_question, type=4)[0]
            ctx['emailInviteCSV'] = AllocationEmail.objects.filter(question=curr_question, type=5)[0]

        # registeredUsers = CSV entries that match a real (non-code) OPRA user
        # unRegisteredUsers = CSV entries with no matching OPRA account
        # mirrors polls' getUsersFromLatestCSV logic using ctx['users'] (is_code_user=False)
        real_usernames = {u.username for u in ctx['users']}
        registered, unregistered = [], []
        if curr_question.recentCSVText:
            csv_ids = [x.strip() for x in curr_question.recentCSVText.split(',') if x.strip()]
            for uid in csv_ids:
                if uid in real_usernames:
                    registered.append(uid)
                else:
                    unregistered.append(uid)
        ctx['registeredUsers'] = registered
        ctx['unRegisteredUsers'] = unregistered

        return ctx

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())


# ── Voting ────────────────────────────────────────────────────────────────────

class AllocationDetailView(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/detail.html'
    context_object_name = 'question'

    def get_order(self, ctx):
        default_order = list(ctx['object'].allocationitem_set.all())
        random.shuffle(default_order)
        return default_order

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lastcomment'] = ""

        current_user_responses = self.object.allocationresponse_set.filter(
            user=self.request.user, active=1
        ).reverse()

        if len(current_user_responses) > 0:
            ctx['submitted_ranking'] = current_user_responses[0].behavior_data
            if current_user_responses[0].comment:
                ctx['lastcomment'] = current_user_responses[0].comment

        ctx['vote_url'] = reverse('allocation:vote', args=(self.object.id,))

        if isPrefReset(self.request):
            ctx['items'] = self.get_order(ctx)
            return ctx

        if len(current_user_responses) > 0:
            ctx['currentSelection'] = getCurrentSelectionAlloc(current_user_responses[0])
            ctx['itr'] = itertools.count(1, 1)
            ctx['unrankedCandidates'] = getUnrankedCandidatesAlloc(current_user_responses[0])
            items = []
            for tier in ctx['currentSelection']:
                items.extend(tier)
            if ctx['unrankedCandidates']:
                items.extend(ctx['unrankedCandidates'])
            ctx['items'] = items
        else:
            ctx['items'] = self.get_order(ctx)

        return ctx

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())


def allocationVote(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    order_str = request.POST["pref_order"]
    pref_order = getPrefOrder(order_str, question)
    behavior_string = request.POST["record_data"]

    if pref_order is None:
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    comment = request.POST.get('comment', '')
    response = AllocationResponse(
        question=question,
        user=request.user,
        timestamp=timezone.now(),
        resp_str=order_str,
        behavior_data=behavior_string,
        active=1,
    )
    if comment:
        response.comment = comment
    response.save()

    prev_count = question.allocationresponse_set.filter(user=request.user, active=1).count()
    if prev_count <= 1:
        messages.success(request, 'Saved!')
    else:
        messages.success(request, 'Updated!')

    return HttpResponseRedirect(reverse('allocation:detail', args=(question.id,)))


class AllocationConfirmationView(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/confirmation.html'


# ── Results views ─────────────────────────────────────────────────────────────

class AllocateResultsView(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/allocationResults/results_page.html'
    context_object_name = 'question'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.results_visible_after and timezone.now() < self.object.results_visible_after:
            return redirect("allocation:allocation_tab")
        return super().get(request, *args, **kwargs)

    def transformSubmittedRankings(self, items, submitted_rankings):
        for entry in submitted_rankings.items():
            key, values = entry
            if len(values) < len(items):
                temp = []
                for j in range(len(values)):
                    for entry in values[j]:
                        temp.append([entry])
                values = temp
                submitted_rankings[key] = values
        return submitted_rankings

    def getPreferencesList(self, pref_set):
        return list(pref_set.values())

    def transformPreferences(self, items, preferences):
        for i in range(len(preferences)):
            if len(preferences[i]) < len(items):
                temp = []
                for j in range(len(preferences[i])):
                    for entry in preferences[i][j]:
                        temp.append([entry])
                preferences[i] = temp
        for i in range(len(preferences)):
            for j in range(len(preferences[i])):
                preferences[i][j] = preferences[i][j][0]
        return preferences

    def transformAllocatedItems(self, allocated_items):
        transformed = [
            ["" for _ in range(len(allocated_items[i]))]
            for i in range(len(allocated_items))
        ]
        for i in range(len(allocated_items)):
            for j in range(len(allocated_items[i])):
                item_obj = allocated_items[i][j]
            if isinstance(item_obj, str):
                transformed[i][j] = item_obj[4:]
            elif hasattr(item_obj, 'item_text'):
                transformed[i][j] = item_obj.item_text
            else:
                transformed[i][j] = str(item_obj)
        return transformed

    def getSumOfAllocatedItems(self, allocated_items, submitted_rankings):
        sum_of_alloc_items_values = []
        allocated_items_with_values = []
        for i in range(len(allocated_items)):
            sum_of_values = 0
            items_with_values = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(allocated_items[i])):
                for k in range(len(submitted_rankings_values)):
                    if "score" in submitted_rankings_values[k][0]:
                        if submitted_rankings_values[k][0]["name"] == allocated_items[i][j]:
                            sum_of_values += submitted_rankings_values[k][0]["score"]
                            items_with_values.append((
                                submitted_rankings_values[k][0]["name"][4:],
                                submitted_rankings_values[k][0]["score"]
                            ))
            sum_of_alloc_items_values.append(sum_of_values)
            allocated_items_with_values.append(items_with_values)
        return allocated_items_with_values, sum_of_alloc_items_values

    def formatOptions(self, items):
        return [item[4:] for item in items]

    def getPrefWithValues(self, submitted_rankings):
        preferences_with_values = []
        for i in range(len(submitted_rankings)):
            curr = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(submitted_rankings_values)):
                if "score" in submitted_rankings_values[j][0]:
                    curr.append([
                        submitted_rankings_values[j][0]["name"][4:],
                        submitted_rankings_values[j][0]["score"]
                    ])
            preferences_with_values.append(curr)
        return preferences_with_values

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        question = self.object

        if not question.allocationresponse_set.exists():
            ctx['error_message'] = "No responses found. Users must submit preferences before viewing allocations."
            return ctx

        mechanism_info = self._prepare_mechanism_info(question)
        ctx.update(mechanism_info)

        user_data = self._prepare_user_data(question)
        ctx.update(user_data)

        current_user_id = self.request.user.id
        current_user_name = user_data['user_names'].get(current_user_id, "")
        ctx['current_user_name'] = current_user_name
        ctx['empty_string'] = ""

        curr_user_ranking = user_data['submitted_rankings'].get(current_user_id, [])
        ctx['curr_user_pref'] = []
        ctx['curr_user_pref_values'] = []
        for entry in curr_user_ranking:
            if not entry:
                continue
            val = entry[0]
            if isinstance(val, dict) and 'name' in val:
                ctx['curr_user_pref'].append(val['name'][4:])
                ctx['curr_user_pref_values'].append(val.get('score', 0))
            elif isinstance(val, str):
                ctx['curr_user_pref'].append(val[4:])
                ctx['curr_user_pref_values'].append(0)

        context_data = {
            'question_id': question.id,
            'mechanism_id': ctx['current_mechanism_id'],
            'preferences': user_data['preferences'],
            'sorted_user_ids': user_data['sorted_user_ids']
        }

        allocation_result, is_cache_hit = self._get_allocation_result(
            context_data, ctx['chosen_cls'], ctx['chosen_label']
        )
        ctx.update(allocation_result)

        if question.alloc_res_tables & 2 != 0:
            ctx["all_user_preferences"] = self._format_user_preferences(
                user_data['sorted_user_ids'],
                user_data['user_names'],
                user_data['submitted_rankings']
            )

        ctx["is_pareto_optimal"] = False
        if allocation_result.get('allocation_matrix') is not None and user_data.get('preferences'):
            try:
                V = np.array(user_data['preferences'])
                A = np.array(allocation_result['allocation_matrix'])
                ctx["is_pareto_optimal"] = is_po(V, A)
            except Exception as e:
                logger.warning("is_PO check failed: %s", e)

        sum_values = allocation_result.get('sum_of_alloc_items_values', [])
        if sum_values:
            ctx["utilitarian_welfare"] = sum(sum_values)
            ctx["egalitarian_welfare"] = min(sum_values)

        item_texts = []
        current_user_index = None
        user_alloc_items = []
        if allocation_result.get('allocated_items') and user_data.get('preferences'):
            preferences_with_values = self.getPrefWithValues(user_data['submitted_rankings'])
            allocated_items_with_values, _ = self.getSumOfAllocatedItems(
                self.transformAllocatedItems(allocation_result['allocated_items']),
                user_data['submitted_rankings']
            )
            envy_matrix = computeEnvyUptoEF1(
                user_data['preferences'],
                allocated_items_with_values,
                preferences_with_values
            )
            ctx['envy_matrix'] = envy_matrix

            items_obj = allocation_result.get("items_obj", [])
            sorted_user_ids = user_data["sorted_user_ids"]
            item_texts = [item.item_text for item in items_obj]

            if current_user_id in sorted_user_ids:
                current_user_index = sorted_user_ids.index(current_user_id)
                user_alloc_items = allocation_result['allocated_items'][current_user_index] \
                    if current_user_index < len(allocation_result['allocated_items']) else []
                ctx["curr_user_bundle"] = user_alloc_items

            if current_user_index is not None and current_user_index < len(user_data['preferences']):
                raw_ranking = user_data['submitted_rankings'].get(sorted_user_ids[current_user_index], [])
                ranking_dict = {}
                for entry in raw_ranking:
                    if entry and isinstance(entry[0], dict):
                        name = entry[0].get('name', '')
                        if name.startswith("item"):
                            ranking_dict[name[4:]] = entry[0].get('score', 0)
                total_value = sum(ranking_dict.get(item.item_text, 0) for item in user_alloc_items)
                ctx["curr_user_bundle_sum"] = total_value
            else:
                ctx["curr_user_bundle_sum"] = 0

        rank_histogram = [0] * len(item_texts)
        if allocation_result.get('allocation_matrix') is not None and item_texts:
            allocation_matrix = allocation_result['allocation_matrix']
            sorted_user_ids = user_data['sorted_user_ids']
            items_obj = allocation_result.get("items_obj", [])
            item_texts = [item.item_text for item in items_obj]
            rank_histogram = [0] * len(item_texts)
            for i, row in enumerate(allocation_matrix):
                user_id = sorted_user_ids[i]
                raw_pref = user_data['submitted_rankings'].get(user_id, [])
                ranked_items = []
                for entry in raw_pref:
                    if isinstance(entry[0], dict):
                        name = entry[0].get("name", "")[4:]
                        score = entry[0].get("score", 0)
                        ranked_items.append((name, score))
                ranked_items.sort(key=lambda x: -x[1])
                item_to_rank = {name: rank for rank, (name, _) in enumerate(ranked_items)}
                for j, alloc in enumerate(row):
                    if alloc == 1:
                        item_name = item_texts[j]
                        if item_name in item_to_rank:
                            rank_histogram[item_to_rank[item_name]] += 1

        ctx["rank_histogram"] = rank_histogram
        return ctx

    def _prepare_mechanism_info(self, question):
        locked_alg_id = question.poll_algorithm
        alg_bitmask = question.alloc_algorithms

        all_mechanisms = [
            (1, "Round Robin", MechanismRoundRobinAllocation),
            (2, "Max Nash Welfare", MechanismMaximumNashWelfare),
            (4, "Market (EF1)", MechanismMarketAllocation),
            (8, "MarketEq (EQ1)", MechanismMarketEqAllocation),
            (16, "Leximin", MechanismLeximinAllocation),
            (32, "MNW Binary", MechanismMaximumNashWelfareBinary),
        ]

        available_mechanisms = [
            (bit, label) for (bit, label, cls) in all_mechanisms if (alg_bitmask & bit) != 0
        ]
        if not available_mechanisms:
            available_mechanisms = [(1, "Round Robin")]

        requested_alg = self.request.GET.get("alg", None)
        if requested_alg is not None:
            try:
                requested_bit = int(requested_alg)
                current_mechanism_id = requested_bit if (alg_bitmask & requested_bit) != 0 else locked_alg_id
            except ValueError:
                current_mechanism_id = locked_alg_id
        else:
            current_mechanism_id = locked_alg_id

        chosen_cls = MechanismRoundRobinAllocation
        chosen_label = "Round Robin"
        for (bit, label, cls) in all_mechanisms:
            if bit == current_mechanism_id:
                chosen_cls = cls
                chosen_label = label
                break

        return {
            "available_mechanisms": available_mechanisms,
            "current_mechanism_id": current_mechanism_id,
            "current_mechanism": chosen_label,
            "chosen_cls": chosen_cls,
            "chosen_label": chosen_label,
            "selected_alloc_res_tables_sum": question.alloc_res_tables,
        }

    def _prepare_user_data(self, question):
        response_set = question.allocationresponse_set.all()
        user_names = {}
        user_pics = {}
        submitted_rankings = {}

        for resp in response_set:
            uid = resp.user_id
            if uid not in user_names:
                user_names[uid] = resp.user.first_name
                pic_path = resp.user.userprofile.profile_pic.name
                user_pics[uid] = f"/{pic_path}" if pic_path else ""
            submitted_rankings[uid] = json.loads(resp.behavior_data)["submitted_ranking"]

        sorted_user_ids = sorted(user_names.keys())
        preferences = self._extract_numeric_preferences(
            response_set, sorted_user_ids, question.allocationitem_set.count()
        )

        return {
            "candidates": [user_names[uid] for uid in sorted_user_ids],
            "profile_pics": [user_pics[uid] for uid in sorted_user_ids],
            "user_names": user_names,
            "submitted_rankings": submitted_rankings,
            "sorted_user_ids": sorted_user_ids,
            "preferences": preferences,
            "current_user_id": self.request.user.id,
        }

    def _extract_numeric_preferences(self, response_set, sorted_user_ids, item_count):
        user_valuations_map = {}
        for resp in response_set:
            uid = resp.user_id
            raw_list = ast.literal_eval(resp.resp_str)
            behavior_dict = json.loads(resp.behavior_data or '{}')
            submitted_scores = behavior_dict.get("submitted_ranking", [])
            item_score_map = {}
            for group in submitted_scores:
                if group and isinstance(group[0], dict):
                    name = group[0].get("name", "")
                    score = group[0].get("score", 0)
                    item_score_map[name] = score
            numeric_vals = []
            for sublist in raw_list:
                for x in sublist:
                    if isinstance(x, str):
                        name = x
                    elif isinstance(x, dict) and "name" in x:
                        name = x["name"]
                    else:
                        name = None
                    val = item_score_map.get(name, 0.0) if name else 0.0
                    numeric_vals.append(val)
            user_valuations_map[uid] = numeric_vals

        for uid in sorted_user_ids:
            if uid not in user_valuations_map or not user_valuations_map[uid]:
                user_valuations_map[uid] = [0.0] * item_count

        max_length = max(len(v) for v in user_valuations_map.values()) if user_valuations_map else item_count
        for uid in user_valuations_map:
            if len(user_valuations_map[uid]) < max_length:
                user_valuations_map[uid] += [0.0] * (max_length - len(user_valuations_map[uid]))

        return [user_valuations_map.get(uid, [0.0] * max_length) for uid in sorted_user_ids]

    def _process_allocation_result(self, result, preferences, sorted_user_ids, question_id):
        question = AllocationQuestion.objects.get(id=question_id) if question_id else None
        items = list(question.allocationitem_set.all()) if question else []
        allocation_matrix = result.A

        allocation_data = {'allocation_matrix': allocation_matrix, 'items_obj': items}
        allocated_items = []
        if allocation_matrix is not None:
            N = len(allocation_matrix)
            if N > 0:
                M = len(allocation_matrix[0])
                for i in range(N):
                    user_items = []
                    for j in range(M):
                        if allocation_matrix[i][j] == 1:
                            if j < len(items):
                                user_items.append(items[j])
                            else:
                                user_items.append({'item_text': f"Item #{j}", 'id': -1})
                    allocated_items.append(user_items)
        allocation_data['allocated_items'] = allocated_items

        sum_values = []
        for i, prefs in enumerate(preferences):
            if i < len(allocation_matrix):
                utility = sum(prefs[j] * allocation_matrix[i][j] for j in range(len(prefs)))
                sum_values.append(utility)
        allocation_data['sum_of_alloc_items_values'] = sum_values
        return allocation_data

    def _get_allocation_result(self, context_data, mechanism_class, mechanism_label):
        cached_result, is_hit = AllocationCache.get_cached_result(context_data)
        if is_hit:
            logger.info("Cache hit for mechanism %s", mechanism_label)
            return self._process_cached_allocation_data(cached_result), True

        logger.info("Cache miss for %s, computing", mechanism_label)
        start_time = timezone.now()
        try:
            mechanism = mechanism_class()
            result = mechanism.allocate(valuations=context_data['preferences'])
            allocation_data = self._process_allocation_result(
                result,
                context_data['preferences'],
                context_data['sorted_user_ids'],
                context_data.get('question_id')
            )
            AllocationCache.store_result(context_data, allocation_data)
            logger.info("Computed in %.2fs", (timezone.now() - start_time).total_seconds())
            return allocation_data, False
        except Exception as e:
            logger.error("Error computing allocation with %s: %s", mechanism_label, e, exc_info=True)
            n = len(context_data['preferences'])
            m = max(len(p) for p in context_data['preferences']) if context_data['preferences'] else 0
            return {
                'error_message': f"Could not compute allocation: {e}",
                'allocation_matrix': np.zeros((n, m)),
                'allocated_items': [[] for _ in range(n)],
                'sum_of_alloc_items_values': [0] * n,
            }, False

    def _format_user_preferences(self, sorted_user_ids, user_names, submitted_rankings):
        result = []
        for uid in sorted_user_ids:
            username = user_names[uid]
            ranking = submitted_rankings[uid]
            cleaned = []
            for group in ranking:
                if group and isinstance(group[0], dict):
                    cleaned.append(group[0].get("name", "")[4:])
            result.append((username, cleaned))
        return result

    def _process_cached_allocation_data(self, cached_result, question_id=None):
        if not question_id:
            question_id = self.kwargs.get('pk')
        question = AllocationQuestion.objects.get(id=question_id)
        items = list(question.allocationitem_set.all())
        cached_result['items_obj'] = items
        if 'allocated_items' in cached_result:
            for i, agent_items in enumerate(cached_result['allocated_items']):
                for j, item_data in enumerate(agent_items):
                    if isinstance(item_data, dict) and 'id' in item_data and item_data['id'] > 0:
                        for item in items:
                            if item.id == item_data['id']:
                                cached_result['allocated_items'][i][j] = item
                                break
        return cached_result


# ── Allocation order ──────────────────────────────────────────────────────────

class AllocationOrder(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/allocation_order.html'

    def get_queryset(self):
        return AllocationQuestion.objects.filter(pub_date__lte=timezone.now())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        current_order = self.object.allocationvoter_set.all()
        temp_order_str = self.request.GET.get('order', '')
        if temp_order_str == "null":
            ctx['question_voters'] = self.object.question_voters.all()
            return ctx
        if len(current_order) > 0:
            ctx['currentSelection'] = current_order
        ctx['question_voters'] = self.object.question_voters.all()
        return ctx


def setAllocationOrder(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    order_str = request.POST["pref_order"]
    if not order_str:
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    pref_order = order_str.split(",")
    if len(pref_order) != question.question_voters.all().count():
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    for voter in question.allocationvoter_set.all():
        voter.delete()

    item_num = 1
    for item in question.question_voters.all():
        array_index = pref_order.index("item" + str(item_num))
        if array_index != -1:
            user = question.question_voters.all()[array_index]
            voter, created = AllocationVoter.objects.get_or_create(
                question=question, user=user, response=None
            )
            voter.save()
        item_num += 1

    return HttpResponseRedirect(reverse('allocation:viewAllocationOrder', args=(question.id,)))


# ── Item bulk operations ──────────────────────────────────────────────────────

def allocation_delete_items(request, question_id):
    """Delete selected or all items from an allocation."""
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        messages.error(request, "Only the allocation owner can delete alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    if request.method == 'POST':
        if 'delete_all' in request.POST:
            question.allocationitem_set.all().delete()
            messages.success(request, "All items have been deleted.")
        else:
            import json as _json
            item_ids = _json.loads(request.POST.get('item_ids', '[]'))
            question.allocationitem_set.filter(id__in=item_ids).delete()
            messages.success(request, f"{len(item_ids)} items have been deleted.")
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocation_upload_csv_choices(request, question_id):
    """Handle CSV file upload to add multiple allocation items at once."""
    from io import TextIOWrapper
    import csv as _csv
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        messages.error(request, "Only the allocation owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    if request.method == 'POST' and request.FILES.get('csvFile'):
        csv_file = request.FILES['csvFile']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a CSV file.")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        try:
            csv_text = TextIOWrapper(csv_file.file, encoding='utf-8')
            csv_reader = _csv.reader(csv_text)
            items_added = 0
            items_skipped = 0
            is_header = False
            for i, row in enumerate(csv_reader):
                if not row or not row[0].strip():
                    continue
                item_name = row[0].strip()
                item_description = row[1].strip() if len(row) > 1 else ''
                item_reference = row[2].strip() if len(row) > 2 else ''
                if i == 0 and not any(c.isdigit() for c in item_name):
                    is_header = True
                    continue
                if question.allocationitem_set.filter(item_text=item_name).exists():
                    items_skipped += 1
                    continue
                AllocationItem(
                    question=question,
                    item_text=item_name,
                    item_description=item_description,
                    imageReference=item_reference,
                    timestamp=timezone.now(),
                    recently_added=(question.status != 1),
                ).save()
                items_added += 1
            if is_header:
                messages.info(request, "Detected and skipped header row.")
            if items_added > 0:
                messages.success(request, f"Successfully added {items_added} items.")
            if items_skipped > 0:
                messages.warning(request, f"Skipped {items_skipped} duplicate items.")
        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocation_upload_bulk_images(request, question_id):
    """Handle bulk image upload matched by imageReference field."""
    import os as _os
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        messages.error(request, "Only the allocation owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    if request.method == 'POST' and request.FILES.getlist('imageFiles'):
        try:
            image_files = request.FILES.getlist('imageFiles')
            all_items = question.allocationitem_set.all()
            images_matched = 0
            images_unmatched = 0
            for image_file in image_files:
                matching = all_items.filter(imageReference=image_file.name)
                if not matching.exists():
                    base_name = _os.path.splitext(image_file.name)[0]
                    matching = all_items.filter(imageReference=base_name)
                if matching.exists():
                    for item in matching:
                        item.image = image_file
                        item.save()
                        images_matched += 1
                else:
                    images_unmatched += 1
            if images_matched > 0:
                messages.success(request, f"Successfully attached {images_matched} images to existing items.")
            if images_unmatched > 0:
                messages.warning(request, f"Could not match {images_unmatched} images to any existing items.")
        except Exception as e:
            messages.error(request, f"Error processing image files: {str(e)}")
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocation_upload_single_image(request, question_id):
    """Handle single image upload for an existing allocation item."""
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.user != question.question_owner:
        messages.error(request, "Only the allocation owner can modify items.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    if request.method == 'POST' and 'image' in request.FILES:
        try:
            image_file = request.FILES['image']
            item_id = request.POST.get('item_id')
            item = AllocationItem.objects.get(pk=item_id, question=question)
            item.image = image_file
            item.save()
            messages.success(request, f"Successfully updated image for '{item.item_text}'.")
        except AllocationItem.DoesNotExist:
            messages.error(request, "The specified item was not found.")
        except Exception as e:
            messages.error(request, f"Error processing image: {str(e)}")
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Duplicate ─────────────────────────────────────────────────────────────────

def allocationDuplicatePoll(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    new_question = AllocationQuestion(
        question_text=question.question_text,
        question_desc=question.question_desc,
        pub_date=timezone.now(),
        question_owner=request.user,
        display_pref=question.display_pref,
        display_user_info=question.display_user_info,
        creator_pref=question.creator_pref,
        emailInvite=question.emailInvite,
        emailDelete=question.emailDelete,
        emailStart=question.emailStart,
        emailStop=question.emailStop,
        emailInviteCSV=question.emailInviteCSV,
        poll_algorithm=question.poll_algorithm,
        alloc_algorithms=question.alloc_algorithms,
        alloc_res_tables=question.alloc_res_tables,
        first_tier=question.first_tier,
        utility_model=question.utility_model,
        open=question.open,
        allow_self_sign_up=question.allow_self_sign_up,
        twocol_enabled=question.twocol_enabled,
        onecol_enabled=question.onecol_enabled,
        slider_enabled=question.slider_enabled,
        star_enabled=question.star_enabled,
        yesno_enabled=question.yesno_enabled,
        budgetUI_enabled=question.budgetUI_enabled,
        ListUI_enabled=question.ListUI_enabled,
        infiniteBudgetUI_enabled=question.infiniteBudgetUI_enabled,
    )
    new_question.save()
    new_question.question_voters.add(*question.question_voters.all())
    for item in question.allocationitem_set.all():
        AllocationItem.objects.create(
            question=new_question,
            item_text=item.item_text,
            item_description=item.item_description,
            timestamp=timezone.now(),
            image=item.image,
            imageURL=item.imageURL,
        )
    from .email import setupAllocationEmail
    setupAllocationEmail(new_question)
    messages.success(request, f"'{question.question_text}' has been duplicated.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Access management ─────────────────────────────────────────────────────────

def allocationChangeType(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    open_string = request.POST['openpoll']
    if open_string == "anon":
        question.open = 1
    elif open_string == "invite":
        question.open = 0
    else:
        question.open = 2
    question.save()
    request.session['setting'] = 4
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationChangeSelfsignup(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    signup_string = request.POST["selfsignup"]
    question.allow_self_sign_up = 1 if signup_string == "allow" else 0
    question.save()
    request.session['setting'] = 4
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def _check_duplicate_allocation_sign_up(user, question):
    for item in question.allocationitem_set.all():
        if str(user.id) == item.self_sign_up_user_id:
            return True
    for r in question.allocationsignuprequest_set.filter(status=1):
        if user == r.user:
            return True
    return False


class AllocationSelfRegisterView(views.generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/self_register.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if _check_duplicate_allocation_sign_up(self.request.user, self.object):
            ctx['submitted'] = True
        return ctx


def allocationSelfSignup(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    if request.method == "POST" and request.user != question.question_owner:
        if _check_duplicate_allocation_sign_up(request.user, question):
            return HttpResponse("You can only register once!")
        item_name = request.POST['item_name']
        AllocationSignUpRequest.objects.create(
            question=question, user=request.user,
            item_name=item_name, timestamp=timezone.now()
        )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationApproveRequest(request, request_id):
    sign_up_request = get_object_or_404(AllocationSignUpRequest, pk=request_id)
    question = sign_up_request.question
    if question.status != 1 and question.status != 4:
        return HttpResponse("Please pause the allocation first.")
    sign_up_request.status = 2
    sign_up_request.save()
    item_text = sign_up_request.item_name
    for item in question.allocationitem_set.all():
        if item_text == item.item_text:
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    recently_added = question.status == 4
    AllocationItem.objects.create(
        question=question, item_text=item_text,
        timestamp=timezone.now(), recently_added=recently_added,
        self_sign_up_user_id=str(sign_up_request.user.id)
    )
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# ── Search API ────────────────────────────────────────────────────────────────

def get_allocation_polls(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') != 'XMLHttpRequest':
        return HttpResponse('fail', content_type='application/json')

    q = request.GET.get('term', '')
    polls = list(
        AllocationQuestion.objects.filter(
            question_owner=request.user, m_poll=False, question_text__icontains=q
        ).order_by('-pub_date')
    )
    polls += list(
        request.user.allocation_participated.filter(
            m_poll=False, question_text__icontains=q
        ).exclude(question_owner=request.user).order_by('-pub_date')
    )
    polls = polls[:20]

    results = []
    for poll in polls:
        results.append({
            'id': poll.id,
            'label': poll.question_text,
            'value': poll.question_text,
            'desc': poll.question_desc or 'None',
            'status': poll.status,
            'created': request.user == poll.question_owner,
            'voter': request.user in poll.question_voters.all(),
        })
    return HttpResponse(json.dumps(results), content_type='application/json')


def get_allocation_voters(request):
    if request.META.get('HTTP_X_REQUESTED_WITH') != 'XMLHttpRequest':
        return HttpResponse('fail', content_type='application/json')

    q = request.GET.get('term', '')
    question_id = request.GET.get('poll_id', '-1')
    users = User.objects.filter(username__icontains=q, userprofile__is_code_user=False)
    if question_id != '-1':
        try:
            question = AllocationQuestion.objects.get(pk=question_id)
            existing = question.question_voters.all()
        except AllocationQuestion.DoesNotExist:
            existing = []
    else:
        existing = []

    results = []
    count = 0
    for user in users:
        if count == 20:
            break
        if user in existing:
            continue
        results.append({'id': user.id, 'label': user.username, 'value': user.username})
        count += 1
    return HttpResponse(json.dumps(results), content_type='application/json')
