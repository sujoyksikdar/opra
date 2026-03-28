import hashlib
import json

import numpy as np
from django.db import models
from django.contrib.auth.models import User


class AllocationVoter(models.Model):
    question = models.ForeignKey('polls.Question', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    response = models.ForeignKey('polls.Response', on_delete=models.CASCADE, null=True)

    def __str__(self):
        return "User " + self.user.username + " assigned to " + self.question.question_text

    class Meta:
        db_table = 'polls_allocationvoter'


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

    class Meta:
        db_table = 'polls_allocationcache'
