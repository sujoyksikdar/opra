import threading

from django.contrib import messages
from django.contrib.auth.models import User
from django.core import mail
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from .models import AllocationQuestion, AllocationEmail


def switchAllocationModel(type, question, request):
    if type == 'invite' or type == 'invite-group':
        email = AllocationEmail.objects.filter(question=question, type=1)
    if type == 'remove' or type == 'remove-group':
        email = AllocationEmail.objects.filter(question=question, type=2)
    if type == 'start':
        email = AllocationEmail.objects.filter(question=question, type=3)
    if type == 'stop':
        email = AllocationEmail.objects.filter(question=question, type=4)
    if type == 'now':
        return [request.POST.get('subject'), request.POST.get('message')]
    if type == 'invite-csv':
        email = AllocationEmail.objects.filter(question=question, type=5)
    if len(email) != 1:
        setupAllocationEmail(question)
    return [email[0].subject, email[0].message]


def setupAllocationEmail(question):
    title = question.question_text
    creator = question.question_owner.username

    emailInvite = AllocationEmail.objects.filter(question=question, type=1)
    if not emailInvite.exists():
        AllocationEmail(question=question, type=1,
            subject="You have been invited to vote on " + title,
            message="<p>Hello [user_name],</p>"
                    f"<p>{creator} has invited you to participate in an allocation. Please login at [url] to check it out.</p>"
                    "<p>Sincerely,<br>OPRA Staff</p>").save()
    else:
        emailInvite.update(subject="You have been invited to vote on " + title,
            message="<p>Hello [user_name],</p>"
                    f"<p>{creator} has invited you to participate in an allocation. Please login at [url] to check it out.</p>"
                    "<p>Sincerely,<br>OPRA Staff</p>")

    emailRemove = AllocationEmail.objects.filter(question=question, type=2)
    if not emailRemove.exists():
        AllocationEmail(question=question, type=2,
            subject="You have been removed from " + title,
            message='Hello [user_name],\n\n' + creator
                    + ' has removed you from an allocation.\n\nSincerely,\nOPRA Staff').save()
    else:
        emailRemove.update(subject="You have been removed from " + title,
            message='Hello [user_name],\n\n' + creator
                    + ' has removed you from an allocation.\n\nSincerely,\nOPRA Staff')

    emailStart = AllocationEmail.objects.filter(question=question, type=3)
    if not emailStart.exists():
        AllocationEmail(question=question, type=3,
            subject=title + ' has started!',
            message='Hello [user_name],\n\n' + creator
                    + ' has started an allocation. It is now available at [url] \n\nSincerely,\nOPRA Staff').save()
    else:
        emailStart.update(subject=title + ' has started!',
            message='Hello [user_name],\n\n' + creator
                    + ' has started an allocation. It is now available at [url] \n\nSincerely,\nOPRA Staff')

    emailStop = AllocationEmail.objects.filter(question=question, type=4)
    if not emailStop.exists():
        AllocationEmail(question=question, type=4,
            subject=title + ' has stopped',
            message='Hello [user_name],\n\n' + creator
                    + ' has ended an allocation. Please visit [url] to view the results.\n\nSincerely,\nOPRA Staff').save()
    else:
        emailStop.update(subject=title + ' has stopped',
            message='Hello [user_name],\n\n' + creator
                    + ' has ended an allocation. Please visit [url] to view the results.\n\nSincerely,\nOPRA Staff')

    emailInviteCSV = AllocationEmail.objects.filter(question=question, type=5)
    if not emailInviteCSV.exists():
        AllocationEmail(question=question, type=5,
            subject="You have been invited to vote on " + title,
            message="<p>Hello [user_name],</p>"
                    f"<p>{creator} has invited you to participate in an allocation. Please login at [url] to check it out.</p>"
                    "<p>Sincerely,<br>OPRA Staff</p>").save()
    else:
        emailInviteCSV.update(subject="You have been invited to vote on " + title,
            message="<p>Hello [user_name],</p>"
                    f"<p>{creator} has invited you to participate in an allocation. Please login at [url] to check it out.</p>"
                    "<p>Sincerely,<br>OPRA Staff</p>")


def translateEmail(text, uname, url):
    text = text.replace("[user_name]", uname)
    text = text.replace("[url]", url)
    return text


