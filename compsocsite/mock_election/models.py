from __future__ import unicode_literals

import datetime

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
import logging
logger = logging.getLogger(__name__)


class MockElectionQuestion(models.Model):
    question_text = models.CharField(max_length=200)
    question_desc = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='static/img/items/', blank=True, null=True)
    imageURL = models.CharField(max_length=500, blank=True, null=True)
    pub_date = models.DateTimeField('date published')
    follow_up = models.OneToOneField('MockElectionQuestion', on_delete=models.CASCADE, null=True, blank=True)
    question_owner = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    question_voters = models.ManyToManyField(User, related_name='mock_election_participated')
    recentCSVText = models.TextField(null=True, blank=True, default=None)
    status = models.IntegerField(default=1)
    display_pref = models.IntegerField(default=1)
    display_user_info = models.IntegerField(default=1)
    creator_pref = models.IntegerField(default=1)
    emailInviteCSV = models.BooleanField(default=False)
    emailInvite = models.BooleanField(default=False)
    emailDelete = models.BooleanField(default=False)
    emailStart = models.BooleanField(default=False)
    emailStop = models.BooleanField(default=False)
    poll_algorithm = models.IntegerField(default=1)
    question_type = models.IntegerField(default=1)
    winner = models.CharField(max_length=200, default="")
    mixtures_pl1 = models.TextField(default="")
    mixtures_pl2 = models.TextField(default="")
    mixtures_pl3 = models.TextField(default="")
    m_poll = models.BooleanField(default=False)
    next = models.IntegerField(default=-1)
    first = models.IntegerField(default=-1)
    open = models.IntegerField(default=0)
    new_vote = models.BooleanField(default=False)
    twocol_enabled = models.BooleanField(default=True)
    onecol_enabled = models.BooleanField(default=True)
    slider_enabled = models.BooleanField(default=True)
    star_enabled = models.BooleanField(default=True)
    yesno_enabled = models.BooleanField(default=True)
    yesno2_enabled = models.BooleanField(default=False)
    single_enabled = models.BooleanField(default=False)
    budgetUI_enabled = models.BooleanField(default=False)
    ListUI_enabled = models.BooleanField(default=False)
    infiniteBudgetUI_enabled = models.BooleanField(default=False)
    allowties = models.BooleanField(default=True)
    initial_ui = models.IntegerField(default=1)
    ui_number = models.IntegerField(default=6)
    vote_rule = models.IntegerField(default=4095)
    alloc_res_tables = models.IntegerField(default=6)
    alloc_algorithms = models.IntegerField(default=0)
    first_tier = models.IntegerField(default=0)
    utility_model = models.IntegerField(default=0)
    results_visible_after = models.DateTimeField(null=True, blank=True)
    correct_answer = models.TextField(default="")
    allow_self_sign_up = models.IntegerField(default=0)

    def __str__(self):
        return self.question_text

    def was_published_recently(self):
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now

    def get_voters(self):
        return ",".join([str(voter) for voter in self.question_voters.all()])


class MockElectionLoginCode(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE, related_name='login_codes')
    code = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='mock_election_login_codes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


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


class MockElectionItem(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)
    item_text = models.CharField(max_length=200)
    item_description = models.CharField(max_length=1000, blank=True, null=True)
    image = models.ImageField(upload_to='static/img/items/', blank=True, null=True)
    imageURL = models.CharField(max_length=500, blank=True, null=True)
    imageReference = models.CharField(max_length=500, blank=True, null=True)
    timestamp = models.DateTimeField('item timestamp')
    recently_added = models.BooleanField(default=False)
    utility = models.FloatField(default=0.0)
    self_sign_up_user_id = models.TextField(default="")

    def __str__(self):
        return self.item_text

    class Meta:
        ordering = ['timestamp']


class MockElectionResponse(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE, null=True)
    resp_str = models.CharField(max_length=1000, null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    timestamp = models.DateTimeField('response timestamp')
    allocation = models.ForeignKey(MockElectionItem, default=None, null=True, blank=True, on_delete=models.CASCADE)
    anonymous_voter = models.CharField(max_length=50, blank=True, null=True)
    anonymous_id = models.IntegerField(default=0)
    comment = models.CharField(max_length=1000, blank=True, null=True)
    active = models.IntegerField(default=1)
    behavior_data = models.TextField(default="")

    def __str__(self):
        if self.user:
            return "Response of user " + self.user.username + "\nfor question " + self.question.question_text + "\nat timestamp " + self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return "Response of user " + self.anonymous_voter + "\nfor question " + self.question.question_text + "\nat timestamp " + self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    class Meta:
        ordering = ['timestamp']


class MockElectionOldWinner(models.Model):
    question = models.ForeignKey(MockElectionQuestion, on_delete=models.CASCADE)
    response = models.ForeignKey(MockElectionResponse, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.response.timestamp.time())


class MockElectionDictionary(models.Model):
    name = models.CharField(max_length=255)
    response = models.ForeignKey(MockElectionResponse, default=None, on_delete=models.CASCADE)

    @staticmethod
    def getDict(name):
        df = MockElectionDictionary.objects.select_related().get(name=name)
        return df

    def __getitem__(self, key):
        return self.mockelectionkeyvaluepair_set.get(key=key).value

    def __setitem__(self, key, value):
        try:
            kvp = self.mockelectionkeyvaluepair_set.get(key=key)
        except MockElectionKeyValuePair.DoesNotExist:
            MockElectionKeyValuePair.objects.create(container=self, key=key, value=value)
        else:
            kvp.value = value
            kvp.save()

    def __delitem__(self, key):
        try:
            kvp = self.mockelectionkeyvaluepair_set.get(key=key)
        except MockElectionKeyValuePair.DoesNotExist:
            raise KeyError
        else:
            kvp.delete()

    def __len__(self):
        return self.mockelectionkeyvaluepair_set.count()

    def iterkeys(self):
        return iter(kvp.key for kvp in self.mockelectionkeyvaluepair_set.all())

    def itervalues(self):
        return iter(kvp.value for kvp in self.mockelectionkeyvaluepair_set.all())

    __iter__ = iterkeys

    def iteritems(self):
        return iter((kvp.key, kvp.value) for kvp in self.mockelectionkeyvaluepair_set.all())

    def keys(self):
        return [kvp.key for kvp in self.mockelectionkeyvaluepair_set.all()]

    def values(self):
        return [kvp.value for kvp in self.mockelectionkeyvaluepair_set.all()]

    def sorted_values(self):
        return list(sorted(self.items(), key=lambda kv: (kv[1], str(kv[0]))))

    def items(self):
        return [(kvp.key, kvp.value) for kvp in self.mockelectionkeyvaluepair_set.all()]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def has_key(self, key):
        return self.contains(key)

    def contains(self, key):
        try:
            self.mockelectionkeyvaluepair_set.get(key=key)
            return True
        except MockElectionKeyValuePair.DoesNotExist:
            return False

    def clear(self):
        self.mockelectionkeyvaluepair_set.all().delete()

    def asPyDict(self):
        fieldDict = dict()
        for kvp in self.mockelectionkeyvaluepair_set.all():
            fieldDict[kvp.key] = kvp.value
        return fieldDict


class MockElectionKeyValuePair(models.Model):
    container = models.ForeignKey(MockElectionDictionary, db_index=True, on_delete=models.CASCADE)
    key = models.ForeignKey(MockElectionItem, default=None, on_delete=models.CASCADE, db_index=True)
    value = models.IntegerField(default=0, db_index=True)


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
