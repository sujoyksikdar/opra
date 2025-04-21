from .models import *
from appauth.models import *
from groups.models import *
import datetime
import os
import time
import collections

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect, HttpResponse, HttpRequest
from django.urls import reverse
from django import views
from django.db.models import Q

from django.utils import timezone
from django.core.cache import cache
from django.template import RequestContext
from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core import mail
from prefpy.mechanism import *
from prefpy.gmm_mixpl import *
from prefpy.egmm_mixpl import *
from .email import EmailThread, emailSettings, setupEmail
from django.conf import settings
from multipolls.models import *
from prefpy.allocation_properties import is_po

from . import opra_crypto
import json
import threading
import itertools
import numpy as np
import pandas as pd
import random
import csv
import ast
import hashlib
import logging

# logger for cache
logger = logging.getLogger(__name__)
from io import TextIOWrapper

active_polls = []

class IndexView(views.generic.ListView):
    """
    Define homepage view, inheriting ListView class, which specifies a context variable.
    
    Note that login is required to view the items on the page.
    """
    
    template_name = 'polls/index2.html'
    context_object_name = 'question_list'
    def get_queryset(self):
        """Override function in parent class and return all questions."""
        
        return Question.objects.all().order_by('-pub_date')


class RegularPollsView(views.generic.ListView):
    """
    Define regular polls view, inheriting ListView class, which specifies a context variable.
    
    The variables used in regular polls page are extracted from database and defined below.
    """
    
    template_name = 'polls/regular_polls.html'
    context_object_name = 'question_list'
    def get_queryset(self):
        """Override function in parent class and return all questions."""
        
        return Question.objects.all().order_by('-pub_date')
        
    
    def get_context_data(self, **kwargs):
        """Override function in parent class and define additional context variables to be used in the page."""
        
        
        ctx = super(RegularPollsView, self).get_context_data(**kwargs)
        # get folders
        ctx['folders'] = Folder.objects.filter(user=self.request.user).all()
        unshown = []
        for folder in ctx['folders']:
            unshown += folder.questions.all()
        
        # sort the lists by date (most recent should be at the top)
        ctx['polls_created'] = list(Question.objects.filter(question_owner=self.request.user,
                                    m_poll=False, question_type = 1).order_by('-pub_date'))
        ctx['active_polls'] = list(Question.objects.filter(question_type = 1).order_by('-pub_date'))
        # get all polls current user participates in and filter out those she is the owner of
        polls = self.request.user.poll_participated.filter(m_poll=False, question_type = 1)
        polls = polls.exclude(question_owner=self.request.user).order_by('-pub_date')
        ctx['polls_participated'] = list(polls) # .filter(question_type = 1)
        
        # for polls in folders, do not show them in the main page
        for poll in unshown:
            if poll in ctx['polls_created']:
                ctx['polls_created'].remove(poll)
            elif poll in ctx['polls_participated']:
                ctx['polls_participated'].remove(poll)

        self.request.session['questionType'] = 1
        return ctx
    
class RegularAllocationView(views.generic.ListView):
    """
    Define regular polls view, inheriting ListView class, which specifies a context variable.
    
    The variables used in regular polls page are extracted from database and defined below.
    """
    
    template_name = 'polls/allocation_tab.html'
    context_object_name = 'question_list'
    def get_queryset(self):
        """Override function in parent class and return all questions."""
        
        return Question.objects.all().order_by('-pub_date')
        
    
    def get_context_data(self, **kwargs):
        """Override function in parent class and define additional context variables to be used in the page."""
        
        
        ctx = super(RegularAllocationView, self).get_context_data(**kwargs)
        # get folders
        ctx['folders'] = Folder.objects.filter(user=self.request.user).all()
        unshown = []
        for folder in ctx['folders']:
            unshown += folder.questions.all()
        
        # sort the lists by date (most recent should be at the top)
        ctx['polls_created'] = list(Question.objects.filter(question_owner=self.request.user,
                                    m_poll=False, question_type = 2).order_by('-pub_date'))
        ctx['active_polls'] = list(Question.objects.filter(question_type = 2).order_by('-pub_date'))
        # get all polls current user participates in and filter out those she is the owner of
        polls = self.request.user.poll_participated.filter(m_poll=False, question_type = 2)
        polls = polls.exclude(question_owner=self.request.user).order_by('-pub_date')
        ctx['polls_participated'] = list(polls) # # .filter(question_type = 2)
        
        # for polls in folders, do not show them in the main page
        for poll in unshown:
            if poll in ctx['polls_created']:
                ctx['polls_created'].remove(poll)
            elif poll in ctx['polls_participated']:
                ctx['polls_participated'].remove(poll)

        self.request.session['questionType'] = 2
        return ctx

class RegularPollsFolderView(views.generic.DetailView):
    """Define folder view, inheriting DetailView class, which specifies a specific object."""
    
    template_name = 'polls/regular_polls_folder.html'
    model = Folder
    
    def get_context_data(self, **kwargs):
        """Override function in parent class and define additional context variables to be used in the page."""
        
        ctx = super(RegularPollsFolderView, self).get_context_data(**kwargs)
        ctx['polls_folder'] = self.object.questions.all()
        return ctx


def reverseListOrder(query):
    """Reverse the order in a list."""
    
    list_query = list(query)
    list_query.reverse()
    return list_query

class MultiPollsView(views.generic.ListView):
    """Define multi-poll view, inheriting ListView class, which specifies a context variable. """
    template_name = 'polls/m_polls.html'
    context_object_name = 'question_list'
    def get_queryset(self):
        """Override function in parent class and return all questions."""
        
        return Question.objects.all()
    
    def get_context_data(self, **kwargs):
        """Override function in parent class and define additional context variables to be used in the page."""
        
        ctx = super(MultiPollsView, self).get_context_data(**kwargs)
        # sort the list by date
        m_polls = MultiPoll.objects.filter(owner=self.request.user)
        m_polls_part = self.request.user.multipoll_participated.exclude(owner=self.request.user)
        ctx['multipolls_created'] = reverseListOrder(m_polls)
        ctx['multipolls_participated'] = reverseListOrder(m_polls_part)
        return ctx


class MainView(views.generic.ListView):
    """Define homepage for users that have not logged in."""
    
    template_name = 'polls/index.html'
    context_object_name = 'question_list'
    
    def get_queryset(self):
        """Override function in parent class and return all questions."""
        
        return Question.objects.all().order_by('-pub_date')

    def get_context_data(self, **kwargs):
        """Override function in parent class and define additional context variables to be used in the page."""
        
        ctx = super(MainView, self).get_context_data(**kwargs)
        # sort the list by date
        ctx['preference'] = 1
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['alloc_methods'] = getAllocMethods()
        ctx['view_preferences'] = getViewPreferences()
        ctx['active_polls'] = active_polls
        return ctx


class DemoView(views.generic.DetailView):
    """Define demo poll, which is not used. Need more work on this."""
    
    model = Question
    template_name = 'polls/demo.html'

    def get_order(self, ctx):
        default_order = ctx['object'].item_set.all()
        return default_order

    def get_context_data(self, **kwargs):
        ctx = super(DemoView, self).get_context_data(**kwargs)
        ctx['items'] = self.get_order(ctx)
        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


class CourseMatchListView(views.generic.ListView):
    # view for course match
    """Define course match page for Fall 2025 SoC Course Assignment."""
    template_name = 'events/CourseMatch/soccoursematchlist.html'
    context_object_name = 'question_list'
    def get_queryset(self):
        return Question.objects.all()
    def get_context_data(self, **kwargs):
        ctx = super(CourseMatchListView, self).get_context_data(**kwargs)
        return ctx

class CourseMatchView(views.generic.DetailView):
    model = Question
    template_name = 'events/CourseMatch/soccoursematchdetail.html'
    
    """Define course match preference submission page view."""
    
    def is_student(self, email: str) -> bool:
        print(os.listdir('./'))
        with open('compsocsite/coursematch/StudentEmails.csv', 'r') as f:
            email_list = pd.read_csv(f)['Email Address'].tolist()
            if email in email_list:
                return True
        return False
    
    def get_order_from_email(self, email: str) -> list:
        with open('compsocsite/coursematch/SeedStudentPreferences.json', 'r') as f:
            seed_prefs = json.load(f)
            if email in seed_prefs:
                return seed_prefs[email]
            else:
                return []
    
    def get_random_order(self, ctx) -> list:
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order
    
    def get_order(self, ctx) -> list:
        """Define the initial order to be displayed on the page."""
        
        # default_order = list(ctx['object'].item_set.all())
        user_email = self.request.user.email
        items_dict = {item.item_text: item for item in ctx['object'].item_set.all()}
        print(f'items_dict length {len(items_dict.keys())}')
        print('items_dict.keys()', items_dict.keys())
        default_order = []
        if self.is_student(user_email):
            seed_order = self.get_order_from_email(user_email)
            print(f'seed order length {len(seed_order)}')
            print('seed_order', seed_order)
            if seed_order == []:
                default_order = self.get_random_order(ctx)
            else:
                default_order = []
                for item_text in seed_order:
                    if item_text in items_dict:
                        default_order.append(items_dict[item_text])
        else:
            default_order = self.get_random_order(ctx)
        print(f'default order length {len(default_order)}')
        print('default_order', default_order)
        return default_order
    
    def get_num_courses(self, ctx) -> int:
        """Get the number of courses to display."""
        
        print('in CourseMatchView get_num_courses', ctx['num_courses'])
        return ctx['num_courses']

    def get_context_data(self, **kwargs):
        print('in CourseMatchView get_context_data')
        print(self.request)
        ctx = super(CourseMatchView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""

        #Case for anonymous user
        if self.request.user.get_username() == "":
            if isPrefReset(self.request):
                ctx['items'] = self.object.item_set.all()
                return ctx
            # check the anonymous voter
            if 'anonymousvoter' in self.request.session and 'anonymousid' in self.request.session:
                # sort the responses from latest to earliest
                anon_id = self.request.session['anonymousid']
                curr_anon_resps = self.object.response_set.filter(anonymous_id=anon_id, active=1).reverse()
                if len(curr_anon_resps) > 0:
                    # get the voter's most recent selection
                    mostRecentAnonymousResponse = curr_anon_resps[0]
                    if mostRecentAnonymousResponse.comment:
                        ctx['lastcomment'] = mostRecentAnonymousResponse.comment
                    ctx['currentSelection'] = getCurrentSelection(curr_anon_resps[0])
                    ctx['unrankedCandidates'] = getUnrankedCandidates(curr_anon_resps[0])
                    ctx['itr'] = itertools.count(1, 1)
                    items_ano = []
                    for item in ctx['currentSelection']:
                        for i in item:
                            items_ano.append(i)
                    if not ctx['unrankedCandidates'] == None:
                        for item in ctx['unrankedCandidates']:
                            items_ano.append(item)
                    ctx['items'] = items_ano
            else:
                # load choices in the default order
                ctx['items'] = self.object.item_set.all()
                    # set number of courses to display            
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            ctx['num_courses'] = json.loads(latest_response.behavior_data)['num_courses']
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment
        
        # reset button
        if isPrefReset(self.request):
            ctx['items'] = self.get_order(ctx)
            return ctx

        # check if the user submitted a vote earlier and display that for modification
        if len(currentUserResponses) > 0 and self.request.user.get_username() != "":
            ctx['currentSelection'] = getCurrentSelection(currentUserResponses[0])
            ctx['itr'] = itertools.count(1, 1)
            ctx['unrankedCandidates'] = getUnrankedCandidates(currentUserResponses[0])
            items = []
            for item in ctx['currentSelection']:
                for i in item:
                    items.append(i)
            if not ctx['unrankedCandidates'] == None:
                for item in ctx['unrankedCandidates']:
                    items.append(item)
            ctx['items'] = items
            ctx['num_courses'] = self.get_num_courses(ctx)    
            print(ctx['num_courses'])

        else:
            # no history so display the list of choices
            ctx['items'] = self.get_order(ctx)
        return ctx
    
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())

