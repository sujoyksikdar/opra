import itertools
import json
import logging
import random
from functools import wraps

import pandas as pd
from appauth.models import *
from django import views
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..models import *
from ..utils import getCurrentSelection, getUnrankedCandidates, isPrefReset

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


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
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


class CodeAllocationView(views.generic.ListView):
    """
    Allocation view for code-based users.
    Only shows 'participated in' allocations.
    """
    template_name = 'polls/allocation_tab_code.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        qid = self.request.session.get('code_question_id')
        return Question.objects.filter(pk=qid, question_type=2).order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super(CodeAllocationView, self).get_context_data(**kwargs)
        qid = self.request.session.get('code_question_id')

        ctx['folders'] = []
        ctx['polls_created'] = []  # no create
        ctx['active_polls'] = list(Question.objects.filter(question_type=2).order_by('-pub_date'))
        polls = Question.objects.filter(pk=qid, question_type=2)
        ctx['polls_participated'] = list(polls)

        self.request.session['questionType'] = 2
        return ctx


class CourseMatchView(views.generic.DetailView):
    """Define course match preference submission page view."""

    model = Question
    template_name = 'events/CourseMatch/soccoursematchdetail.html'
        
    def is_student(self, email: str) -> bool:
        try:
            with open('compsocsite/coursematch/StudentIDEmails.csv', 'r') as f:
                email_list = pd.read_csv(f)['Email Address'].tolist()
                if email in email_list:
                    return True
            return False
        except FileNotFoundError:
            # File not found, consider everyone a student in this case
            return True
    
    def get_order_from_email(self, email: str) -> list:
        try:
            with open('compsocsite/coursematch/SeedStudentPreferences.json', 'r') as f:
                seed_prefs = json.load(f)
                if email in seed_prefs:
                    return seed_prefs[email]
                else:
                    return []
        except (FileNotFoundError, json.JSONDecodeError):
            # File not found or invalid JSON, return empty list
            return []
    
    
    def get_random_order(self, ctx) -> list:
        """Generate a random ordering over the items"""
        
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order

    def get_items_dict(self, ctx) -> dict:
        """Get a dictionary of items with their text as keys."""
        
        items_dict = {item.item_text.replace('\ufeff', ''): item for item in ctx['object'].item_set.all()}
        return items_dict
    
    def get_order(self, ctx) -> list:
        """Define the initial order to be displayed on the page."""
        
        # default_order = list(ctx['object'].item_set.all())
        user_email = self.request.user.email
        items_dict = self.get_items_dict(ctx)
        default_order = []
        if self.is_student(user_email):
            seed_order = self.get_order_from_email(user_email)
            if seed_order == []:
                default_order = self.get_random_order(ctx)
            else:
                default_order = []
                for item_text in seed_order:
                    if item_text in items_dict:
                        default_order.append(items_dict[item_text])
        else:
            default_order = self.get_random_order(ctx)
        return default_order
    
    def get_num_courses(self, ctx) -> int:
        """Get the number of courses to display."""
        
        return ctx['num_courses']

    def get_context_data(self, **kwargs):
        ctx = super(CourseMatchView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""

        # Get the responses for the current logged-in user from latest to earliest
        # Only filter by user if the user is authenticated
        if self.request.user.is_authenticated:
            currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()
        else:
            currentUserResponses = []

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

        # Set default num_courses
        ctx['num_courses'] = 3

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            try:
                ctx['num_courses'] = json.loads(latest_response.behavior_data)['num_courses']
            except (KeyError, json.JSONDecodeError):
                pass  # Keep default value if error
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

        else:
            # no history so display the list of choices
            ctx['items'] = self.get_order(ctx)
        return ctx
    
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())
