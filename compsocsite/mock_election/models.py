from __future__ import unicode_literals

import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from core.models import (
    VotingQuestion, BaseItem, BaseResponse, BaseLoginCode,
    BaseDictionary, BaseKeyValuePair,
)
import logging
logger = logging.getLogger(__name__)


class MockElectionClasses(models.Model):
    title = models.CharField(max_length=100, default="")
    startDate = models.DateField('start date')
    weekly = models.IntegerField(default=0)
    teacher = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    attendance = models.IntegerField(default=-1)
    teachingAssistants = models.ManyToManyField(User, related_name='mock_election_tas')
    students = models.ManyToManyField(User, related_name='mock_election_students')


class MockElectionQuestion(VotingQuestion):
    question_voters = models.ManyToManyField(User, related_name='mock_election_participated')
    follow_up = models.OneToOneField('MockElectionQuestion', on_delete=models.CASCADE, null=True, blank=True)
    related_class = models.ForeignKey(MockElectionClasses, null=True, on_delete=models.CASCADE)


class MockElectionLoginCode(BaseLoginCode):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE, related_name='login_codes')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='mock_election_login_codes')


class MockElectionUnregisteredUser(models.Model):
    email = models.EmailField(unique=True)
    polls_invited = models.ManyToManyField(MockElectionQuestion, related_name='invited_unregistered_users')


class MockElectionEmail(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)
    type = models.IntegerField()
    subject = models.CharField(max_length=100)
    message = models.CharField(max_length=500)

    def __str__(self):
        return str(self.question)


class MockElectionItem(BaseItem):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)


class MockElectionResponse(BaseResponse):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE, null=True)
    allocation = models.ForeignKey(MockElectionItem, default=None, null=True, blank=True, on_delete=models.CASCADE)


class MockElectionOldWinner(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)
    response = models.ForeignKey(MockElectionResponse, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.response.timestamp.time())


class MockElectionDictionary(BaseDictionary):
    response = models.ForeignKey(MockElectionResponse, default=None, on_delete=models.CASCADE)


class MockElectionKeyValuePair(BaseKeyValuePair):
    container = models.ForeignKey(MockElectionDictionary, db_index=True, on_delete=models.CASCADE, related_name='pairs')
    key = models.ForeignKey(MockElectionItem, default=None, on_delete=models.CASCADE, db_index=True)


class MockElectionFinalResult(models.Model):
    question = models.OneToOneField(MockElectionQuestion, on_delete=models.CASCADE)
    result_string = models.TextField(default="")
    mov_string = models.TextField(default="")
    node_string = models.TextField(default="")
    edge_string = models.TextField(default="")
    shade_string = models.TextField(default="")
    cand_num = models.IntegerField(default=1)
    timestamp = models.DateTimeField('result timestamp')


class MockElectionVoteResult(models.Model):
    question = models.ForeignKey(MockElectionQuestion, null=True, on_delete=models.CASCADE)
    result_string = models.TextField(default="")
    mov_string = models.TextField(default="")
    cand_num = models.IntegerField(default=1)
    timestamp = models.DateTimeField('result timestamp')

    class Meta:
        ordering = ['-timestamp']


class MockElectionMoV(models.Model):
    result = models.ForeignKey(MockElectionVoteResult, on_delete=models.CASCADE)
    value = models.IntegerField(default=0)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']


class MockElectionScoreMap(models.Model):
    result = models.ForeignKey(MockElectionVoteResult, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)

    def asPyDict(self):
        fieldDict = dict()
        for kvp in self.mockelectioncandscorepair_set.all():
            fieldDict[kvp.cand] = kvp.score
        return fieldDict

    class Meta:
        ordering = ['order']


class MockElectionCandScorePair(models.Model):
    container = models.ForeignKey(MockElectionScoreMap, on_delete=models.CASCADE)
    cand = models.IntegerField(default=0)
    score = models.FloatField(default=0.0)


class MockElectionUserVoteRecord(models.Model):
    timestamp = models.DateTimeField('record timestamp')
    user = models.CharField(max_length=100, default="(Anonymous)")
    question = models.ForeignKey(MockElectionQuestion, default=None, on_delete=models.CASCADE)
    record = models.CharField(max_length=10000, default="")
    col = models.TextField(default="")
    one_col = models.TextField(default="")
    slider = models.TextField(default="")
    star = models.TextField(default="")
    swit = models.TextField(default="")
    initial_order = models.TextField(default="")
    initial_type = models.IntegerField(default=0)
    final_order = models.TextField(default="")
    device = models.CharField(default="", max_length=20)
    comment_time = models.CharField(max_length=100, default="")
    submit_time = models.CharField(max_length=100, default="")
    ui = models.CharField(max_length=100, default="")

    class Meta:
        ordering = ['timestamp']


class MockElectionSignUpRequest(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item_name = models.TextField()
    status = models.IntegerField(default=1)
    timestamp = models.DateTimeField('request timestamp')
