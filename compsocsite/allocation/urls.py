from django.urls import re_path, path
from django.contrib.auth.decorators import login_required
from . import views
from . import email
from . import record

app_name = 'allocation'

urlpatterns = [
    # ── Search API ─────────────────────────────────────────────────────────────
    re_path(r'^api/search/$', views.get_allocation_polls, name='get_allocation_polls'),
    re_path(r'^api/get_voters/$', views.get_allocation_voters, name='get_allocation_voters'),

    # ── List / tabs ────────────────────────────────────────────────────────────
    re_path(r'^allocation_tab$', login_required(views.RegularAllocationView.as_view()), name='allocation_tab'),
    re_path(r'^allocation_tab/code$', views.CodeAllocationView.as_view(), name='allocation_tab_code'),

    # ── Creation wizard ────────────────────────────────────────────────────────
    re_path(r'^add_step1/$', views.AllocationAddStep1, name='AddStep1'),
    re_path(r'^(?P<pk>[0-9]+)/add_step2/$', views.AllocationAddStep2View.as_view(), name='AddStep2'),
    re_path(r'^(?P<pk>[0-9]+)/add_step3/$', views.AllocationAddStep3View.as_view(), name='AddStep3'),
    re_path(r'^(?P<pk>[0-9]+)/add_step4/$', views.AllocationAddStep4View.as_view(), name='AddStep4'),

    # ── Item management ────────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/choice/add/$', views.allocationAddChoice, name='addchoice'),
    re_path(r'^(?P<question_id>[0-9]+)/editchoice/$', views.allocationEditChoice, name='editchoice'),
    re_path(r'^(?P<question_id>[0-9]+)/edit/basic/$', views.allocationEditBasicInfo, name='editBasicInfo'),
    re_path(r'^choice/delete/([0-9]+)/$', views.allocationDeleteChoice, name='delchoice'),
    re_path(r'^(?P<question_id>[0-9]+)/items/delete/$', views.allocation_delete_items, name='delete_items'),
    re_path(r'^(?P<question_id>[0-9]+)/choices/upload/csv/$', views.allocation_upload_csv_choices, name='upload_csv_choices'),
    re_path(r'^(?P<question_id>[0-9]+)/choices/upload/image/$', views.allocation_upload_single_image, name='upload_single_image'),
    re_path(r'^(?P<question_id>[0-9]+)/choices/upload/bulk/$', views.allocation_upload_bulk_images, name='upload_bulk_images'),

    # ── Voter management ───────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/addvoter/$', views.allocationAddVoter, name='addvoter'),
    re_path(r'^(?P<question_id>[0-9]+)/delvoter/$', views.allocationRemoveVoter, name='delvoter'),
    re_path(r'^(?P<question_id>[0-9]+)/removegroupvoters/$', views.allocationRemoveGroupVoters, name='removegroupvoters'),
    re_path(r'^(?P<question_id>[0-9]+)/savelatestcsv/$', views.allocationSaveLatestCSV, name='savelatestcsv'),
    re_path(r'^(?P<question_id>[0-9]+)/send_email_invites/$', views.allocationSendEmailInvites, name='send_email_invites'),
    re_path(r'^(?P<question_id>[0-9]+)/codes/add/$', views.allocationAddCodes, name='addcodes'),
    re_path(r'^(?P<question_id>[0-9]+)/codes/export/$', views.allocationExportCodes, name='exportcodes'),

    # ── Response management ────────────────────────────────────────────────────
    re_path(r'^(?P<response_id>[0-9]+)/deleteuservotes/$', views.allocationDeleteUserVotes, name='deluservotes'),
    re_path(r'^(?P<response_id>[0-9]+)/restoreuservotes/$', views.allocationRestoreUserVotes, name='resuservotes'),

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/start/$', views.startAllocation, name='start'),
    re_path(r'^(?P<question_id>[0-9]+)/pause/$', views.pauseAllocation, name='pause'),
    re_path(r'^(?P<question_id>[0-9]+)/resume/$', views.resumeAllocation, name='resume'),
    re_path(r'^(?P<question_id>[0-9]+)/stop/$', views.stopAllocation, name='stopAllocation'),
    re_path(r'^delete/([0-9]+)/$', views.deleteAllocation, name='delallocation'),

    # ── Duplicate ──────────────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/duplicateallocation/$', views.allocationDuplicatePoll, name='dupallocation'),

    # ── Access management ──────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/changeType/$', views.allocationChangeType, name='changeType'),
    re_path(r'^(?P<question_id>[0-9]+)/changeselfsignup/$', views.allocationChangeSelfsignup, name='changeselfsignup'),
    re_path(r'^(?P<pk>[0-9]+)/selfregister/$', views.AllocationSelfRegisterView.as_view(), name='selfregister'),
    re_path(r'^(?P<question_id>[0-9]+)/selfsignup/$', views.allocationSelfSignup, name='selfsignup'),
    re_path(r'^request/(?P<request_id>[0-9]+)/approve/$', views.allocationApproveRequest, name='approverequest'),

    # ── Email ──────────────────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/emailSettings/$', email.allocationEmailSettings, name='emailSettings'),
    re_path(r'^(?P<question_id>[0-9]+)/emailNow/$', email.allocationEmailNow, name='emailNow'),

    # ── Settings ───────────────────────────────────────────────────────────────
    re_path(r'^(?P<question_id>[0-9]+)/settings/initial$', views.allocationSetInitialSettings, name='setinitial'),
    re_path(r'^(?P<question_id>[0-9]+)/settings/algorithm$', views.allocationSetPollingSettings, name='setPollingSettings'),
    re_path(r'^(?P<question_id>[0-9]+)/settings/visibility$', views.allocationSetVisibilitySettings, name='setVisibilitySettings'),

    # ── Poll info ──────────────────────────────────────────────────────────────
    re_path(r'^(?P<pk>[0-9]+)/allocationinfo/$', views.AllocationPollInfoView.as_view(), name='allocationinfo'),

    # ── User Records ───────────────────────────────────────────────────────────
    re_path(r'^(?P<pk>[0-9]+)/recordView/$', record.AllocationRecordView.as_view(), name='recordView'),
    re_path(r'^(?P<question_id>[0-9]+)/downloadlatestvotes/$', record.downloadAllocationLatestVotes, name='downloadlatestvotes'),

    # ── Voting ─────────────────────────────────────────────────────────────────
    re_path(r'^(?P<pk>[0-9]+)/$', views.AllocationDetailView.as_view(), name='detail'),
    re_path(r'^(?P<question_id>[0-9]+)/vote/$', views.allocationVote, name='vote'),
    re_path(r'^(?P<pk>[0-9]+)/confirmation/$', views.AllocationConfirmationView.as_view(), name='confirmation'),

    # ── Results ────────────────────────────────────────────────────────────────
    re_path(r'^(?P<pk>[0-9]+)/allocate/results/$', views.AllocateResultsView.as_view(), name='allocate_results'),

    # ── Allocation order ───────────────────────────────────────────────────────
    re_path(r'^(?P<pk>[0-9]+)/allocate/order$', views.AllocationOrder.as_view(), name='viewAllocationOrder'),
    re_path(r'^(?P<question_id>[0-9]+)/allocate/order/set/$', views.setAllocationOrder, name='setAllocationOrder'),
]