def AddStep1View(request):
    """
    Define the first step in creating poll.
    
    Obtain title, description, type, allowing tie, and image from POST of HTTP request.
    Redirects to add step 1 page if request does not contain POST, go to add step 2 otherwise.
    """
    context = RequestContext(request)
    if request.method == 'POST':
        questionString = request.POST['questionTitle']
        questionDesc = request.POST['desc']
        questionType = request.POST['questiontype']
        imageURL = request.POST['imageURL']
        tie=False
        t = request.POST.getlist('allowties')
        if "1" in t:
            tie = True
        if "2" in t:
            tie = False

        # create a new question using information from the form and inherit
        # settings from the user's preferences
        question = Question(question_text=questionString, question_desc=questionDesc,
                            pub_date=timezone.now(), question_owner=request.user,
                            display_pref=request.user.userprofile.displayPref,
                            emailInvite=request.user.userprofile.emailInvite,
                            emailDelete=request.user.userprofile.emailDelete,
                            emailStart=request.user.userprofile.emailStart,
                            emailStop=request.user.userprofile.emailStop, creator_pref=1,allowties = tie)
        if request.FILES.get('docfile') != None:
            question.image = request.FILES.get('docfile')
        elif imageURL != '':
            question.imageURL = imageURL
        question.question_type = questionType
        
        question.save()
        setupEmail(question)
        return HttpResponseRedirect(reverse('polls:AddStep2', args=(question.id,)))
    return render(request,'polls/add_step1.html', {})


class AddStep2View(views.generic.DetailView):
    """Define step 2 in creating poll: adding choices."""
    
    model = Question
    template_name = 'polls/add_step2.html'
    def get_context_data(self, **kwargs):
        ctx = super(AddStep2View, self).get_context_data(**kwargs)
        ctx['items'] = self.object.item_set.all()
        return ctx
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())


class AddStep3View(views.generic.DetailView):
    """Defind step 3 in creating poll: inviting voters."""

    model = Question
    template_name = 'polls/add_step3.html'

    def getUsersFromLatestCSV(self, recentCSVText, existingUsers):
        registeredUsers, unRegisteredUsers=[],[]
        if(recentCSVText is not None): 
            userIDsFromCSV = recentCSVText.split(",")
            userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]

            existingUserIDs = [user.username for user in existingUsers]

            for userID in userIDsFromCSV:
                if userID in existingUserIDs:
                    registeredUsers.append(userID)
                else:
                    unRegisteredUsers.append(userID)

        return registeredUsers, unRegisteredUsers

    def get_context_data(self, **kwargs):
        ctx = super(AddStep3View, self).get_context_data(**kwargs)
        ctx['users'] = User.objects.all()
        ctx['groups'] = Group.objects.all()
        
        curr_question = ctx['question']
        ctx['recentCSVText'] = curr_question.recentCSVText
        registeredUsers, unRegisteredUsers = self.getUsersFromLatestCSV(curr_question.recentCSVText, ctx['users'])
        ctx['registeredUsers'] = registeredUsers
        ctx['unRegisteredUsers'] = unRegisteredUsers

        if Email.objects.filter(question=self.object).count() > 0:
            ctx['emailInvite'] = Email.objects.filter(question=self.object, type=1)[0]
            ctx['emailDelete'] = Email.objects.filter(question=self.object, type=2)[0]
            ctx['emailStart'] = Email.objects.filter(question=self.object, type=3)[0]
            ctx['emailStop'] = Email.objects.filter(question=self.object, type=4)[0]
            ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=4)[0]
            if len(Email.objects.filter(question=self.object, type=5)) > 0:
                ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=5)[0]

        return ctx
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())


class AddStep4View(views.generic.DetailView):
    """Define step 4 in creating poll: privacy setting, voting mechanisms, voting UIs, etc."""
    
    model = Question
    template_name = 'polls/add_step4.html'
    def get_context_data(self, **kwargs):
        ctx = super(AddStep4View, self).get_context_data(**kwargs)
        ctx['preference'] = self.request.user.userprofile.displayPref
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['alloc_methods'] = getAllocMethods()
        ctx['view_preferences'] = getViewPreferences()
        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


def addChoice(request, question_id):
    """
    Called when the "+" for adding choice is pressed.
    
    Submitted data must satisfy:
        - cannot be empty
        - cannot contain exactly same text as choices already added
    Image is optional.
    """

    question = get_object_or_404(Question, pk=question_id)
    item_text = request.POST['choice']
    imageURL = request.POST['imageURL']

    # check for empty strings
    if item_text == "":
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # check for duplicates
    allChoices = question.item_set.all()
    for choice in allChoices:
        if item_text == choice.item_text:
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    # for cases of adding new alternative when poll is paused
    recentlyAdded = False
    if question.status == 4:
        recentlyAdded = True
    # create the choice
    item = Item(question=question, item_text=item_text, timestamp=timezone.now(),
                recently_added=recentlyAdded)

    # if the user uploaded an image or set a URL, add it to the item
    if request.FILES.get('docfile') != None:
        item.image = request.FILES.get('docfile')
    elif imageURL != '':
        item.imageURL = imageURL
    
    # save the choice
    item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def editChoice(request, question_id):
    """Called when choice title or description is edited in poll info page."""
    
    question = get_object_or_404(Question, pk=question_id)
    for item in question.item_set.all():
        # get data from POST request
        new_text = request.POST["item"+str(item.id)]
        item_desc = request.POST["itemdescription"+str(item.id)]
        imageURL = request.POST["imageURL"+str(item.id)]
        # update choice info accordingly
        if item_desc != "":
            item.item_description = item_desc
        if request.FILES.get("docfile"+str(item.id)) != None:
            item.image = request.FILES.get("docfile"+str(item.id))
        elif imageURL != "":
            item.imageURL = imageURL
        item.item_text = new_text
        item.save()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def editBasicInfo(request, question_id):
    """
    Called in basic info tab in poll info page when saving changes.
    
    Updates title, description, available voting UIs, and whether ties are allowed.
    """
    
    question = get_object_or_404(Question, pk=question_id)
    # update title and description
    new_title = question.question_text
    if "title" in request.POST:
        new_title = request.POST["title"]
    new_desc = question.question_desc
    if "desc" in request.POST:
        new_desc = request.POST["desc"]
    question.question_text = new_title
    question.question_desc = new_desc
    
    # update UIs
    twocol = False
    onecol = False
    slider = False
    star = False
    yesno = False
    yesno2 = False
    BUI_slider = False
    LUI = False
    IBUI = False
    uilist = request.POST.getlist('ui')
    if "twocol" in uilist:
        twocol = True
    if "onecol" in uilist:
        onecol = True
    if "slider" in uilist:
        slider = True
    if "star" in uilist:
        star = True
    if "yesno" in uilist:
        yesno = True
    if "yesno2" in uilist:
        yesno2 = True
    if "BUI_slider" in uilist:
        BUI_slider = True 
    if "LUI" in uilist:
        LUI = True
    if "IBUI" in uilist:
        IBUI = True
    question.twocol_enabled = twocol
    question.onecol_enabled = onecol
    question.slider_enabled = slider
    question.star_enabled = star
    question.yesno_enabled = yesno
    question.yesno2_enabled = yesno2
    question.budgetUI_enabled = BUI_slider
    question.ListUI_enabled =LUI
    question.infiniteBudgetUI_enabled =IBUI
    question.ui_number = twocol+onecol+slider+star+yesno+yesno2+BUI_slider+LUI+IBUI
    
    # update whether ties are allowed
    tie=question.allowties
    t = request.POST.getlist('allowties')
    if "1" in t:
        tie = True
    if "2" in t:
        tie = False

    question.allowties = tie
    
    # save the changes
    question.save()
    request.session['setting'] = 8
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def deleteChoice(request, choice_id):
    """Delete a choice; can only be done before a poll starts."""
    
    item = get_object_or_404(Item, pk=choice_id)
    item.delete()
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


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

# find the winner(s) using the polling algorithm selected earlier
# Question question
# return String winnerStr
def getPollWinner(question):
    """
    Calculate winner of poll. 
    
    Parameter: Question object.
    Returns: string containing winner(s), mixture for k = 1, 2, 3.
    """
    
    all_responses = question.response_set.filter(active=1).order_by('-timestamp')
    (latest_responses, previous_responses) = categorizeResponses(all_responses)
    # Calculate results
    cand_map = getCandidateMapFromList(list(question.item_set.all()))
    results = getVoteResults(latest_responses, cand_map)
    (vote_results, mixtures_pl1, mixtures_pl2, mixtures_pl3) = ([],[],[],[])
    if(len(results) == 4):
        (vote_results, mixtures_pl1, mixtures_pl2, mixtures_pl3) = results
    else : 
        return "",json.dumps([]),json.dumps([]),json.dumps([])
    
    index_vote_results = question.poll_algorithm - 1
    current_result = vote_results[index_vote_results]

    winnerStr = ""
    
    # Transform result data into JSON strings and save in database

    #item_set = getCandidateMap(latest_responses[0])
    for index, score in current_result.items():
        # index 5 uses Simplified Bucklin, where score is rank.
        #   A low score means it has a high rank (e.g. rank 1 > rank 2),
        #   so the best score is the minimum.
        # All other indices rank score from highest to lowest, so the best score would be
        #   the maximum.
        if ((score == min(current_result.values()) and index_vote_results == 5)
                or (score == max(current_result.values()) and index_vote_results != 5)):
            #add a comma to separate the winners
            if winnerStr != "":
                winnerStr += ", "
            #add the winner
            winnerStr += cand_map[index].item_text

    if hasattr(question, 'finalresult'):
        question.finalresult.delete()
    result = FinalResult(question=question, timestamp=timezone.now(),
                        result_string="", mov_string="", cand_num=question.item_set.all().count(),
                        node_string="", edge_string="", shade_string="")
    
    resultlist = []
    mov = getMarginOfVictory(latest_responses, cand_map)
    movlist = [str(i) for i in mov]
    for x in range(0, len(vote_results)):
        for key, value in vote_results[x].items():
            resultlist.append(str(value))
            # resultstr += str(value)
            # resultstr += ","
    # for x in range(0, len(mov)):
    #     movstr += str(mov[x])
    #     movstr += ","
    # resultstr = resultstr[:-1]
    # movstr = movstr[:-1]
    (nodes, edges) = parseWmg(latest_responses, cand_map)
    # for node in nodes:
    #     for k, v in node.items():
    #         nodestr += k + "," + str(v) + ";"
    #     nodestr += "|"
    # nodestr = nodestr[:-2]
    # for edge in edges:
    #     for k, v in edge.items():
    #         edgestr += k + "," + str(v) + ";"
    #     edgestr += "|"
    # edgestr = edgestr[:-2]
    shadevalues = getShadeValues(vote_results)
    # for x in shadevalues:
    #     for y in x:
    #         shadestr += y + ";"
    #     shadestr += "|"
    # shadestr = shadestr[:-2]
    result.result_string = json.dumps(resultlist)
    result.mov_string = json.dumps(movlist)
    result.node_string = json.dumps(nodes)
    result.edge_string = json.dumps(edges)
    result.shade_string = json.dumps(shadevalues)
    result.save()
    
    # Resets new vote flag so that result is not computed again
    if question.new_vote:
        question.new_vote = False
    question.winner = winnerStr
    question.mixtures_pl1 = json.dumps(mixtures_pl1)
    question.mixtures_pl2 = json.dumps(mixtures_pl2)
    question.mixtures_pl3 = json.dumps(mixtures_pl3)
    question.save()

    return winnerStr, json.dumps(mixtures_pl1), json.dumps(mixtures_pl2), json.dumps(mixtures_pl3)



def interpretResult(finalresult):
    """
    Interpret result into strings that can be shown on the result page.
    
    Parameter: FinalResult object
    Returns: list of list of String containing data used on result page.
    """
    
    candnum = finalresult.cand_num
    resultlist = json.loads(finalresult.result_string)
    tempResults = []
    algonum = len(getListPollAlgorithms())
    if len(resultlist) < candnum*algonum:
        algonum = 7
    if len(resultlist) > 0:
        for x in range(0, algonum):
            tempList = []
            for y in range(x*candnum, (x+1)*candnum):
                tempList.append(resultlist[y])
            tempResults.append(tempList)
    tempMargin = json.loads(finalresult.mov_string)
    tempShades = json.loads(finalresult.shade_string)
    temp_nodes = json.loads(finalresult.node_string)
    tempEdges = json.loads(finalresult.edge_string)
    return [tempResults, tempMargin, tempShades, temp_nodes, tempEdges]


