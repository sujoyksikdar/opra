from django.urls import re_path
from django.contrib.auth.decorators import login_required
from . import views

app_name = 'allocation'

urlpatterns = [
    re_path(r'^allocation_tab$', login_required(views.RegularAllocationView.as_view()), name='allocation_tab'),
    re_path(r'^allocation_tab/code$', views.CodeAllocationView.as_view(), name='allocation_tab_code'),
    re_path(r'^(?P<pk>[0-9]+)/allocate/results/$', views.AllocateResultsView.as_view(), name='allocate_results'),
    re_path(r'^(?P<pk>[0-9]+)/allocate/order$', views.AllocationOrder.as_view(), name='viewAllocationOrder'),
    re_path(r'^(?P<question_id>[0-9]+)/allocate/order/set/$', views.setAllocationOrder, name='setAllocationOrder'),
    re_path(r'^(?P<question_id>[0-9]+)/stop/allocation/$', views.stopAllocation, name='stopAllocation'),
]
