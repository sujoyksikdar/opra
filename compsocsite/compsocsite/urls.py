"""compsocsite URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  re_path(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  re_path(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  re_path(r'^blog/', include('blog.urls'))
"""
from django.urls import include, re_path
from django.contrib import admin
from django.views.generic.base import RedirectView
from django.conf import settings
from django.views.static import serve
from django.views.generic import TemplateView
from appauth import views
from polls.views import sendMessage
from polls.views import CourseMatchListView

urlpatterns = [
    re_path(r'^$', RedirectView.as_view(url='/polls/main')),
    re_path(r'^polls/', include('polls.urls')),
    re_path(r'^allocations/', include('allocation.urls')),
    re_path(r'^mock_election/', include('mock_election.urls')),
    re_path(r'^groups/', include('groups.urls')),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^auth/', include('appauth.urls')),
    re_path(r'^sessions/', include('sessions_local.urls')),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATICFILES_DIRS[0], 'show_indexes':True}),
    re_path(r'^multipolls/', include('multipolls.urls')),
    re_path(r'^message$', sendMessage, name='message'),
    re_path('accounts/profile', RedirectView.as_view(url='/polls/main')),
    re_path(r'^socialSignup/$', views.socialSignup, name='socialSignup'),
    re_path('accounts/', include('allauth.urls')),  
    
    # user_guide (Django templates — replaces VitePress static files)
    re_path(r'^user_docs/$', RedirectView.as_view(url='/user_docs/polls/'), name='user_guide'),
    re_path(r'^user_docs/polls/$', TemplateView.as_view(template_name='user_guide_polls.html'), name='user_guide_polls'),
    re_path(r'^user_docs/allocations/$', TemplateView.as_view(template_name='user_guide_allocations.html'), name='user_guide_allocations'),
    re_path(r'^user_docs/groups/$', TemplateView.as_view(template_name='user_guide_groups.html'), name='user_guide_groups'),
    re_path(r'^user_docs/mock-election/$', TemplateView.as_view(template_name='user_guide_mock_election.html'), name='user_guide_mock_election'),
    
    # custom
    re_path(r'^soccoursematch$', CourseMatchListView.as_view(), name='soccoursematch'),
]
