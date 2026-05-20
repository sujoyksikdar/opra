import hashlib
import json

import numpy as np
from django.db import models
from django.contrib.auth.models import User

from core.models import (
    BaseQuestion, BaseItem, BaseResponse, BaseLoginCode,
    BaseDictionary, BaseKeyValuePair,
)


class AllocationQuestion(BaseQuestion):
    question_voters = models.ManyToManyField(User, related_name='allocation_participated')

    # Polls templates check question.question_type to branch between regular polls
    # (type 1) and allocation polls (type 2). AllocationQuestion is always type 2.
    @property
    def question_type(self):
        return 2


class AllocationItem(BaseItem):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)


class AllocationResponse(BaseResponse):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE, null=True)
    allocation = models.ForeignKey(
        AllocationItem, default=None, null=True, blank=True, on_delete=models.CASCADE
    )


class AllocationDictionary(BaseDictionary):
    response = models.ForeignKey(AllocationResponse, default=None, on_delete=models.CASCADE)


class AllocationKeyValuePair(BaseKeyValuePair):
    container = models.ForeignKey(AllocationDictionary, db_index=True, on_delete=models.CASCADE, related_name='pairs')
    key = models.ForeignKey(AllocationItem, default=None, on_delete=models.CASCADE, db_index=True)


class AllocationVoter(models.Model):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    response = models.ForeignKey(AllocationResponse, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return "User " + self.user.username + " assigned to " + self.question.question_text


class AllocationLoginCode(BaseLoginCode):
    question = models.ForeignKey(AllocationQuestion, on_delete=models.CASCADE, related_name='login_codes')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='allocation_login_codes')


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
        serializable_data = AllocationCache._make_serializable(context_data)
        data_str = json.dumps(serializable_data, sort_keys=True)
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