def recalculateResult(request, question_id):
    """Called when poll owner wants to recalculate result manually."""
    
    question = get_object_or_404(Question, pk=question_id)
    getPollWinner(question)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))



def isPrefReset(request):
    """Reset order in two-column UI. No longer used."""
    # reset link would have '?order=null' at the end
    orderStr = request.GET.get('order', '')
    if orderStr == "null":
        return True
    return False


def getCurrentSelection(mostRecentResponse):
    """
    Given a response, return current ranking data that can be loaded on voting UIs.
    
    Parameter: Response object.
    Returns: List<List<Item>>
    """
    responseDict = {}
    responseDict = buildResponseDict(mostRecentResponse, mostRecentResponse.question,
                                    getPrefOrder(mostRecentResponse.resp_str,
                                    mostRecentResponse.question))
    rd = responseDict
    array = []
    for itr in range(mostRecentResponse.question.item_set.all().count()):
        array.append([])
    for itr in rd:
        if rd[itr] != 1000:
            array[rd[itr] - 1].append(itr)
    return array

def getUnrankedCandidates(resp):
    """Simiar to getCurrentSelection; gets unranked alternatives."""
    
    rd = buildResponseDict(resp, resp.question, getPrefOrder(resp.resp_str, resp.question))
    array = []
    for itr in rd:
        if rd[itr] == 1000:
            array.append(itr)
    if len(array) == 0:
        return None
    return array


class DetailView(views.generic.DetailView):
    """Define poll voting page view."""
    
    model = Question
    template_name = 'polls/detail.html'

    def get_order(self, ctx):
        """Define the initial order to be displayed on the page."""
        
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order

    def get_context_data(self, **kwargs):
        print(self.request)
        ctx = super(DetailView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""

        #Case for anonymous user
        if self.request.user.get_username() == "":
            if isPrefReset(self.request):
                ctx['items'] = self.object.item_set.all()
                return ctx
            # check the anonymous voter
            if 'anonymousvoter' in self.request.session and 'anonymousid' in self.request.session:
                # sort the responses from latest to earliest
                anon_id = self.request.session['anonymousid']
                curr_anon_resps = self.object.response_set.filter(anonymous_id=anon_id, active=1).reverse()
                if len(curr_anon_resps) > 0:
                    # get the voter's most recent selection
                    mostRecentAnonymousResponse = curr_anon_resps[0]
                    if mostRecentAnonymousResponse.comment:
                        ctx['lastcomment'] = mostRecentAnonymousResponse.comment
                    ctx['currentSelection'] = getCurrentSelection(curr_anon_resps[0])
                    ctx['unrankedCandidates'] = getUnrankedCandidates(curr_anon_resps[0])
                    ctx['itr'] = itertools.count(1, 1)
                    items_ano = []
                    for item in ctx['currentSelection']:
                        for i in item:
                            items_ano.append(i)
                    if not ctx['unrankedCandidates'] == None:
                        for item in ctx['unrankedCandidates']:
                            items_ano.append(item)
                    ctx['items'] = items_ano
            else:
                # load choices in the default order
                ctx['items'] = self.object.item_set.all()
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment

        # reset button
        if isPrefReset(self.request):
            ctx['items'] = self.get_order(ctx)
            return ctx

        # check if the user submitted a vote earlier and display that for modification
        if len(currentUserResponses) > 0 and self.request.user.get_username() != "":
            ctx['currentSelection'] = getCurrentSelection(currentUserResponses[0])
            ctx['itr'] = itertools.count(1, 1)
            ctx['unrankedCandidates'] = getUnrankedCandidates(currentUserResponses[0])
            items = []
            for item in ctx['currentSelection']:
                for i in item:
                    items.append(i)
            if not ctx['unrankedCandidates'] == None:
                for item in ctx['unrankedCandidates']:
                    items.append(item)
            ctx['items'] = items
        else:
            # no history so display the list of choices
            ctx['items'] = self.get_order(ctx)
        
        return ctx
    
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())

def addPreferenceValueToResp(objs):
    for i in range(len(objs)):
        response, prefOrder = objs[i]

        # convert behavior_data to json and extract submitted_ranking
        behavior_data = json.loads(response.behavior_data)
        submitted_rankings = behavior_data.get("submitted_ranking", [])

        # Initialize empty set
        scores = set()

        # Extract the scores from submitted_rankings and add it to the scores set
        for tier in submitted_rankings:
            for jsonObj in tier:
                if isinstance(jsonObj, dict) and "score" in jsonObj:
                    scores.add(jsonObj["score"])

        scores = sorted(list(scores))[-1::-1] if scores else []

        # Add score as the first element in the tier-list
        for i in range(len(scores) if len(scores) < len(prefOrder) else len(prefOrder)):
            prefOrder[i].insert(0, scores[i])

        # print(prefOrder, scores)

    return objs

# view for settings detail
class PollInfoView(views.generic.DetailView):
    model = Question
    template_name = 'polls/pollinfo.html'

    def getUsersFromLatestCSV(self, recentCSVText, existingUsers):
        registeredUsers, unRegisteredUsers=[],[]
        if(recentCSVText is not None): 
            userIDsFromCSV = recentCSVText.split(",")
            userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]

            existingUserIDs = [user.username for user in existingUsers]

            for userID in userIDsFromCSV:
                if userID in existingUserIDs:
                    registeredUsers.append(userID)
                else:
                    unRegisteredUsers.append(userID)

        return registeredUsers, unRegisteredUsers

    def get_context_data(self, **kwargs):
        ctx = super(PollInfoView, self).get_context_data(**kwargs)
        curr_question = self.object
        emailInvite = Email.objects.filter(question=self.object, type=1)
        setupEmail(self.object)
        if Email.objects.filter(question=self.object).count() > 0:
            ctx['emailInvite'] = Email.objects.filter(question=self.object, type=1)[0]
            ctx['emailDelete'] = Email.objects.filter(question=self.object, type=2)[0]
            ctx['emailStart'] = Email.objects.filter(question=self.object, type=3)[0]
            ctx['emailStop'] = Email.objects.filter(question=self.object, type=4)[0]
            ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=4)[0]
            if len(Email.objects.filter(question=self.object, type=5)) > 0:
                ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=5)[0]
        ctx['users'] = User.objects.all()
        ctx['items'] = self.object.item_set.all()
        ctx['groups'] = Group.objects.all()
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['alloc_methods'] = getAllocMethods()
        twos = []
        for i in range(0, len(ctx['poll_algorithms'])):
            twos.append(2 ** i)
        ctx['twos'] = twos
        ctx['bools'] = self.object.vote_rule

        # display this user's history
        currentUserResponses = self.object.response_set.filter(user=self.request.user,
                                                               active=1).order_by('-timestamp')
        if len(currentUserResponses) > 0:
            ctx['user_latest_responses'] = getSelectionList([currentUserResponses[0]])
            if(curr_question.question_type == 2): ctx['user_latest_responses'] = addPreferenceValueToResp(ctx['user_latest_responses'])

        ctx['user_previous_responses'] = getSelectionList(currentUserResponses[1:])
        if(curr_question.question_type == 2): 
            ctx['user_previous_responses'] = addPreferenceValueToResp(ctx['user_previous_responses'])

        # get history of all users
        all_responses = self.object.response_set.filter(active=1).order_by('-timestamp')
        (latest_responses, previous_responses) = categorizeResponses(all_responses)
        ctx['latest_responses'] = getSelectionList(latest_responses)
        ctx['previous_responses'] = getSelectionList(previous_responses)
        if(curr_question.question_type == 2): 
            ctx['latest_responses'] = addPreferenceValueToResp(ctx['latest_responses'])
            ctx['previous_responses'] = addPreferenceValueToResp(ctx['previous_responses'])

        # get deleted votes
        deleted_resps = self.object.response_set.filter(active=0).order_by('-timestamp')
        (latest_deleted_resps,previous_deleted_resps) = categorizeResponses(deleted_resps)
        ctx['latest_deleted_resps'] = getSelectionList(latest_deleted_resps)
        ctx['previous_deleted_resps'] = getSelectionList(previous_deleted_resps)
        if(curr_question.question_type == 2):
            ctx['latest_deleted_resps'] = addPreferenceValueToResp(ctx['latest_deleted_resps'])
            ctx['previous_deleted_resps'] = addPreferenceValueToResp(ctx['previous_deleted_resps'])

        if self.object.question_voters.all().count() > 0:
            progressPercentage = len(latest_responses) / self.object.question_voters.all().count()
            progressPercentage = progressPercentage * 100
            ctx['progressPercentage'] = progressPercentage
        ctx['request_list'] = self.object.signuprequest_set.filter(status=1)

        # alloc_res_tables contains display options for results of an allocation
        selected_alloc_res_tables_sum = curr_question.alloc_res_tables
        ctx['selected_alloc_res_tables_sum'] = selected_alloc_res_tables_sum

        # Registered and unRegisteredUsers
        registeredUsers, unRegisteredUsers = self.getUsersFromLatestCSV(curr_question.recentCSVText, ctx['users'])
        ctx['registeredUsers'] = registeredUsers
        ctx['unRegisteredUsers'] = unRegisteredUsers
        ctx['recentCSVText'] = curr_question.recentCSVText

        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())