def translateHTML(text, uname, url, options):
    text = translateEmail(text, uname, url)
    text = "<p>" + text + "</p>"
    text = text.replace("\n\n", "</p><br /><p>")
    text = text.replace("\n", "</p><p>")
    text += options
    return text


class AllocationEmailThread(threading.Thread):
    def __init__(self, request, question_id, type, voters=None, mail_sub=None, mail_body=None):
        threading.Thread.__init__(self)
        self.question = get_object_or_404(AllocationQuestion, pk=question_id)
        self.type = type
        self.request = request
        self.email = switchAllocationModel(type, self.question, request)
        self.title = self.question.question_text
        self.creator_obj = User.objects.get(id=self.question.question_owner_id)
        self.creator = self.creator_obj.username
        if self.creator_obj.first_name != "":
            self.creator = self.creator_obj.first_name + " " + self.creator_obj.last_name

        if type == 'remove':
            self.voters = request.POST.getlist('voters')
        elif type in ('invite', 'invite-group', 'invite-csv', 'remove-group'):
            self.voters = voters
        else:
            self.voters = self.question.question_voters.all()

        if mail_sub:
            self.email[0] = mail_sub
        if mail_body:
            self.email[1] = mail_body

    def run(self):
        options = ''
        if self.type == 'invite-csv':
            if self.voters[0] == 'None':
                return
            for voter in self.voters:
                name, uname = voter, voter
                url = self.request.build_absolute_uri(reverse('appauth:login') + '?name=' + uname)
                mail.send_mail(translateEmail(self.email[0], name, url),
                    translateEmail(self.email[1], name, url),
                    'opra@cs.binghamton.edu', [voter],
                    html_message=translateHTML(self.email[1], name, url, options))
            return

        for voter in self.voters:
            if self.type in ('invite', 'remove', 'invite-group', 'remove-group'):
                voter = get_object_or_404(User, username=voter)
            name = voter.username
            uname = voter.username
            if voter.first_name != "":
                name = voter.first_name + " " + voter.last_name
            url = self.request.build_absolute_uri(reverse('appauth:login') + '?name=' + uname)
            mail.send_mail(translateEmail(self.email[0], name, url),
                translateEmail(self.email[1], name, url),
                'opra@cs.binghamton.edu', [voter.email],
                html_message=translateHTML(self.email[1], name, url, options))


def allocationEmailSettings(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)

    if request.POST.get('mailNotificationSubject1') is not None:
        emailInvite = AllocationEmail.objects.filter(question=question, type=1)[0]
        emailInvite.subject = request.POST.get('mailNotificationSubject1')
        emailInvite.message = request.POST.get('mailNotificationBody1')
        emailInvite.save()
        question.emailInvite = request.POST.get('email') == 'email'

    if request.POST.get('mailNotificationSubject') is not None:
        emailDelete = AllocationEmail.objects.filter(question=question, type=2)[0]
        emailDelete.subject = request.POST.get('mailNotificationSubject')
        emailDelete.message = request.POST.get('mailNotificationBody')
        emailDelete.save()
        question.emailDelete = request.POST.get('email') == 'email'

    if request.POST.get('startSubject') is not None:
        emailStart = AllocationEmail.objects.filter(question=question, type=3)[0]
        emailStart.subject = request.POST.get('startSubject')
        emailStart.message = request.POST.get('startMessage')
        emailStart.save()
        question.emailStart = request.POST.get('emailStart') == 'email'

    if request.POST.get('stopSubject') is not None:
        emailStop = AllocationEmail.objects.filter(question=question, type=4)[0]
        emailStop.subject = request.POST.get('stopSubject')
        emailStop.message = request.POST.get('stopMessage')
        emailStop.save()
        question.emailStop = request.POST.get('emailStop') == 'email'

    if request.POST.get('mailSubject') is not None:
        emailInviteCSV = AllocationEmail.objects.filter(question=question, type=5)[0]
        emailInviteCSV.subject = request.POST.get('mailSubject')
        emailInviteCSV.message = request.POST.get('mailBody')
        emailInviteCSV.save()
        question.emailInviteCSV = request.POST.get('email') == 'email'

    question.save()
    request.session['setting'] = 5
    messages.success(request, "Your changes have been saved.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def allocationEmailNow(request, question_id):
    email_class = AllocationEmailThread(request, question_id, "now")
    email_class.start()
    messages.success(request, "The Email has been sent to all the participants of the allocation.")
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
