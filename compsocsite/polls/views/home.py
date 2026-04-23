import itertools
import json
import logging
import random
from functools import wraps

from appauth.models import *
from django import views
from django.shortcuts import redirect
from django.utils import timezone
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..models import *
from ..utils import (getAllocMethods, getCurrentSelection,
                     getListPollAlgorithms, getUnrankedCandidates,
                     getViewPreferences, isPrefReset)

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
    """Define demo poll for course matching functionality."""
    
    model = Question
    template_name = 'events/CourseMatch/coursematchdemo.html'
    
    def is_student(self, email: str) -> bool:
        # In demo mode, treat all users as students
        return True
    
    def get_order_from_email(self, email: str) -> list:
        # For demo, return empty list to use random order
        return []
    
    def get_random_order(self, ctx) -> list:
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order
    
    def get_order(self, ctx) -> list:
        """Define the initial order to be displayed on the page."""
        # For demo, always use random order
        default_order = self.get_random_order(ctx)
        return default_order
    
    def get_num_courses(self, ctx) -> int:
        """Get the number of courses to display."""
        # Default to 3 courses for demo if not set
        return ctx.get('num_courses', 3)

    def get_context_data(self, **kwargs):
        ctx = super(DemoView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""
        ctx['demo_message'] = "This is a demo of the CourseMatchView functionality."

        # Case for anonymous user
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
                # For demo, set a default number of courses
                ctx['num_courses'] = 3
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            try:
                ctx['num_courses'] = json.loads(latest_response.behavior_data)['num_courses']
            except:
                ctx['num_courses'] = 3  # Default for demo
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment
        else:
            # For demo, set a default number of courses
            ctx['num_courses'] = 3
        
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


class DemoView(views.generic.DetailView):
    """Define demo poll for course matching functionality."""
    
    model = Question
    template_name = 'events/CourseMatch/coursematchdemo.html'
    
    def is_student(self, email: str) -> bool:
        # In demo mode, treat all users as students
        return True
    
    def get_order_from_email(self, email: str) -> list:
        # For demo, return empty list to use random order
        return []
    
    def get_random_order(self, ctx) -> list:
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order
    
    def get_order(self, ctx) -> list:
        """Define the initial order to be displayed on the page."""
        # For demo, always use random order
        default_order = self.get_random_order(ctx)
        return default_order
    
    def get_num_courses(self, ctx) -> int:
        """Get the number of courses to display."""
        # Default to 3 courses for demo if not set
        return ctx.get('num_courses', 3)

    def get_context_data(self, **kwargs):
        ctx = super(DemoView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""
        ctx['demo_message'] = "This is a demo of the CourseMatchView functionality."

        # Case for anonymous user
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
                # For demo, set a default number of courses
                ctx['num_courses'] = 3
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            try:
                ctx['num_courses'] = json.loads(latest_response.behavior_data)['num_courses']
            except:
                ctx['num_courses'] = 3  # Default for demo
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment
        else:
            # For demo, set a default number of courses
            ctx['num_courses'] = 3
        
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


class CourseMatchDemoView(views.generic.DetailView):
    """Define demo poll for course matching functionality."""
    
    model = Question
    template_name = 'events/CourseMatch/coursematchdemo.html'
    
    def is_student(self, email: str) -> bool:
        # In demo mode, treat all users as students
        return True
    
    def get_order_from_email(self, email: str) -> list:
        # For demo, return empty list to use random order
        return []
    
    def get_random_order(self, ctx) -> list:
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order
    
    def get_order(self, ctx) -> list:
        """Define the initial order to be displayed on the page."""
        # For demo, always use random order
        default_order = self.get_random_order(ctx)
        return default_order
    
    def get_num_courses(self, ctx) -> int:
        """Get the number of courses to display."""
        # Default to 3 courses for demo if not set
        return ctx.get('num_courses', 3)

    def get_context_data(self, **kwargs):
        ctx = super(CourseMatchDemoView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""
        ctx['demo_message'] = "This is a demo of the CourseMatchView functionality."

        # Case for anonymous user
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
                # For demo, set a default number of courses
                ctx['num_courses'] = 3
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            try:
                ctx['num_courses'] = json.loads(latest_response.behavior_data)['num_courses']
            except:
                ctx['num_courses'] = 3  # Default for demo
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment
        else:
            # For demo, set a default number of courses
            ctx['num_courses'] = 3
        
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
