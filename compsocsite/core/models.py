from __future__ import unicode_literals

import datetime

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class BaseQuestion(models.Model):
    question_text = models.CharField(max_length=200)
    question_desc = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='static/img/items/', blank=True, null=True)
    imageURL = models.CharField(max_length=500, blank=True, null=True)
    pub_date = models.DateTimeField('date published')
    question_owner = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
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
    alloc_res_tables = models.IntegerField(default=6)
    alloc_algorithms = models.IntegerField(default=0)
    first_tier = models.IntegerField(default=0)
    utility_model = models.IntegerField(default=0)
    results_visible_after = models.DateTimeField(null=True, blank=True)
    m_poll = models.BooleanField(default=False)
    next = models.IntegerField(default=-1)
    first = models.IntegerField(default=-1)
    open = models.IntegerField(default=0)
    twocol_enabled = models.BooleanField(default=True)
    onecol_enabled = models.BooleanField(default=True)
    slider_enabled = models.BooleanField(default=True)
    star_enabled = models.BooleanField(default=True)
    yesno_enabled = models.BooleanField(default=True)
    budgetUI_enabled = models.BooleanField(default=False)
    ListUI_enabled = models.BooleanField(default=False)
    infiniteBudgetUI_enabled = models.BooleanField(default=False)
    allowties = models.BooleanField(default=True)
    initial_ui = models.IntegerField(default=1)
    ui_number = models.IntegerField(default=6)
    allow_self_sign_up = models.IntegerField(default=0)

    class Meta:
        abstract = True

    def __str__(self):
        return self.question_text

    def was_published_recently(self):
        now = timezone.now()
        return now - datetime.timedelta(days=1) <= self.pub_date <= now

    def get_voters(self):
        return ",".join([str(voter) for voter in self.question_voters.all()])


class VotingQuestion(BaseQuestion):
    # question_type is a real IntegerField here (not on BaseQuestion) because
    # AllocationQuestion overrides it as an @property returning 2.
    question_type = models.IntegerField(default=1)
    winner = models.CharField(max_length=200, default="")
    mixtures_pl1 = models.TextField(default="")
    mixtures_pl2 = models.TextField(default="")
    mixtures_pl3 = models.TextField(default="")
    new_vote = models.BooleanField(default=False)
    yesno2_enabled = models.BooleanField(default=False)
    single_enabled = models.BooleanField(default=False)
    vote_rule = models.IntegerField(default=4095)
    correct_answer = models.TextField(default="")

    class Meta:
        abstract = True


class BaseItem(models.Model):
    item_text = models.CharField(max_length=200)
    item_description = models.CharField(max_length=1000, blank=True, null=True)
    image = models.ImageField(upload_to='static/img/items/', blank=True, null=True)
    imageURL = models.CharField(max_length=500, blank=True, null=True)
    imageReference = models.CharField(max_length=500, blank=True, null=True)
    timestamp = models.DateTimeField('item timestamp')
    recently_added = models.BooleanField(default=False)
    utility = models.FloatField(default=0.0)
    self_sign_up_user_id = models.TextField(default="")

    class Meta:
        abstract = True
        ordering = ['timestamp']

    def __str__(self):
        return self.item_text


class BaseResponse(models.Model):
    resp_str = models.CharField(max_length=1000, null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    timestamp = models.DateTimeField('response timestamp')
    anonymous_voter = models.CharField(max_length=50, blank=True, null=True)
    anonymous_id = models.IntegerField(default=0)
    comment = models.CharField(max_length=1000, blank=True, null=True)
    active = models.IntegerField(default=1)
    behavior_data = models.TextField(default="")

    class Meta:
        abstract = True
        ordering = ['timestamp']

    def __str__(self):
        identifier = self.user.username if self.user else self.anonymous_voter
        return (
            "Response of user " + identifier
            + "\nfor question " + self.question.question_text
            + "\nat timestamp " + self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        )


class BaseLoginCode(models.Model):
    code = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.code


class BaseDictionary(models.Model):
    # Per-response ranked-preference store. Concrete subclasses must declare
    # `response = ForeignKey(<ConcreteResponse>, ...)` and pair with a
    # BaseKeyValuePair subclass whose `container` FK uses `related_name='pairs'`.
    name = models.CharField(max_length=255)

    class Meta:
        abstract = True

    @classmethod
    def getDict(cls, name):
        return cls.objects.select_related().get(name=name)

    def __getitem__(self, key):
        return self.pairs.get(key=key).value

    def __setitem__(self, key, value):
        try:
            kvp = self.pairs.get(key=key)
        except self.pairs.model.DoesNotExist:
            self.pairs.create(key=key, value=value)
        else:
            kvp.value = value
            kvp.save()

    def __delitem__(self, key):
        try:
            kvp = self.pairs.get(key=key)
        except self.pairs.model.DoesNotExist:
            raise KeyError
        else:
            kvp.delete()

    def __len__(self):
        return self.pairs.count()

    def __iter__(self):
        return iter(kvp.key for kvp in self.pairs.all())

    iterkeys = __iter__

    def itervalues(self):
        return iter(kvp.value for kvp in self.pairs.all())

    def iteritems(self):
        return iter((kvp.key, kvp.value) for kvp in self.pairs.all())

    def keys(self):
        return [kvp.key for kvp in self.pairs.all()]

    def values(self):
        return [kvp.value for kvp in self.pairs.all()]

    def items(self):
        return [(kvp.key, kvp.value) for kvp in self.pairs.all()]

    def sorted_values(self):
        return list(sorted(self.items(), key=lambda kv: (kv[1], str(kv[0]))))

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def has_key(self, key):
        return self.contains(key)

    def contains(self, key):
        try:
            self.pairs.get(key=key)
            return True
        except self.pairs.model.DoesNotExist:
            return False

    def clear(self):
        self.pairs.all().delete()

    def asPyDict(self):
        return {kvp.key: kvp.value for kvp in self.pairs.all()}


class BaseKeyValuePair(models.Model):
    value = models.IntegerField(default=0, db_index=True)

    class Meta:
        abstract = True
