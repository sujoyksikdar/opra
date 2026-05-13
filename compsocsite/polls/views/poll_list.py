import logging
from functools import wraps

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


class CodePollsView(views.generic.ListView):
    """
    Polls view for code-based users.
    Only shows 'participated in' polls.
    """
    template_name = 'polls/regular_polls_code.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        qid = self.request.session.get('code_question_id')
        return Question.objects.filter(pk=qid, question_type=1).order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super(CodePollsView, self).get_context_data(**kwargs)
        qid = self.request.session.get('code_question_id')

        ctx['folders'] = []
        ctx['polls_created'] = []  
        ctx['active_polls'] = list(Question.objects.filter(question_type=1).order_by('-pub_date'))
        polls = Question.objects.filter(pk=qid, question_type=1)
        ctx['polls_participated'] = list(polls)

        self.request.session['questionType'] = 1
        return ctx


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
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


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
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
