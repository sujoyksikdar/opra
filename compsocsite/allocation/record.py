import json

from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views import generic

from .models import AllocationQuestion


class AllocationRecordView(generic.DetailView):
    model = AllocationQuestion
    template_name = 'allocation/record.html'
    context_object_name = 'question'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        responses = self.object.allocationresponse_set.all()
        interpreted_records = []
        for r in responses:
            try:
                record_data = json.loads(r.behavior_data)
                if isinstance(record_data, dict):
                    if r.user:
                        record_data['user'] = r.user.username
                    record_data['timestamp'] = str(r.timestamp)
                interpreted_records.append(json.dumps(record_data, indent=4))
            except (ValueError, TypeError):
                interpreted_records.append(r.behavior_data)
        ctx['user_records'] = interpreted_records
        return ctx


def downloadAllocationLatestVotes(request, question_id):
    question = get_object_or_404(AllocationQuestion, pk=question_id)
    response_set = question.allocationresponse_set.filter(active=1).order_by('-timestamp')
    records = []
    for r in response_set:
        record = {}
        if r.user is None:
            record['username'] = None
            record['email'] = None
        else:
            record['username'] = r.user.username
            record['email'] = r.user.email
        record['question_id'] = r.question.id
        record['timestamp'] = str(r.timestamp)
        record['behavior_data'] = r.behavior_data
        records.append(record)
    return JsonResponse(records, safe=False)