# view for results detail
class AllocateResultsView(views.generic.DetailView):
    model = Question
    template_name = 'polls/allocationResults/results_page.html'

    def getItemsObjects(self):
        items = [] 
        items_obj=[]
        for item in list(self.object.item_set.all()):
            items.append("item"+item.item_text)
            items_obj.append(item)
        return items,items_obj
    
    def getDataFromResponseSet(self, response_set):
        pref_set = {}
        candidates={}
        submitted_rankings={}
        profile_pics = {}
        # extracting required information from response_set
        # using dictionary instead of list to avoid duplicate preferences in response_set
        for response in response_set:
            candidates[response.user_id] = response.user.first_name 
            url = response.user.userprofile.profile_pic.name;
            profile_pics[response.user_id] = "/"+url if url != None else ''
            pref_set[response.user_id] = ast.literal_eval(response.resp_str)
            submitted_rankings[response.user_id]  = json.loads(response.behavior_data)["submitted_ranking"]
        return pref_set, candidates, submitted_rankings, profile_pics
    
    def transformSubmittedRankings(self, items, submitted_rankings):
        #transform submitted rankings
        for entry in submitted_rankings.items():
            key,values = entry
            if(len(values) < len(items)):
                temp = []
                for j in range(len(values)):
                    for entry in values[j]:
                        temp.append([entry])
                values= temp
                submitted_rankings[key] = values
        return submitted_rankings
    
    def getPreferencesList(self, pref_set):
        preferences=[]
        # change the type of preferences so that it is compatible to 
        # store and retrieve from list
        for pref in pref_set.values(): preferences.append(pref)
        return preferences
        
    def transformPreferences(self, items, preferences):
        # transform Preferences
        for i in range(len(preferences)):
            if(len(preferences[i]) < len(items)):
                temp = []
                for j in range(len(preferences[i])):
                    for entry in preferences[i][j]:
                        temp.append([entry])
                preferences[i]= temp

        for i in range(len(preferences)):
            for j in range(len(preferences[i])):
                preferences[i][j] = preferences[i][j][0]
        return preferences

    def transformAllocatedItems(self, allocated_items):
        # transform allocated_items
        allocated_items_transformed = [["" for j in range(len(allocated_items[i]))] for i in range(len(allocated_items))]
        for i in range(len(allocated_items)):
            for j in range(len(allocated_items[i])):
                allocated_items_transformed[i][j] = allocated_items[i][j][4:]
        return allocated_items_transformed
    
    def getSumOfAllocatedItems(self, allocated_items, submitted_rankings):
        # Computing allocated items and Sum of values of allocated items for each candidate
        sum_of_alloc_items_values = []
        allocated_items_with_values =[]
        for i in range(len(allocated_items)):
            sum_of_values = 0
            items_with_values = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(allocated_items[i])):
                #submitted_rankings_values = list(submitted_rankings.values())[i]
                for k in range(len(submitted_rankings_values)):
                    if "score" in submitted_rankings_values[k][0]:
                        if(submitted_rankings_values[k][0]["name"] == allocated_items[i][j]):
                            sum_of_values+=submitted_rankings_values[k][0]["score"]
                            items_with_values.append((submitted_rankings_values[k][0]["name"][4:], submitted_rankings_values[k][0]["score"]))
            sum_of_alloc_items_values.append(sum_of_values)
            allocated_items_with_values.append(items_with_values)
        return allocated_items_with_values, sum_of_alloc_items_values
    
    def formatOptions(self, items):
        # remove 'item' from 'itemOption' string
        for i in range(len(items)):
            items[i] = items[i][4:]
        return items

    def getPrefWithValues(self, submitted_rankings):
        # computing preferences with values for each candidate
        preferences_with_values = []
        for i in range(len(submitted_rankings)):
            curr_cand_preferences_with_values=[]
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(submitted_rankings_values)):
                if "score" in submitted_rankings_values[j][0]:
                    curr_cand_preferences_with_values.append([submitted_rankings_values[j][0]["name"][4:], submitted_rankings_values[j][0]["score"]])
            preferences_with_values.append(curr_cand_preferences_with_values)
        return preferences_with_values
    
    def computeEnvyUptoEF1(self, preferences, allocated_items_with_values,preferences_with_values):
        # compute envy matrix
        envy_matrix = [[(0,0) for j in range(len(preferences))] for i in range(len(preferences))]
        for i in range(len(allocated_items_with_values)):
            for j in range(len(allocated_items_with_values)):
                if i!=j:
                    envy,sum2 = self.getEnvy(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                    envy_matrix[i][j]  = (envy,sum2)
                    if envy_matrix[i][j][0] < 0:
                        ef1_val = self.getEF1(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                        if ef1_val == "EF1":
                            envy_matrix[i][j] = ("EF1",sum2)
                else:
                    envy_matrix[i][j] = (0,0)
        return envy_matrix
    
    def computePureEF1(self, preferences, allocated_items_with_values, preferences_with_values):
        # compute envy free upto 1 item matrix
        ef1_matrix = [[0 for j in range(len(preferences))] for i in range(len(preferences))]
        for i in range(len(allocated_items_with_values)):
            for j in range(len(allocated_items_with_values)):
                if i!=j:
                    ef1_matrix[i][j] = self.getEF1(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                else:
                    ef1_matrix[i][j] = 0

    def getEnvy(self, pref1, allocated_items1, pref2, allocated_items2):  

        # cand 1 sum
        sum1 = 0
        for item,val in allocated_items1:
            sum1+=val

        # cand 2 sum with cand 1 preferences
        sum2 = 0
        for item1, val1 in allocated_items2:
            for item2, val2 in pref1:
                if(item1 == item2):sum2+=val2
            
        return sum1-sum2,sum2

    def getEF1(self, pref1, allocated_items1, pref2, allocated_items2):
        for i in range(len(allocated_items2)):

            copy_allocated_items2 = allocated_items2.copy()
            copy_allocated_items2.remove(allocated_items2[i])

            # cand 1 sum
            sum1 = 0
            for item,val in allocated_items1:
                sum1+=val

            # cand 2 sum with cand 1 preferences
            sum2 = 0
            for item1, val1 in copy_allocated_items2:
                for item2, val2 in pref1:
                    if(item1 == item2):sum2+=val2

            EF1_val = sum1-sum2   
            if EF1_val >= 0:
                return "EF1"
        return "Not EF1"
    
    def getAllocatedItemObjects(self, item_objs, items_texts):
        allocated_items_objs = []
        for obj in item_objs:
            for item_name in items_texts:
                if item_name == obj.item_text:
                    allocated_items_objs.append(obj)
        return allocated_items_objs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        question = self.object  # the current question instance

        # if no responses, nothing to show
        if not question.response_set.exists():
            ctx['error_message'] = "No responses found. Users must submit preferences before viewing allocations."
            return ctx
        
        # get mechanism information and prepare context
        mechanism_info = self._prepare_mechanism_info(question)
        ctx.update(mechanism_info)
        
        # get user responses and preferences
        user_data = self._prepare_user_data(question)
        ctx.update(user_data)
        
        current_user_id = self.request.user.id
        current_user_name = user_data['user_names'].get(current_user_id, "")
        ctx['current_user_name'] = current_user_name
        ctx['empty_string'] = ""

        curr_user_ranking = user_data['submitted_rankings'].get(current_user_id, [])
        ctx['curr_user_pref'] = []
        ctx['curr_user_pref_values'] = []

        for entry in curr_user_ranking: #support for twocol & onecol
            if not entry:
                continue
            val = entry[0]
            if isinstance(val, dict) and 'name' in val:
                ctx['curr_user_pref'].append(val['name'][4:])  # Strip "item" prefix
                ctx['curr_user_pref_values'].append(val.get('score', 0))
            elif isinstance(val, str):
                ctx['curr_user_pref'].append(val[4:])  #for string like "itemcake"
                ctx['curr_user_pref_values'].append(0)
        # create context data dictionary for caching
        context_data = {
            'question_id': question.id,
            'mechanism_id': ctx['current_mechanism_id'],
            'preferences': user_data['preferences'],
            'sorted_user_ids': user_data['sorted_user_ids']
        }
        
        # get cached result or compute new allocation
        allocation_result, is_cache_hit = self._get_allocation_result(
            context_data, 
            ctx['chosen_cls'], 
            ctx['chosen_label']
        )
        
        # Update context with allocation results
        ctx.update(allocation_result)
        
        # Add additional UI-specific data
        if question.alloc_res_tables & 2 != 0:
            ctx["all_user_preferences"] = self._format_user_preferences(
                user_data['sorted_user_ids'],
                user_data['user_names'],
                user_data['submitted_rankings']
            )
        
        # Check Pareto Optimality
        ctx["is_pareto_optimal"] = False
        if allocation_result.get('allocation_matrix') is not None and user_data.get('preferences'):
            try:
                V = np.array(user_data['preferences'])
                A = np.array(allocation_result['allocation_matrix'])
                ctx["is_pareto_optimal"] = is_po(V, A)
            except Exception as e:
                print("is_PO check failed:", e)

        # Compute Welfare Metrics
        sum_values = allocation_result.get('sum_of_alloc_items_values', [])
        if sum_values:
            utilitarian_welfare = sum(sum_values)
            egalitarian_welfare = min(sum_values)
            ctx["utilitarian_welfare"] = utilitarian_welfare
            ctx["egalitarian_welfare"] = egalitarian_welfare

        # First-choice analysis
        first_choices_data = []
        if allocation_result.get('allocation_matrix') is not None:
            allocation_matrix = allocation_result['allocation_matrix']
            preferences = user_data['preferences']
            for i, row in enumerate(allocation_matrix):  # For each agent
                # Get that agent's valuation vector
                valuations = preferences[i]
                max_val = max(valuations)  # Their most preferred item's value
                count = 0
                for j, alloc in enumerate(row):  # Loop through their allocated items
                    if alloc == 1 and valuations[j] == max_val:
                        count += 1
                first_choices_data.append(count)

        ctx["first_choices_data"] = first_choices_data

        return ctx

    def _prepare_mechanism_info(self, question):
        """Prepare mechanism selection information"""
        # question model
        locked_alg_id = question.poll_algorithm
        alg_bitmask = question.alloc_algorithms
        
        # define known allocation mechanisms
        all_mechanisms = [
            (1,  "Round Robin",       MechanismRoundRobinAllocation),
            (2,  "Max Nash Welfare",  MechanismMaximumNashWelfare),
            (4,  "Market (EF1)",      MechanismMarketAllocation),
            (8,  "MarketEq (EQ1)",    MechanismMarketEqAllocation),
            (16, "Leximin",           MechanismLeximinAllocation),
            (32, "MNW Binary",        MechanismMaximumNashWelfareBinary),
        ]

        # build a list of allowed (bit, label) from the bitmask
        available_mechanisms = []
        for (bit, label, cls) in all_mechanisms:
            if (alg_bitmask & bit) != 0:
                available_mechanisms.append((bit, label))
        
        # if no algorithms are selected, fall back to Round Robin
        if not available_mechanisms:
            # Fall back to Round Robin if no algorithms are selected
            available_mechanisms = [(1, "Round Robin")]
        
        # requested ?alg=...
        requested_alg = self.request.GET.get("alg", None)
        if requested_alg is not None:
            try:
                requested_bit = int(requested_alg)
                # if that bit is not in the poll's bitmask, revert to locked
                if (alg_bitmask & requested_bit) == 0:
                    current_mechanism_id = locked_alg_id
                else:
                    current_mechanism_id = requested_bit
            except ValueError:
                current_mechanism_id = locked_alg_id
        else:
            current_mechanism_id = locked_alg_id

        # Find which mechanism class is chosen
        chosen_cls = None
        chosen_label = "Unknown"
        for (bit, label, cls) in all_mechanisms:
            if bit == current_mechanism_id:
                chosen_cls = cls
                chosen_label = label
                break

        # If none matched, default to round robin
        if not chosen_cls:
            chosen_cls = MechanismRoundRobinAllocation
            chosen_label = "Round Robin"
        
        return {
            "available_mechanisms": available_mechanisms,
            "current_mechanism_id": current_mechanism_id,
            "current_mechanism": chosen_label,
            "chosen_cls": chosen_cls,
            "chosen_label": chosen_label,
            "selected_alloc_res_tables_sum": question.alloc_res_tables
        }

    def _prepare_user_data(self, question):
        """Extract user responses and preferences"""
        response_set = question.response_set.all()
        current_user_id = self.request.user.id

        # Build map of user ids -> name/pic
        user_names = {}
        user_pics = {}
        submitted_rankings = {}
        
        for resp in response_set:
            uid = resp.user_id
            if uid not in user_names:
                print(user_names)
                user_names[uid] = resp.user.first_name
                print(resp.user)
                pic_path = resp.user.userprofile.profile_pic.name
                user_pics[uid] = f"/{pic_path}" if pic_path else ""
            submitted_rankings[uid] = json.loads(resp.behavior_data)["submitted_ranking"]

        sorted_user_ids = sorted(user_names.keys())
        
        # Build a matrix of numeric valuations
        preferences = self._extract_numeric_preferences(
            response_set, 
            sorted_user_ids, 
            question.item_set.count()
        )
        
        return {
            "candidates": [user_names[uid] for uid in sorted_user_ids],
            "profile_pics": [user_pics[uid] for uid in sorted_user_ids],
            "user_names": user_names,
            "submitted_rankings": submitted_rankings,
            "sorted_user_ids": sorted_user_ids,
            "preferences": preferences,
            "current_user_id": current_user_id
        }

    def _extract_numeric_preferences(self, response_set, sorted_user_ids, item_count):
        """Extract numeric preference values from responses"""
        user_valuations_map = {}
        
        # Process each response
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
                for x in sublist:  # handle multiple items per tier
                    if isinstance(x, str):  # raw_list
                        name=x
                    elif isinstance(x, dict) and "name" in x:
                        name=x["name"]
                    if name:
                        val=item_score_map.get(name,0.0)
                    else:
                        try:
                            val = float(x[4:]) if isinstance(x, str) and x.startswith("item") else 0.0
                        except:
                            val = 0.0
                    numeric_vals.append(val)
            user_valuations_map[uid] = numeric_vals

        # Fix for empty preferences
        for uid in sorted_user_ids:
            if uid not in user_valuations_map or not user_valuations_map[uid]:
                user_valuations_map[uid] = [0.0] * item_count
        
        # Make sure all preference lists have the same length
        max_length = max([len(vals) for vals in user_valuations_map.values()]) if user_valuations_map else item_count
        for uid in user_valuations_map:
            if len(user_valuations_map[uid]) < max_length:
                user_valuations_map[uid] += [0.0] * (max_length - len(user_valuations_map[uid]))

        # Convert to a 2d list in user-id sorted order
        preferences = []
        for uid in sorted_user_ids:
            preferences.append(user_valuations_map.get(uid, [0.0] * max_length))
        
        return preferences

    def _process_allocation_result(self, result, preferences, sorted_user_ids, question_id):
        """Process allocation result into template context data"""
        # Extract allocation matrix
        allocation_matrix = result.A  # shape: (num_agents, num_items)
        
        # Get question and items
        question = Question.objects.get(id=question_id) if question_id else None
        items = list(question.item_set.all()) if question else []
        
        # Create basic allocation data
        allocation_data = {
            'allocation_matrix': allocation_matrix,
            'items_obj': items,
        }
        
        # Reconstruct allocated items
        allocated_items = []
        if allocation_matrix is not None:
            N = len(allocation_matrix)
            if N > 0:
                M = len(allocation_matrix[0])
                for i in range(N):
                    user_items = []
                    for j in range(M):
                        if allocation_matrix[i][j] == 1 and j < len(items):
                            # Store the actual Item object
                            user_items.append(items[j])
                        elif allocation_matrix[i][j] == 1:
                            # Fallback for items beyond the range
                            user_items.append({'item_text': f"Item #{j}", 'id': -1})
                    allocated_items.append(user_items)
        allocation_data['allocated_items'] = allocated_items
        
        # Calculate sum of values for each agent
        sum_values = []
        for i, prefs in enumerate(preferences):
            if i < len(allocation_matrix):
                utility = sum(prefs[j] * allocation_matrix[i][j] for j in range(len(prefs)))
                sum_values.append(utility)
        
        allocation_data['sum_of_alloc_items_values'] = sum_values
        
        return allocation_data

    def _get_allocation_result(self, context_data, mechanism_class, mechanism_label):
        """Get cached allocation or compute a new one"""
        # Try to get from cache
        cached_result, is_hit = AllocationCache.get_cached_result(context_data)
        
        if is_hit:
            logger.info(f"Cache hit for mechanism {mechanism_label}")
            print(f"\n>>> CACHE HIT: Using cached result for {mechanism_label} <<<\n")
            # return cached_result, True
            # Process the cached data to ensure it's in the right format for the template
            processed_result = self._process_cached_allocation_data(cached_result)
            return processed_result, True
        
        # If not in cache, compute allocation
        logger.info(f"Cache miss for mechanism {mechanism_label}, computing allocation")
        print(f"\n>>> CACHE MISS: Computing new result for {mechanism_label} <<<\n")
        start_time = timezone.now()
        
        try:
            # Run the allocation mechanism
            mechanism = mechanism_class()
            result = mechanism.allocate(valuations=context_data['preferences'])
            
            # Process the allocation result
            allocation_data = self._process_allocation_result(
                result, 
                context_data['preferences'],
                context_data['sorted_user_ids'],
                context_data.get('question_id')
            )
            
            # Store in cache
            AllocationCache.store_result(context_data, allocation_data)
            
            # Log performance
            end_time = timezone.now()
            computation_time = (end_time - start_time).total_seconds()
            logger.info(f"Allocation computed in {computation_time:.2f}s for mechanism {mechanism_label}")
            print(f"Allocation computed in {computation_time:.2f}s for mechanism {mechanism_label}")
            
            return allocation_data, False
            
        except Exception as e:
            logger.error(f"Error computing allocation with {mechanism_label}: {str(e)}", exc_info=True)
            print(f"\n>>> ERROR computing allocation with {mechanism_label}: {str(e)} <<<\n")
            
            # Create fallback allocation
            n = len(context_data['preferences'])
            m = max([len(p) for p in context_data['preferences']]) if context_data['preferences'] else 0
            empty_matrix = np.zeros((n, m))
            
            # Return error data
            error_data = {
                'error_message': f"Could not compute allocation with {mechanism_label}: {str(e)}",
                'allocation_matrix': empty_matrix,
                'allocated_items': [[] for _ in range(n)],
                'sum_of_alloc_items_values': [0] * n
            }
            
            return error_data, False

    def _format_user_preferences(self, sorted_user_ids, user_names, submitted_rankings):
        """Format user preferences for display"""
        all_user_prefs = []
        for uid in sorted_user_ids:
            username = user_names[uid]
            ranking = submitted_rankings[uid]
            cleaned = []
            for group in ranking:
                if group and isinstance(group[0], dict):
                    item_name = group[0].get("name", "")[4:]
                    cleaned.append((item_name))
            all_user_prefs.append((username, cleaned))
        return all_user_prefs

    def _process_cached_allocation_data(self, cached_result, question_id=None):
        """Process cached allocation data to work with the template"""
        if not question_id:
            question_id = self.kwargs.get('pk')
            
        question = Question.objects.get(id=question_id)
        items = list(question.item_set.all())
        
        # Store items_obj reference
        cached_result['items_obj'] = items
        
        # Convert dictionary items back to Item objects
        if 'allocated_items' in cached_result:
            for i, agent_items in enumerate(cached_result['allocated_items']):
                for j, item_data in enumerate(agent_items):
                    if isinstance(item_data, dict) and 'id' in item_data and item_data['id'] > 0:
                        # Find matching item by ID
                        for item in items:
                            if item.id == item_data['id']:
                                cached_result['allocated_items'][i][j] = item
                                break
        
        return cached_result

# view for submission confirmation
class ConfirmationView(views.generic.DetailView):
    model = Question
    template_name = 'polls/confirmation.html'


# view that displays vote results using various algorithms
class VoteResultsView(views.generic.DetailView):
    model = Question
    template_name = 'polls/vote_rule.html'
    def get_context_data(self, **kwargs):
        ctx = super(VoteResultsView, self).get_context_data(**kwargs)
        #print("page accessed")
        cand_map = getCandidateMapFromList(list(self.object.item_set.all()))
        ctx['cand_map'] = cand_map# if (len(latest_responses) > 0) else None
        if len(list(self.object.response_set.all())) == 0:
            return ctx
        if self.object.status != 4 and self.object.new_vote == True:
            getPollWinner(self.object)
        final_result = self.object.finalresult
        if self.object.mixtures_pl1 == "":
            getPollWinner(self.object)
        if self.object.mixtures_pl1 != "":
            mixtures_pl1 = json.loads(self.object.mixtures_pl1)
            mixtures_pl2 = json.loads(self.object.mixtures_pl2)
            mixtures_pl3 = json.loads(self.object.mixtures_pl3)
        else:
            mixtures_pl1 = [[]]
            mixtures_pl2 = []
            mixtures_pl3 = []

        l = interpretResult(final_result)
        # print(l[0])
        poll_algorithms = []
        algorithm_links = []
        vote_results = []
        margin_victory = []
        shade_values = []

        start_poll_algorithms = getListPollAlgorithms()
        start_algorithm_links = getListAlgorithmLinks()
        to_show = self.object.vote_rule
        itr = 0
        poll_alg_num = self.object.poll_algorithm
        while to_show > 0:
            if to_show % 2 == 1:
                poll_algorithms.append(start_poll_algorithms[itr])
                algorithm_links.append(start_algorithm_links[itr])
                vote_results.append(l[0][itr])
                shade_values.append(l[2][itr])
                if itr < len(l[1]):
                    margin_victory.append(l[1][itr])
                to_show = to_show - 1
            elif itr < self.object.poll_algorithm - 1:
                poll_alg_num -= 1
            to_show = int(to_show / 2)
            itr += 1
        ctx['poll_algorithms'] = poll_algorithms
        ctx['poll_alg_num'] = poll_alg_num
        ctx['algorithm_links'] = algorithm_links
        ctx['vote_results'] = vote_results
        ctx['margin_victory'] = margin_victory
        ctx['shade_values'] = shade_values
        ctx['wmg_nodes'] = l[3]
        ctx['wmg_edges'] = l[4]
        ctx['time'] = final_result.timestamp
        ctx['margin_len'] = len(margin_victory)

        m = len(mixtures_pl1) - 1
        ctx['mixtures_pl1'] = mixtures_pl1
        ctx['mixtures_pl2'] = mixtures_pl2
        ctx['mixtures_pl3'] = mixtures_pl3
        previous_results = self.object.voteresult_set.all()
        ctx['previous_winners'] = []
        for pw in previous_results:
            obj = {}
            obj['title'] = str(pw.timestamp.time())
            candnum = pw.cand_num
            resultstr = pw.result_string
            movstr = pw.mov_string
            if resultstr == "" and movstr == "":
                continue
            resultlist = resultstr.split(",")
            movlist = movstr.split(",")
            tempResults = []
            algonum = len(getListPollAlgorithms())
            if len(resultlist) < candnum*algonum:
                algonum = 7
            if len(resultlist) > 0:
                for x in range(0, algonum):
                    tempList = []
                    for y in range(x*candnum, (x+1)*candnum):
                        tempList.append(resultlist[y])
                    tempResults.append(tempList)
            obj['vote_results'] = tempResults
            tempMargin = []
            for margin in movlist:
                tempMargin.append(margin)
            obj['margin_victory'] = tempMargin
            ctx['previous_winners'].append(obj)
        return ctx

# get a list of algorithms supported by the system
# return List<String>
def getListPollAlgorithms():
    return ["Plurality", "Borda", "Veto", "K-approval (k = 3)", "Simplified Bucklin",
            "Copeland", "Maximin","MaxiMin-Duplicate", "STV", "Baldwin", "Coombs", "Black", "Ranked Pairs",
            "Plurality With Runoff", "Borda Mean", "Simulated Approval"]

def getListAlgorithmLinks():
    return ["https://en.wikipedia.org/wiki/Plurality_voting_method",
            "https://en.wikipedia.org/wiki/Borda_count", "", "",
            "https://en.wikipedia.org/wiki/Bucklin_voting",
            "https://en.wikipedia.org/wiki/Copeland%27s_method",
            "https://en.wikipedia.org/wiki/Minimax_Condorcet",
            "https://en.wikipedia.org/wiki/Single_transferable_vote",
            "https://en.wikipedia.org/wiki/Nanson%27s_method#Baldwin_method",
            "https://en.wikipedia.org/wiki/Coombs%27_method","","","","",""]

# get a list of allocation methods
# return List[String]
def getAllocMethods():
    return [
        "Round Robin",
        "Maximum Nash Welfare",
        "Market",
        "MarketEq",
        "Leximin",
        "MNW Binary"
    ]

# get a list of visibility settings
# return List<String>
def getViewPreferences():
    return [
        # "Everyone can see all votes at all times",
        "Everyone can see all preferences", 
        "Everyone can only see own preference",
        "Nothing"
            ]

def getViewUserInfo():
    return [
        "Only username of users will be shown",
        "Only numbers of users will be shown",
        "Nothing"
    ]

def getViewPreferencesForAllocation():
    return ["This is Duplicate view pref"]


def getWinnersFromIDList(idList):
    winners = {}
    for i in idList:
        try:
            q = Question.objects.get(pk=i)
            winners[i] = q.winner
        except Question.DoesNotExist:
            pass
    return winners

# build a graph of nodes and edges from a 2d dictionary
# List<Response> latest_responses
# return (List<Dict> nodes, List<Dict> edges)
def parseWmg(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return ([], [])

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return ([], [])

    # make sure there's at least one response
    if len(latest_responses) == 0:
        return ([], [])

    # get nodes (the options)
    nodes = []
    for rowIndex in cand_map:
        data = {}
        data['id'] = rowIndex
        data['value'] = 1
        data['label'] = cand_map[rowIndex].item_text
        nodes.append(data)

    # get edges from the weighted majority graph
    wmg = pollProfile.getWmg()
    edges = []
    for rowIndex in wmg:
        row = wmg[rowIndex]
        for colIndex in row:
            value = row[colIndex]
            if value > 0:
                data = {}
                data['from'] = rowIndex
                data['to'] = colIndex
                data['value'] = value
                data['title'] = str(value)
                edges.append(data)

    return (nodes, edges)

# format a list of votes to account for ties
def getSelectionList(responseList):
    selectList = []
    for response in responseList:
        selectList.append((response, getCurrentSelection(response)))
    return selectList

#separate the user votes into two categories: (1)most recent (2)previous history
# List<Response> all_responses
# return (List<Response> latest_responses, List<Response> previous_responses)
def categorizeResponses(all_responses):
    latest_responses = []
    previous_responses = []

    if len(all_responses) > 0:
        #the first response must be the most recent
        latest_responses.append(all_responses[0])

    others = all_responses[1:]

    #the outer loop goes through all the responses
    for response1 in others:
        #for anonymous users, check anonymous name instead of username
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
            #check if the user has voted multiple times
            for response2 in latest_responses:
                if not response2.user == None:
                    if response1.user.username == response2.user.username:
                        add = False
                        previous_responses.append(response1)
                        break

            #this is the most recent vote
            if add:
                latest_responses.append(response1)

    return (latest_responses, previous_responses)

# get a list of options for this poll
# Response response
# return Dict<int, Item> cand_map
def getCandidateMap(response):
    d = {}
    if response.dictionary_set.all().count() > 0:
        d = Dictionary.objects.get(response=response)
    else:
        d = buildResponseDict(response, response.question,
                                getPrefOrder(response.resp_str, response.question))
    d = interpretResponseDict(d)
    cand_map = {}

    counter = 0
    for item in d.items():
        cand_map[counter] = item[0]
        counter += 1
    return cand_map

def getCandidateMapFromList(candlist):
    cand_map = {}
    counter = 0
    for item in candlist:
        cand_map[counter] = item
        counter += 1
    return cand_map

#convert a user's preference into a 2d map
# Response response
# return Dict<int, Dict<int, int>> pref_graph
def getPreferenceGraph(response, cand_map):
    pref_graph = {}
    dictionary = {}
    if response.dictionary_set.all().count() > 0:
        dictionary = Dictionary.objects.get(response=response)
    else:
        dictionary = buildResponseDict(response, response.question,
                                        getPrefOrder(response.resp_str, response.question))
    dictionary = interpretResponseDict(dictionary)
    for cand1Index in cand_map:
        tempDict = {}
        for cand2Index in cand_map:
            if cand1Index == cand2Index:
                continue

            cand1 = cand_map[cand1Index]
            cand2 = cand_map[cand2Index]
            cand1Rank = dictionary.get(cand1)
            cand2Rank = dictionary.get(cand2)
            #lower number is better (i.e. rank 1 is better than rank 2)
            if cand1Rank < cand2Rank:
                tempDict[cand2Index] = 1
            elif cand2Rank < cand1Rank:
                tempDict[cand2Index] = -1
            else:
                tempDict[cand2Index] = 0
        pref_graph[cand1Index] = tempDict

    return pref_graph

# initialize a profile object using all the preferences
# List<Response> latest_responses
# return Profile object
def getPollProfile(latest_responses, cand_map):
    if len(latest_responses) == 0:
        return None

    pref_list = []
    for response in latest_responses:
        pref_graph = getPreferenceGraph(response, cand_map)
        userPref = Preference(pref_graph)
        pref_list.append(userPref)
    return Profile(cand_map, pref_list)
    
def translateSingleWinner(winner, cand_map):
    result = {}
    if isinstance(winner, collections.Iterable):
        return translateWinnerList(winner,cand_map)
    for cand in cand_map.keys():
        if cand == winner:
            result[cand] = 1
        else:
            result[cand] = 0
    return result

def translateWinnerList(winners, cand_map):
    result = {}
    for cand in cand_map.keys():
        if cand in winners:
            result[cand] = 1
        else:
            result[cand] = 0
    return result
    
def translateBinaryWinnerList(winners, cand_map):
    result = {}
    if len(cand_map.keys()) != len(winners):
        return result
    for cand in cand_map.keys():
        if winners[cand] == 1:
            result[cand] = 1
        else:
            result[cand] = 0
    return result

#calculate the results of the vote using different algorithms
# List<Response> latest_responses
# return a List<Dictionary<Double>>
def getVoteResults(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return []

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return []

    scoreVectorList = []
    scoreVectorList.append(MechanismPlurality().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismBorda().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismVeto().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismKApproval(3).getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismSimplifiedBucklin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismCopeland(1).getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))

    #STV, Baldwin, Coombs give list of integers as output
    stv = MechanismSTV().STVwinners(pollProfile)
    baldwin = MechanismBaldwin().baldwin_winners(pollProfile)
    coombs = MechanismCoombs().coombs_winners(pollProfile)
    #print("test8")
    black = MechanismBlack().black_winner(pollProfile)
    #print("test7")
    ranked = MechanismRankedPairs().ranked_pairs_cowinners(pollProfile)
    pwro = MechanismPluralityRunOff().PluRunOff_cowinners(pollProfile)
    bordamean = MechanismBordaMean().Borda_mean_winners(pollProfile)
    simapp, sim_scores = MechanismBordaMean().simulated_approval(pollProfile)
    # print("pwro=", pwro)
    #print("test6")
    scoreVectorList.append(translateWinnerList(stv, cand_map))
    scoreVectorList.append(translateWinnerList(baldwin, cand_map))
    scoreVectorList.append(translateWinnerList(coombs, cand_map))
    scoreVectorList.append(translateWinnerList(black, cand_map))
    scoreVectorList.append(translateWinnerList(ranked, cand_map))
    scoreVectorList.append(translateWinnerList(pwro, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(bordamean, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(simapp, cand_map))

    #for Mixtures
    #print("test1")
    rankings = pollProfile.getOrderVectorsEGMM()
    m = len(rankings[0])
    #print("test2")
    mixtures_pl1 = egmm_mixpl(rankings, m, k=1, itr=10)[0].tolist()
    #print("test3")
    mixtures_pl2 = egmm_mixpl(rankings, m, k=2, itr=10).tolist()
    #print("test4")
    mixtures_pl3 = egmm_mixpl(rankings, m, k=3, itr=10).tolist()
    #print("test5")
    #gmm = GMMMixPLAggregator(list(pollProfile.cand_map.values()), use_matlab=False)

    return scoreVectorList, mixtures_pl1, mixtures_pl2, mixtures_pl3

def calculatePreviousResults(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.voteresult_set.clear()
    cand_map = getCandidateMapFromList(list(question.item_set.all()))
    previous_winners = question.oldwinner_set.all()
    for pw in previous_winners:

        result = VoteResult(question=question, timestamp=pw.response.timestamp,
                            result_string="", mov_string="",
                            cand_num=question.item_set.all().count())
        result.save()
        resultstr = ""
        movstr = ""
        responses = question.response_set.reverse()
        responses = responses.filter(timestamp__range=[datetime.date(1899, 12, 30),
                                    pw.response.timestamp], 
                                    active=1)
        (lr, pr) = categorizeResponses(responses)
        scorelist, mixtures_pl1, mixtures_pl2, mixtures_pl3 = getVoteResults(lr, cand_map)
        mov = getMarginOfVictory(lr, cand_map)
        for x in range(0, len(scorelist)):
            for key, value in scorelist[x].items():
                resultstr += str(value)
                resultstr += ","
        for x in range(0, len(mov)):
            movstr += str(mov[x])
            movstr += ","
        resultstr = resultstr[:-1]
        movstr = movstr[:-1]
        result.result_string = resultstr
        result.mov_string = movstr
        result.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


# return lighter (+lum) or darker (-lum) color as a hex string
# pass original hex string and luminosity factor, e.g. -0.1 = 10% darker
# String hexVal
# double lum
def colorLuminance(hexVal, lum):
    #convert to decimal and change luminosity
    rgb = "#"
    for i in range(0, 3):
        c = int(hexVal[i * 2 : i * 2 + 2], 16)
        c = round(min(max(0, c + (c * float(lum))), 255))
        c = hex(int(c))
        rgb += ("00" + str(c))[len(str(c)):]
    return rgb

# get a range of colors from green to red
# List<int> scoreVectorList
# return a List<List<String>> shadeValues
def getShadeValues(scoreVectorList):
    shadeValues = []

    for row in scoreVectorList:
        sortedRow = sorted(set(list(row.values())))
        highestRank = len(sortedRow) - 1

        newRow = []
        greenColor = "6cbf6c"
        whiteColor = "ffffff"
        for index in row:
            rank = sortedRow.index(row[index])

            if highestRank == 0:
                # must be the winner
                newRow.append("#" + greenColor)
                continue

            # make the colors closer to the left lighter (higher value) and toward the right
            #   darker (lower value)

            # the 5th row is Simplified Bucklin (lower score is better so reverse the colorings
            #   for this row)
            counter = len(shadeValues)
            if counter != 4:
                luminance = 1 - rank / float(highestRank)
            else:
                luminance = rank / float(highestRank)

            # set lowest rank to white
            if luminance == 1:
                newRow.append("#" + whiteColor)
                continue
            if luminance <= 0.5:
                luminance /= 2.0

            newRow.append(colorLuminance(greenColor, luminance))

        shadeValues.append(newRow)
    return shadeValues

# find the minimum number of votes needed to change the poll results
# List<Response> latest_responses
# return List<int> marginList
def getMarginOfVictory(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return []

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return []
    marginList = []
    for x in range(0,len(getListPollAlgorithms())):
        marginList.append(-1)
    marginList[0] = MechanismPlurality().getMov(pollProfile)
    marginList[1] = MechanismBorda().getMov(pollProfile)
    marginList[2] = MechanismVeto().getMov(pollProfile)
    marginList[3] = MechanismKApproval(3).getMov(pollProfile)
    marginList[4] = MechanismSimplifiedBucklin().getMov(pollProfile)
    #marginList[12] = MechanismPluralityRunOff().getMov(pollProfile)

    return marginList

# used to help find the recommended order
# User user
# User otherUser
# return double kendall_tau
def getKTScore(user, otherUser):
    kendall_tau = 0
    num = 0
    questions = Question.objects.all().filter(question_voters=otherUser).filter(question_voters=user)
    for q in questions:
        userResponse = q.response_set.filter(user=user).reverse()
        other_user_response = q.response_set.filter(user=otherUser).reverse()
        if len(userResponse) > 0 and len(other_user_response) > 0:
            num = num + 1
            userResponse = get_object_or_404(Dictionary, response=userResponse[0])
            other_user_response = get_object_or_404(Dictionary, response=other_user_response[0])
            kendall_tau += getKendallTauScore(userResponse, other_user_response)

    if num != 0:
        kendall_tau /= num
    if kendall_tau == 0:
        kendall_tau = .25
    else:
        kendall_tau = 1/(1 + kendall_tau)
    return kendall_tau

# use other responses to recommend a response order for you
# responses are sorted from latest to earliest
# List<Response> response
# request request
# List<Item> default_order
# return List<Item> final_list
def getRecommendedOrder(other_user_responses, request, default_order):
    # no responses
    if len(other_user_responses) == 0:
        return default_order

    # if the poll owner added more choices during the poll, then reset using the default order
    itemsLastResponse = len(getCandidateMap(other_user_responses[0]))
    itemsCurrent = default_order.count()
    if itemsLastResponse != itemsCurrent:
        return default_order

    # iterate through all the responses
    preferences = []
    for resp in other_user_responses:
        user = request.user
        otherUser = resp.user

        # get current user and other user preferences
        KT = getKTScore(user, otherUser)
        pref_graph = getPreferenceGraph(resp, cand_map)
        preferences.append(Preference(pref_graph, KT))

    cand_map = getCandidateMap(other_user_responses[0])
    pollProfile = Profile(cand_map, preferences)

    # incomplete answers
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return default_order

    # return the order based off of ranking
    pref = MechanismBorda().getCandScoresMap(pollProfile)
    l = list(sorted(pref.items(), key=lambda kv: (kv[1], kv[0])))
    final_list = []
    for p in reversed(l):
        final_list.append(cand_map[p[0]])
    return final_list

# function to add voter to voter list (invite only)
# can invite new voters at any time
def addVoter(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    creator_obj = User.objects.get(id=question.question_owner_id)

    newVoters = request.POST.getlist('voters')
    # send an invitation email
    email = request.POST.get('email') == 'email'
    question.emailInvite = email
    question.save()
    if email:
        email_class = EmailThread(request, question_id, 'invite')
        email_class.start()
    try:
        if(type(newVoters) == list):
            # add each voter to the question by username
            for voter in newVoters:
                voterObj = User.objects.get(username=voter)
                question.question_voters.add(voterObj.id)
    except User.DoesNotExist:
        print("User does not exist in function addVoter().") # use logging
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    data = "{}"
    mimetype = 'application/json'
    return HttpResponse(data, mimetype)

def addVoters(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    creator_obj = User.objects.get(id=question.question_owner_id)

    email = request.POST.get('email') == 'email'

    mailSub = request.POST.get('mailNotificationSubject1')
    mailBody = request.POST.get('mailNotificationBody1')

    newVoters = request.POST.getlist('voters')
    if newVoters: 
        try:
            for voter in newVoters:
                voterObj = User.objects.get(username=voter)
                question.question_voters.add(voterObj.id)
            
            if email:
                # print("Email sending logic here to invite users")
                email_class = EmailThread(request, question_id, 'invite', newVoters)
                email_class.start()
                messages.success(request,"The Email has been sent to the added users!")

                # mail.send_mail(mailSub,
                #             mailBody,
                #             'opra@cs.binghamton.edu',
                #             ['mukhil1140@gmail.com'], # newVoters
                #             html_message='')
                
        except User.DoesNotExist:
            print("User does not exist in function addVoters().")
            request.session['setting'] = 1
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    newGroups = request.POST.getlist('groups')
    votersEmailIDsInGroups=[]
    if newGroups:
        for group in newGroups:
            groupObj = Group.objects.get(name=group)
            voters = groupObj.members.all()
            question.question_voters.add(*voters)
            votersEmailIDsInGroups = votersEmailIDsInGroups + [voter.username for voter in voters] 
        
        for mailID in votersEmailIDsInGroups:
            if mailID in newVoters:
                votersEmailIDsInGroups.remove(mailID)

        if email:
            # print("Email sending logic here to invite group users")
            email_class = EmailThread(request, question_id, 'invite-group', votersEmailIDsInGroups)
            email_class.start()
            messages.success(request,"The Email has been sent to the added users!")

            # mail.send_mail(mailSub,
            #                 mailBody,
            #                 'opra@cs.binghamton.edu',
            #                 ['mukhil1140@gmail.com'], # votersEmailIDsInGroups
            #                 html_message='')

    question.emailInvite = email
    # if email:
    #     email_class = EmailThread(request, question_id, 'invite')
    #     email_class.start()
    question.save()
    emailSettings(request, question_id)
    messages.success(request, "Selected users have been addedd to "+ question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

# Save the recently uploaded csv text
def saveLatestCSV(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    creator_obj = User.objects.get(id=question.question_owner_id)

    recentCSVText = request.POST.get('votersCSVText')

    try:
        question.recentCSVText = recentCSVText
        question.save();
        addUsersAndSendEmailInvite(request, question_id)
    except Exception as e:
        print(e)
    request.session['setting'] = 1
    messages.success(request, "The users have been added to "+ question.question_text)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def sendEmail(toEmails, mailSubject, mailBody):
    # logic to send email from opra mail id 
    mail.send_mail(mailSubject,
                    mailBody,
                    'opra@cs.binghamton.edu',
                    ['mukhil1140@gmail.com'], # toEmails
                    html_message='')
    return

def getRegAndUnRegUsers(userIDsFromCSV):
    regUsers, UnregUsers = [], []
    for userID in userIDsFromCSV:
        try:
            _user = User.objects.get(email = userID)
            regUsers.append(userID)
        except User.DoesNotExist: 
            UnregUsers.append(userID)

    return regUsers, UnregUsers

# Send email invite to Registered and Non registered Participants
# added using csv
def addUsersAndSendEmailInvite(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    creator_obj = User.objects.get(id=question.question_owner_id)

    recepients = request.POST.get('recepients')
    mailSubject = request.POST.get('mailSubject')
    mailBody = request.POST.get('mailBody')
    # existingUsers = User.objects.all()
    # existingUserIDs = [user.username for user in existingUsers]

    registers_users_of_current_poll = []
    UnRegistered_users_of_current_poll = []

    email = request.POST.get('email') == 'email'

    try: 
        recentCSVText = question.recentCSVText
        if(recentCSVText is not None): 
            userIDsFromCSV = recentCSVText.split(",")
            userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]

            # The invited user to this poll might be already registered with OPRA
            # for userID in userIDsFromCSV:
            #     if userID in existingUserIDs:
            #         registers_users_of_current_poll.append(userID)
            #     else:
            #         UnRegistered_users_of_current_poll.append(userID)

            # modified Logic to segregate Reg/Unreg Users
            registers_users_of_current_poll, UnRegistered_users_of_current_poll = getRegAndUnRegUsers(userIDsFromCSV)
            
            # Logic to add registered Voters to poll
            for voter in registers_users_of_current_poll:
                voterObj = User.objects.get(username=voter)
                question.question_voters.add(voterObj.id)

            '''
            Logic for adding Unregistered Voters : 

            Case 1:
            Get the list of emails of unregistered users for the current poll, after submitting the csv.
            Create an UnregisteredUser Object for every email in unregistered users for the current poll.
            Add the question to the list of polls invited to the newly created UnregisteredUser Object.

            Case 2:
            When the unregistered user has already been invited to registred with OPRA via other polls, 
            but still the user had not registred with OPRA. In this case, no new object for the UnregisteredUser has to 
            be created. Just add the question to the list of polls invited of the reterieved UnregisteredUser Object.

            '''

            # UnRegistered_users_of_current_poll - UnRegistered Participants/users of the current poll after submitting csv
            for email in UnRegistered_users_of_current_poll:
                # the voter_obj will be retrieved if the user is invited via other polls, 
                # but not registered with OPRA yet.
                try:
                    voter_obj = UnregisteredUser.objects.get(email = email)
                    voter_obj.polls_invited.add(question)
                
                # the voter_obj will be created if the user is invited to get registered with OPRA for first time
                except UnregisteredUser.DoesNotExist:
                    voter_obj = UnregisteredUser.objects.create(email=email)
                    voter_obj.save(); question.save();
                    voter_obj.polls_invited.add(question)

                
            # invited_users_across_all_polls = UnregisteredUser.objects.all()
            # for invited_voter_obj in invited_users_across_all_polls:
            #     print(invited_voter_obj.email, invited_voter_obj.polls_invited.count())
            
            csvEmails = request.POST.get('textAreaForCustomMails')
            customEmails = csvEmails.split(',')
            
            if email:
                if(recepients == "regVotersOnly"):
                    # print("Email sending logic for regVotersOnly")
                    email_class = EmailThread(request, question_id, 'invite-csv', registers_users_of_current_poll)
                    email_class.start()
                    # sendEmail(registers_users_of_current_poll, mailSubject, mailBody)
                elif(recepients == "unregVotersOnly"):
                    # print("Email sending logic for unregVotersOnly")
                    email_class = EmailThread(request, question_id, 'invite-csv', UnRegistered_users_of_current_poll)
                    email_class.start()
                    # sendEmail(UnRegistered_users_of_current_poll, mailSubject, mailBody)
                elif(recepients == "customEmails"):
                    # print("Email sending logic for customEmails")
                    email_class = EmailThread(request, question_id, 'invite-csv', customEmails)
                    email_class.start()
                    # sendEmail(customEmails, mailSubject, mailBody)
                elif(recepients == "allVoters"):
                    # print("Email sending logic for All voters")
                    email_class = EmailThread(request, question_id, 'invite-csv', userIDsFromCSV)
                    email_class.start()
                    # sendEmail(userIDsFromCSV, mailSubject, mailBody) 
                messages.success(request, "The Email has been sent to the recepients!")
            emailSettings(request, question_id)
            return     
    except Exception as e:
        print(e) # TODO: handle specific exception and change this to logging
        return 
    return 

# remove voters from a poll.
# should only be done before a poll starts
def removeVoter(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    newVoters = request.POST.getlist('voters')
    email = request.POST.get('email') == 'email'

    mailSub = request.POST.get('mailNotificationSubject')
    mailBody = request.POST.get('mailNotificationBody')

    question.emailDelete = email
    if email:
        # print("Email sending logic to remove user")
        email_class = EmailThread(request, question_id, 'remove')
        email_class.start()
        messages.success(request,"The Email has been sent to the removed users!")
    
    for voter in newVoters:
        voterObj = User.objects.get(username=voter)
        question.question_voters.remove(voterObj.id)
    # if email:
    #     mail.send_mail(mailSub,
    #                 mailBody,
    #                 'opra@cs.binghamton.edu',
    #                 ['mukhil1140@gmail.com'], # newVoters
    #                 html_message='')

    question.save()
    emailSettings(request, question_id)
    messages.success(request, "Selected users have been removed from "+ question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def setInitialSettings(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # map the 1-based dropdown index (1..6) to the actual bits (1,2,4,8,16,32)
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32}

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

    # 8) save changes
    question.save()

    # 9) redirect
    if question.question_type == 1:
        return HttpResponseRedirect(reverse("polls:regular_polls"))
    else:
        return HttpResponseRedirect(reverse("polls:allocation_tab"))


# set algorithms and visibility
def setPollingSettings(request, question_id):
    """
    Process the POST submission from _set_polling_settings.html and update the Question model
    with the chosen algorithms/bitmasks.
    """
    question = get_object_or_404(Question, pk=question_id)

    # Map the 1-based dropdown index to the actual bit:
    BIT_MAP = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 32}

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


# poll is open to anonymous voters
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

# poll is closed to anonymous voters
def closePoll(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.open = 0
    question.save()
    request.session['setting'] = 4
    messages.success(request, 'Your changes have been saved.')
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

# poll is closed to anonymous voters, open to people logged in
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
    #return HttpResponseRedirect(reverse('polls:regular_polls'))

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

# view for ordering voters for allocation
class AllocationOrder(views.generic.DetailView):
    model = Question
    template_name = 'polls/allocation_order.html'
    def get_context_data(self, **kwargs):
        ctx = super(AllocationOrder, self).get_context_data(**kwargs)
        currentAllocationOrder = self.object.allocationvoter_set.all()
        tempOrderStr = self.request.GET.get('order', '')
        if tempOrderStr == "null":
            ctx['question_voters'] = self.object.question_voters.all()
            return ctx

        # check if the user submitted a vote earlier and display that for modification
        if len(currentAllocationOrder) > 0:
            ctx['currentSelection'] = currentAllocationOrder

        ctx['question_voters'] = self.object.question_voters.all()
        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())

# manually set the allocation order of voters
def setAllocationOrder(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # get the voter order
    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    if orderStr == "":
        # the user must rank all voters
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    prefOrder = orderStr.split(",")
    if len(prefOrder) != len(question.question_voters.all()):
        # the user must rank all voters
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    #reset allocation order
    for voter in question.allocationvoter_set.all():
        voter.delete()

    # find ranking student gave for each item under the question
    item_num = 1
    for item in question.question_voters.all():
        arrayIndex = prefOrder.index("item" + str(item_num))
        if arrayIndex != -1:
            user = question.question_voters.all()[arrayIndex]
            # add pref to list
            voter, created = AllocationVoter.objects.get_or_create(question=question,
                                                                   user=user, response=None)
            voter.save()

        item_num += 1

    return HttpResponseRedirect(reverse('polls:viewAllocationOrder', args=(question.id,)))

# if the allocation mechanism is early-first or late-first serial dictatorship,
#   assign the order based off of latest response time
# Question question
# List<Response> latest_responses
def getInitialAllocationOrder(question, latest_responses):
    if len(latest_responses) == 0:
        return

    # assign the default allocation order from earliest to latest
    counter = len(question.item_set.all())
    for user_response in list(reversed(latest_responses)):
        # no more items left to allocate
        if counter == 0:
            return

        counter -= 1
        # create the object
        voter, created = AllocationVoter.objects.get_or_create(question=user_response.question,
                                                               user=user_response.user)
        # save the most recent response
        voter.response = user_response
        voter.save()
    return

# get the current allocation order for this poll
# if this poll is part of a multi-poll, then it must consider the order of the previous subpolls
# Question question
# List<Response> latest_responses
# return Query<AllocationVoter> allocation_order
def getCurrentAllocationOrder(question, latest_responses):
    # get the allocation order from the first multipoll
    allocation_order = []
    if question.m_poll == True:
        multipoll = question.multipoll_set.all()[0]
        firstSubpoll = multipoll.questions.all()[0]
        allocation_order = firstSubpoll.allocationvoter_set.all()

        # fix the allocation order from the first subpoll
        if len(allocation_order) == 0:
            # get allocation order
            getInitialAllocationOrder(question, latest_responses)
        else:
            # copy a new allocation order based off of the first subpoll
            for alloc_item in allocation_order:
                voter, created = AllocationVoter.objects.get_or_create(question=question,
                                                                       user=alloc_item.user)
                voter.response = question.response_set.reverse().filter(user=alloc_item.user)[0]
                voter.save()
        allocation_order = question.allocationvoter_set.all()
    else:
        # get the allocation order
        allocation_order = question.allocationvoter_set.all()

        # calculate initial order if there is none or if new voters are added during the poll
        if len(allocation_order) == 0 or len(allocation_order) != len(latest_responses):
            getInitialAllocationOrder(question, latest_responses)
            allocation_order = question.allocationvoter_set.all()

    return allocation_order

# order user responses similar to the allocation order
# Query<AllocationVoter> allocation_order
# return List<Response>
def getResponseOrder(allocation_order):
    response_set = []
    for order_item in allocation_order:
        question = order_item.question
        user = order_item.user

        # skip if no vote
        if question.response_set.reverse().filter(user=user, active=1).count() == 0:
            continue

        # save response
        response = question.response_set.reverse().filter(user=user, active=1)[0]
        order_item.response = response
        order_item.save()

        # add to the list
        response_set.append(response)
    return response_set

# update the database with the new allocation results
# Question question
# Dict<String, String> allocationResults
def assignAllocation(question, allocationResults):
    for username, item in allocationResults.items():
        currentUser = User.objects.filter(username=username).first()
        allocatedItem = question.item_set.get(item_text=item)
        mostRecentResponse = question.response_set.reverse().filter(user=currentUser, active=1)[0]
        mostRecentResponse.allocation = allocatedItem
        mostRecentResponse.save()
    return

# organize the data into items and responses (most recent) and then apply allocation algorithms
# to get the final result
# Question question
def getFinalAllocation(question):
    # the latest and previous responses are from latest to earliest
    response_set = question.response_set.filter(active=1).order_by('-timestamp')
    (latest_responses, previous_responses) = categorizeResponses(response_set)

    # no responses, so stop here
    if len(latest_responses) == 0:
        return

    allocation_order = getCurrentAllocationOrder(question, latest_responses)
    response_set = getResponseOrder(allocation_order) # get list of responses in specified order

    # make items and responses views.generic
    item_set = latest_responses[0].question.item_set.all()
    itemList = []
    for item in item_set:
        itemList.append(item.item_text)
    responseList = []
    for response in response_set:
        tempDict = {}
        dictionary = {}
        if response.dictionary_set.all().count() > 0:
            dictionary = Dictionary.objects.get(response=response)
        else:
            dictionary = buildResponseDict(response, response.question,
                                            getPrefOrder(response.resp_str,
                                            response.question))
        dictionary = interpretResponseDict(dictionary)
        for item, rank in dictionary.items():
            tempDict[item.item_text] = rank
        responseList.append((response.user.username, tempDict))

    allocationResults = allocation(question.poll_algorithm, itemList, responseList)
    assignAllocation(question, allocationResults)


# function to get preference order from a string
# String orderStr
# Question question
# return List<List<String>> prefOrder
def getPrefOrder(orderStr, question):
    # empty string
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
    
    # the user hasn't ranked all the preferences yet
    #if length != len(question.item_set.all()):
    #   return None

    return final_order

# function to process student submission
def vote(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    prevResponseCount = question.response_set.filter(user=request.user, active=1).count()
    # get the preference order

    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    behavior_string = request.POST["record_data"]
    #print(behavior_string)
    if prefOrder == None:
        # the user must rank all preferences
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # make Response object to store data
    comment = request.POST['comment']
    response = Response(question=question, user=request.user, timestamp=timezone.now(),
                        resp_str=orderStr, behavior_data=behavior_string)
    
    if comment != "":
        response.comment = comment
    response.save()

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

def coursematch_vote(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    prevResponseCount = question.response_set.filter(user=request.user, active=1).count()
    # get the preference order

    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    behavior_string = request.POST["record_data"]
    #print(behavior_string)
    if prefOrder == None:
        # the user must rank all preferences
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # make Response object to store data
    comment = request.POST['comment']
    response = Response(question=question, user=request.user, timestamp=timezone.now(),
                        resp_str=orderStr, behavior_data=behavior_string)
    
    if comment != "":
        response.comment = comment
    response.save()

    if question.related_class != None and request.user not in question.related_class.students.all():
        question.related_class.students.add(request.user)

    if question.related_class != None and request.user == question.related_class.teacher:
        formatted_order = sorted([i[4:] for i in prefOrder[0]])
        question.correct_answer = json.dumps(formatted_order)
        question.save()
    
    question.num_courses = json.loads(request.POST["record_data"])["num_courses"]
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

    return HttpResponseRedirect(reverse('polls:coursematch', args=(question.id,)))

# function to process student submission for course match
def vote(request, question_id):
    print(f'in vote(), request {request}, question id {question_id}')
    question = get_object_or_404(Question, pk=question_id)

    prevResponseCount = question.response_set.filter(user=request.user, active=1).count()
    # get the preference order

    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    behavior_string = request.POST["record_data"]
    #print(behavior_string)
    if prefOrder == None:
        # the user must rank all preferences
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    # make Response object to store data
    comment = request.POST['comment']
    response = Response(question=question, user=request.user, timestamp=timezone.now(),
                        resp_str=orderStr, behavior_data=behavior_string)
    
    if comment != "":
        response.comment = comment
    response.save()

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

# create a new dictionary that stores the preferences and rankings
# Response response
# Question question
# List<List<String>> prefOrder
def buildResponseDict(response, question, prefOrder):
    d = {}

    if prefOrder is None:
        return d
    # find ranking user gave for each item under the question
    item_num = 1
    for item in question.item_set.all():
        rank = 1
        #Flag for examining the case when new choices are added to poll after poll starts
        flag = True
        for l in prefOrder:
            string = "item" + str(item)
            if string in l:
                d[item] = rank
                #If the item is found in preforder, the set flag to false
                flag = False
                break
            rank += 1
        if flag:
            d[item] = 1000
        # if arrayIndex == -1:
        #     # set value to lowest possible rank
        #     d[item] = question.item_set.all().count()
        # else:
        #     # add 1 to array index, since rank starts at 1
        #     rank = (prefOrder.index("item" + str(item))) + 1
        #     # add pref to response dict
        #     d[item] = rank
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


# join a poll without logging in
def anonymousJoin(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    name = request.POST['name']
    request.session['anonymousvoter'] = name
    return HttpResponseRedirect(reverse('polls:detail', args=(question.id,)))

# submit a vote without logging in
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
    #print(orderStr)
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

# Mixture API
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

# Mixture API
def mixtureAPI_test(request):
    context = RequestContext(request)
    return render(request, 'polls/api_test.html', context)

#Poll search API
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

# Add function
def addFolder(request):
    if request.method == 'POST':
        title = request.POST['title']
        fold = Folder(user=request.user, title=title, edit_date=timezone.now())
        fold.save()
        for poll in request.POST.getlist('polls'):
            try:
                q = Question.objects.filter(id=int(poll)).all()[0]
                fold.questions.add(q)
            except:
                print("Error: poll not working")
        fold.save()
        # print(fold.questions)
        return HttpResponseRedirect(reverse('polls:regular_polls'))
    else:
        print("Error: not post in addFolder function line 1993")

def deleteFolder(request, folder_id):
    try:
        folder_obj = get_object_or_404(Folder, pk=folder_id)
        folder_obj.delete()
    except:
        print("Problem in retrieving Folder object with id:" ,folder_id)
    return HttpResponseRedirect(reverse('polls:regular_polls'))

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


class RGView(views.generic.ListView):
    template_name = 'events/ResearchGroup.html'
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())
    def get_context_data(self, **kwargs):
        ctx = super(RGView, self).get_context_data(**kwargs)
        return ctx

class RGENView(views.generic.ListView):
    template_name = 'events/ResearchGroupEN.html'
    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())
    def get_context_data(self, **kwargs):
        ctx = super(RGENView, self).get_context_data(**kwargs)
        return ctx

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


class SelfRegisterView(views.generic.DetailView):
    model = Question
    template_name = "polls/self_register.html"
    def get_context_data(self, **kwargs):
        ctx = super(SelfRegisterView, self).get_context_data(**kwargs)
        if check_duplicate_sign_up(self.request.user,self.object):
            ctx["submitted"] = True
        return ctx

def change_self_sign_up(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    signup_string = request.POST["selfsignup"]
    if signup_string == "allow":
        question.allow_self_sign_up = 1
    else:
        question.allow_self_sign_up = 0
    question.save()
    request.session['setting'] = 4
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def self_sign_up(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    if request.method == "POST" and request.user != question.question_owner:
        if check_duplicate_sign_up(request.user,question):
            return HttpResponse("You can only register once!")
        item_name = request.POST['item_name']
        new_request = SignUpRequest(question=question,user=request.user,item_name=item_name,timestamp=timezone.now())
        new_request.save()
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
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

def upload_csv_choices(request, question_id):
    """
    Handle CSV file upload to add multiple alternatives at once.
    Expected CSV format:
    - One row per item
    - First column: Item name (required)
    - Second column: Item description (optional)
    - Third column: Asset name (optional)
    - Additional columns are ignored
    
    """
    question = get_object_or_404(Question, pk=question_id)
    
    # check if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST' and request.FILES.get('csvFile'):
        csv_file = request.FILES['csvFile']
        
        # validate file type
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a CSV file.")
            return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
        
        try:
            # read CSV file
            csv_text = TextIOWrapper(csv_file.file, encoding='utf-8')
            csv_reader = csv.reader(csv_text)
            
            items_added = 0
            items_skipped = 0
            items_with_desc = 0
            items_with_images = 0
            
            for row in csv_reader:
                if not row or not row[0].strip():  # skip empty rows or rows without name
                    continue
                    
                item_name = row[0].strip()
                item_description = row[1].strip() if len(row) > 1 else ""
                asset_name = row[2].strip() if len(row) > 2 else ""
                
                # check duplicates
                if question.item_set.filter(item_text=item_name).exists():
                    items_skipped += 1
                    continue
                
                # create new item
                recentlyAdded = question.status == 4
                item = Item(
                    question=question,
                    item_text=item_name,
                    item_description=item_description,
                    image=asset_name if asset_name else None,
                    timestamp=timezone.now(),
                    recently_added=recentlyAdded
                )
                item.save()
                items_added += 1
                if item_description:
                    items_with_desc += 1
                if asset_name:
                    items_with_images += 1
            
            # provide feedback
            if items_added > 0:
                success_msg = f"Successfully added {items_added} items"
                details = []
                if items_with_desc > 0:
                    details.append(f"{items_with_desc} with descriptions")
                if items_with_images > 0:
                    details.append(f"{items_with_images} with images")
                if details:
                    success_msg += f" ({', '.join(details)})"
                messages.success(request, success_msg + ".")
            if items_skipped > 0:
                messages.warning(request, f"Skipped {items_skipped} duplicate items.")
                
        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")
    
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def upload_bulk_images(request, question_id):
    """
    Handle bulk image upload to create multiple items at once.
    Each image file will become a new item, using the filename (without extension) as the item name.
    """
    question = get_object_or_404(Question, pk=question_id)
    
    # if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can add alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST' and request.FILES.getlist('imageFiles'):
        try:
            image_files = request.FILES.getlist('imageFiles')
            name_prefix = request.POST.get('namePrefix', '').strip()
            
            items_added = 0
            items_skipped = 0
            
            for image_file in image_files:
                # get filename without extension as item name
                filename = os.path.splitext(image_file.name)[0]
                item_name = f"{name_prefix}{filename}" if name_prefix else filename
                
                # check for duplicates
                if question.item_set.filter(item_text=item_name).exists():
                    items_skipped += 1
                    continue
                
                # create new item
                recentlyAdded = question.status == 4
                item = Item(
                    question=question,
                    item_text=item_name,
                    image=image_file,
                    timestamp=timezone.now(),
                    recently_added=recentlyAdded
                )
                item.save()
                items_added += 1
            
            if items_added > 0:
                messages.success(request, f"Successfully added {items_added} items with images.")
            if items_skipped > 0:
                messages.warning(request, f"Skipped {items_skipped} items due to duplicate names.")
                
        except Exception as e:
            messages.error(request, f"Error processing image files: {str(e)}")
    
    request.session['setting'] = 0
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

def delete_items(request, question_id):
    """Delete multiple items or all items from a poll."""
    question = get_object_or_404(Question, pk=question_id)
    
    # check if user is poll owner
    if request.user != question.question_owner:
        messages.error(request, "Only the poll owner can delete alternatives.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    
    if request.method == 'POST':
        if 'delete_all' in request.POST:
            # delete all 
            question.item_set.all().delete()
            messages.success(request, "All items have been deleted.")
        else:
            # delete selected 
            try:
                item_ids = json.loads(request.POST.get('item_ids', '[]'))
                question.item_set.filter(id__in=item_ids).delete()
                messages.success(request, f"{len(item_ids)} items have been deleted.")
            except Exception as e:
                messages.error(request, f"Error deleting items: {str(e)}")
    
    request.session['setting'] = 0

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))