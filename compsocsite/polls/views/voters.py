import csv
import io
import logging
import secrets
import string
from functools import wraps

from appauth.models import *
from django import views
from django.contrib import messages
from django.core import mail
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from groups.models import *
from multipolls.models import *
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..email import EmailThread, emailSettings
from ..models import *
from .poll_management import check_duplicate_sign_up

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
    all_new_usernames = list(newVoters)
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
            group_usernames = [voter.username for voter in voters]
            votersEmailIDsInGroups.extend(group_usernames)
            all_new_usernames.extend(group_usernames)        
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
    existing_emails = question.recentCSVText.split(",") if question.recentCSVText else []
    updated_list = list(set(existing_emails + all_new_usernames))
    question.recentCSVText = ",".join(updated_list)
    question.save()
    emailSettings(request, question_id)
    messages.success(request, "Selected users have been addedd to "+ question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def saveLatestCSV(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    creator_obj = User.objects.get(id=question.question_owner_id)

    recentCSVText = request.POST.get('votersCSVText')

    try:
        question.recentCSVText = recentCSVText
        question.save() 
        addUsersFromCSV(request, question_id)
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


def addUsersFromCSV(request: HttpRequest, question_id: int) -> None:
    question = get_object_or_404(Question, pk=question_id)
    recentCSVText = question.recentCSVText
    if recentCSVText is None:
        return

    userIDsFromCSV = recentCSVText.split(",")
    userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]
    registers_users_of_current_poll, UnRegistered_users_of_current_poll = getRegAndUnRegUsers(userIDsFromCSV)

    # Add registered users to the poll
    for voter in registers_users_of_current_poll:
        voterObj = User.objects.get(username=voter)
        question.question_voters.add(voterObj.id)

    # Handle unregistered users
    for email in UnRegistered_users_of_current_poll:
        try:
            voter_obj = UnregisteredUser.objects.get(email=email)
            voter_obj.polls_invited.add(question)
        except UnregisteredUser.DoesNotExist:
            voter_obj = UnregisteredUser.objects.create(email=email)
            voter_obj.save()
            question.save()
            voter_obj.polls_invited.add(question)


def send_email_invites(request: HttpRequest, question_id: int):
    question = get_object_or_404(Question, pk=question_id)

    recepients = request.POST.get('recepients')
    mailSubject = request.POST.get('mailSubject') or None
    mailBody = request.POST.get('mailBody') or None
    csvEmails = request.POST.get('textAreaForCustomMails', '')
    customEmails = [email.strip() for email in csvEmails.split(',') if email.strip()]

    recentCSVText = question.recentCSVText
    userIDsFromCSV = [userID.strip() for userID in recentCSVText.split(",")] if recentCSVText else []

    if not userIDsFromCSV and not customEmails:
        messages.error(request, "No recipients found to send email.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    reg_users, unreg_users = getRegAndUnRegUsers(userIDsFromCSV)

    users_to_email = []
    match recepients:
        case "regVotersOnly":
            users_to_email = reg_users
        case "unregVotersOnly":
            users_to_email = unreg_users
        case "customEmails":
            users_to_email = customEmails
        case "allVoters":
            users_to_email = userIDsFromCSV

    email_class = EmailThread(
        request, question_id, 'invite-csv',
        users_to_email, mail_sub=mailSubject, mail_body=mailBody
    )
    email_class.start()

    messages.success(request, "The Email has been sent to the recepients!")
    emailSettings(request, question_id)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

SPECIALS = "!@#$%^&*()_+[]{}|;:,.<>?"   
def _generate_strong_code(length=10):
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice(SPECIALS)
    pool = string.ascii_letters + string.digits + SPECIALS
    rest = ''.join(secrets.choice(pool) for _ in range(length - 4))
    raw = list(upper + lower + digit + special + rest)
    secrets.SystemRandom().shuffle(raw)
    return ''.join(raw)


def add_codes(request, question_id):
    if request.method != 'POST':
        return HttpResponse(status=405)

    question = get_object_or_404(Question, pk=question_id)

    try:
        count = int(request.POST.get('count', '25'))
    except ValueError:
        count = 25
    if count < 1:
        count = 1
    elif count> 100:
        count=100

    created = 0
    attempts = 0

    while created < count and attempts < count * 10:
        attempts += 1
        code = _generate_strong_code(10)
        try:
            lc = LoginCode.objects.create(question=question, code=code)
            uname = f"code_{question.id}_{secrets.token_hex(4)}"
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
                    is_code_user=True
                )
            lc.user = u
            lc.save(update_fields=['user'])
            question.question_voters.add(u)

            created += 1
        except IntegrityError:
            continue

    messages.success(request, f"Created {created} login codes.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER') or reverse('polls:regular_polls'))


def export_codes_csv(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    codes = question.login_codes.order_by('created_at').values_list('code', flat=True)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['code'])
    for c in codes:
        w.writerow([c])
    buf.seek(0)

    resp = HttpResponse(buf.getvalue(), content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="opra_q{question_id}_codes.csv"'
    return resp


def removeVoter(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    if question.status != 1:
        messages.error(request, "Cannot remove voters after the poll is started/paused.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    newVoters = request.POST.getlist('voters')
    if not newVoters:
        messages.warning(request, "No users were selected for removal.")
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    email = request.POST.get('email') is not None
    # remove voters
    users_to_remove = User.objects.filter(username__in=newVoters)
    emails_to_send = [user.email for user in users_to_remove]

    question.question_voters.remove(*users_to_remove)

    existing_emails = question.recentCSVText.split(",") if question.recentCSVText else []
    updated_list = [email.strip() for email in existing_emails if email.strip().lower() not in [u.lower() for u in newVoters]]
    question.recentCSVText = ",".join(updated_list)


    mailSub = request.POST.get('mailNotificationSubject')
    mailBody = request.POST.get('mailNotificationBody')

    question.emailDelete = email
    if email:
        # print("Email sending logic to remove user")
        email_class = EmailThread(request, question_id, 'remove',emails_to_send)
        email_class.start()
        messages.success(request,"The Email has been sent to the removed users!")
    
    question.save()
    emailSettings(request, question_id)
    messages.success(request, "Selected users have been removed from "+ question.question_text)
    request.session['setting'] = 1
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


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
