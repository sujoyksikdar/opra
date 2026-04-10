import hashlib
import json

import numpy as np
from django.db import models
from django.contrib.auth.models import User


class AllocationQuestion(models.Model):
    question_text = models.CharField(max_length=200)
    question_desc = models.TextField(null=True, blank=True)
    image = models.ImageField(upload_to='static/img/items/', blank=True, null=True)
    imageURL = models.CharField(max_length=500, blank=True, null=True)
    pub_date = models.DateTimeField('date published')
    question_owner = models.ForeignKey(User, null=True, on_delete=models.CASCADE)
    question_voters = models.ManyToManyField(User, related_name='allocation_participated')
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
    allow_self_sign_up = models.IntegerField(default=0)
    initial_ui = models.IntegerField(default=1)
    ui_number = models.IntegerField(default=6)
    twocol_enabled = models.BooleanField(default=True)
    onecol_enabled = models.BooleanField(default=True)
    slider_enabled = models.BooleanField(default=True)
    star_enabled = models.BooleanField(default=True)
    yesno_enabled = models.BooleanField(default=True)
    budgetUI_enabled = models.BooleanField(default=False)
    ListUI_enabled = models.BooleanField(default=False)
    infiniteBudgetUI_enabled = models.BooleanField(default=False)
    allowties = models.BooleanField(default=True)

    # Polls templates check question.question_type to branch between regular polls
    # (type 1) and allocation polls (type 2). AllocationQuestion is always type 2.
    @property
    def question_type(self):
        return 2

    def __str__(self):
        return self.question_text

    def get_voters(self):
        return ",".join([str(voter) for voter in self.question_voters.all()])


class AllocationItem(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)
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


class AllocationResponse(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE, null=True)
    resp_str = models.CharField(max_length=1000, null=True, blank=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    timestamp = models.DateTimeField('response timestamp')
    allocation = models.ForeignKey(
        AllocationItem, default=None, null=True, blank=True, on_delete=models.CASCADE
    )
    anonymous_voter = models.CharField(max_length=50, blank=True, null=True)
    anonymous_id = models.IntegerField(default=0)
    comment = models.CharField(max_length=1000, blank=True, null=True)
    active = models.IntegerField(default=1)
    behavior_data = models.TextField(default="")

    def __str__(self):
        if self.user:
            return (
                "Response of user " + self.user.username
                + "\nfor question " + self.question.question_text
                + "\nat timestamp " + self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            )
        return (
            "Response of user " + self.anonymous_voter
            + "\nfor question " + self.question.question_text
            + "\nat timestamp " + self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        )

    class Meta:
        ordering = ['timestamp']


class AllocationDictionary(models.Model):
    name = models.CharField(max_length=255)
    response = models.ForeignKey(AllocationResponse, default=None, on_delete=models.CASCADE)

    def __getitem__(self, key):
        return self.allocationkeyvaluepair_set.get(key=key).value

    def __setitem__(self, key, value):
        try:
            kvp = self.allocationkeyvaluepair_set.get(key=key)
        except AllocationKeyValuePair.DoesNotExist:
            AllocationKeyValuePair.objects.create(container=self, key=key, value=value)
        else:
            kvp.value = value
            kvp.save()

    def __delitem__(self, key):
        try:
            kvp = self.allocationkeyvaluepair_set.get(key=key)
        except AllocationKeyValuePair.DoesNotExist:
            raise KeyError
        else:
            kvp.delete()

    def __len__(self):
        return self.allocationkeyvaluepair_set.count()

    def __iter__(self):
        return iter(kvp.key for kvp in self.allocationkeyvaluepair_set.all())

    def keys(self):
        return [kvp.key for kvp in self.allocationkeyvaluepair_set.all()]

    def values(self):
        return [kvp.value for kvp in self.allocationkeyvaluepair_set.all()]

    def items(self):
        return [(kvp.key, kvp.value) for kvp in self.allocationkeyvaluepair_set.all()]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def contains(self, key):
        try:
            self.allocationkeyvaluepair_set.get(key=key)
            return True
        except AllocationKeyValuePair.DoesNotExist:
            return False

    def clear(self):
        self.allocationkeyvaluepair_set.all().delete()

    def sorted_values(self):
        return list(sorted(self.items(), key=lambda kv: (kv[1], str(kv[0]))))


class AllocationKeyValuePair(models.Model):
    container = models.ForeignKey(AllocationDictionary, db_index=True, on_delete=models.CASCADE)
    key = models.ForeignKey(AllocationItem, default=None, on_delete=models.CASCADE, db_index=True)
    value = models.IntegerField(default=0, db_index=True)


class AllocationVoter(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    response = models.ForeignKey(AllocationResponse, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return "User " + self.user.username + " assigned to " + self.question.question_text


class AllocationLoginCode(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE, related_name='login_codes')
    code = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='allocation_login_codes')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


class AllocationSignUpRequest(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item_name = models.TextField()
    status = models.IntegerField(default=1)
    timestamp = models.DateTimeField('request timestamp')


class AllocationEmail(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)
    type     = models.IntegerField()
    subject  = models.CharField(max_length=100)
    message  = models.CharField(max_length=500)

    def __str__(self):
        return str(self.question)


class AllocationCache(models.Model):
    """Cache for allocation results to avoid recomputation."""
    hash_key = models.CharField(max_length=64, unique=True)
    allocation_data = models.TextField()
    timestamp = models.DateTimeField(auto_now=True)
    hit_count = models.IntegerField(default=0)

    @staticmethod
    def generate_key(context_data):
        data_str = json.dumps(context_data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    @staticmethod
    def get_cached_result(context_data):
        try:
            hash_key = AllocationCache.generate_key(context_data)
            cache_entry = AllocationCache.objects.get(hash_key=hash_key)
            cache_entry.hit_count += 1
            cache_entry.save()
            return json.loads(cache_entry.allocation_data), True
        except AllocationCache.DoesNotExist:
            return None, False
        except Exception:
            return None, False

    @staticmethod
    def store_result(context_data, allocation_result):
        try:
            hash_key = AllocationCache.generate_key(context_data)
            serializable_result = AllocationCache._make_serializable(allocation_result)
            AllocationCache.objects.update_or_create(
                hash_key=hash_key,
                defaults={'allocation_data': json.dumps(serializable_result)}
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _make_serializable(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: AllocationCache._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [AllocationCache._make_serializable(i) for i in obj]
        return obj
