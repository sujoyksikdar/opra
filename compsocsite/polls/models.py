from __future__ import unicode_literals

import datetime

from django.db import models
from django.utils import timezone
from six import python_2_unicode_compatible
from django.contrib.auth.models import User
import os
from django.conf import settings
from core.models import (
    VotingQuestion, BaseItem, BaseResponse, BaseLoginCode,
    BaseDictionary, BaseKeyValuePair,
)
import logging
logger = logging.getLogger(__name__)

# Models

class Classes(models.Model):
    title = models.CharField(max_length=100, default="")
    startDate = models.DateField('start date')
    weekly = models.IntegerField(default=0)
    teacher = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    attendance = models.IntegerField(default=-1)
    teachingAssistants = models.ManyToManyField(User, related_name='tas')
    students = models.ManyToManyField(User, related_name='students')

# question that will receive responses
class Question(VotingQuestion):
    question_voters = models.ManyToManyField(User, related_name='poll_participated')
    follow_up = models.OneToOneField('Question', on_delete=models.CASCADE, null=True, blank=True)
    related_class = models.ForeignKey(Classes, null=True, on_delete=models.CASCADE)


class LoginCode(BaseLoginCode):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='login_codes')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='login_codes')

class UnregisteredUser(models.Model):
    email = models.EmailField(unique=True)
    polls_invited = models.ManyToManyField(Question, related_name='invited_unregistered_users')

# email to be sent
@python_2_unicode_compatible
class Folder(models.Model):
    questions = models.ManyToManyField(Question)
    user      = models.ForeignKey(User, on_delete=models.CASCADE)
    title     = models.CharField(max_length=500)
    edit_date = models.DateTimeField()
    def __str__(self):
        return self.title

# email to be sent
@python_2_unicode_compatible
class Email(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    type     = models.IntegerField()
    subject  = models.CharField(max_length=100)
    message  = models.CharField(max_length=500)
    def __str__(self):
        return str(self.question)

#Helper function for image
def get_image_path(instance, filename):
    return 'static/img/items/'

# item to rank in a question
class Item(BaseItem):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)

# all information pertaining to a response that a student made to a question
class Response(BaseResponse):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, null=True)
    allocation = models.ForeignKey(Item, default=None, null=True, blank=True, on_delete=models.CASCADE)  # assigned by algorithm function

# all information pertaining to a response that a student made to a question
@python_2_unicode_compatible
class EmailResponse(models.Model):
    identity = models.CharField(max_length=20, null=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True)
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    def __str__(self):
        return ""     

# a winner at a certain point in time
@python_2_unicode_compatible
class OldWinner(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    response = models.ForeignKey(Response, on_delete=models.CASCADE)
    def __str__(self):
        return (str(self.response.timestamp.time()))

# collection of a student's preferences within a single response (to a single question)
class Dictionary(BaseDictionary):
    response = models.ForeignKey(Response, default=None, on_delete=models.CASCADE)

# key-value pair of an item and the ranking a student gave it in their response
class KeyValuePair(BaseKeyValuePair):
    container = models.ForeignKey(Dictionary, db_index=True, on_delete=models.CASCADE, related_name='pairs')
    key = models.ForeignKey(Item, default=None, on_delete=models.CASCADE, db_index=True)
    
class FinalResult(models.Model):
    question = models.OneToOneField(Question, on_delete=models.CASCADE)
    result_string = models.TextField(default="")
    mov_string = models.TextField(default="")
    node_string = models.TextField(default="")
    edge_string = models.TextField(default="")
    shade_string = models.TextField(default="")
    cand_num = models.IntegerField(default = 1)
    timestamp = models.DateTimeField('result timestamp')

class VoteResult(models.Model):
    question = models.ForeignKey(Question, null=True, on_delete=models.CASCADE)
    result_string = models.TextField(default="")
    mov_string = models.TextField(default="")
    cand_num = models.IntegerField(default = 1)
    timestamp = models.DateTimeField('result timestamp')
    class Meta:
        ordering = ['-timestamp']
        
class MoV(models.Model):
    result = models.ForeignKey(VoteResult, on_delete=models.CASCADE)
    value = models.IntegerField(default=0)
    order = models.IntegerField(default=0)
    class Meta:
        ordering = ['order']
    
class ScoreMap(models.Model):
    result = models.ForeignKey(VoteResult, on_delete=models.CASCADE)
    order = models.IntegerField(default=0)
    def asPyDict(self):
        """Get a python dictionary that represents this Dictionary object.
        This object is read-only.
        """
        fieldDict = dict()
        for kvp in self.candscorepair_set.all():
            fieldDict[kvp.cand] = kvp.score
        return fieldDict
    class Meta:
        ordering = ['order']

class CandScorePair(models.Model):
    container = models.ForeignKey(ScoreMap, on_delete=models.CASCADE)
    cand = models.IntegerField(default = 0)
    score = models.FloatField(default = 0.0)
    
class UserVoteRecord(models.Model):
    timestamp = models.DateTimeField('record timestamp')
    user =models.CharField(max_length=100,default="(Anonymous)")
    question = models.ForeignKey(Question,default=None, on_delete=models.CASCADE)
    record = models.CharField(max_length=10000,default="")
    col = models.TextField(default="")
    one_col = models.TextField(default="")
    slider = models.TextField(default="")
    star = models.TextField(default="")
    swit = models.TextField(default="")
    initial_order = models.TextField(default="")
    initial_type = models.IntegerField(default=0)
    final_order = models.TextField(default="")
    device = models.CharField(default="",max_length=20)
    comment_time = models.CharField(max_length=100,default="")
    submit_time = models.CharField(max_length=100,default="")
    ui = models.CharField(max_length=100,default="")
    class Meta:
        ordering = ['timestamp']

class Message(models.Model):
    text = models.CharField(max_length=10000, default="")
    timestamp = models.DateTimeField('message timestamp')
    email = models.CharField(max_length=100, default="")
    name = models.CharField(max_length=200, default="")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)

class Experiment(models.Model):
    title = models.CharField(max_length=10000)
    timestamp = models.DateTimeField('date/time created')
    polls = models.TextField(default="[]")
    status = models.IntegerField(default=0)
    participants = models.ManyToManyField(User)

class RandomUtilityPool(models.Model):
    data = models.TextField(default="[]")

class SignUpRequest(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item_name = models.TextField()
    status = models.IntegerField(default=1)
    timestamp = models.DateTimeField('request timestamp')

