import ast
import json
import logging

import numpy as np
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django import views
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required

from prefpy.mechanism import (
    MechanismRoundRobinAllocation,
    MechanismMaximumNashWelfare,
    MechanismMarketAllocation,
    MechanismMarketEqAllocation,
    MechanismLeximinAllocation,
    MechanismMaximumNashWelfareBinary,
)
from prefpy.allocation_properties import is_po

from polls.models import Question, Item, Response, Dictionary
from groups.models import Folder
from polls.utils import getPrefOrder, block_code_users

from .models import AllocationVoter, AllocationCache
from .utils import computeEnvyUptoEF1

logger = logging.getLogger(__name__)


@method_decorator(block_code_users("/polls/allocation_tab/code"), name="dispatch")
@method_decorator(login_required, name="dispatch")
class RegularAllocationView(views.generic.ListView):
    template_name = 'allocation/allocation_tab.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        return Question.objects.all().order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super(RegularAllocationView, self).get_context_data(**kwargs)
        ctx['folders'] = Folder.objects.filter(user=self.request.user).all()
        unshown = []
        for folder in ctx['folders']:
            unshown += folder.questions.all()

        ctx['polls_created'] = list(Question.objects.filter(
            question_owner=self.request.user, m_poll=False, question_type=2
        ).order_by('-pub_date'))
        ctx['active_polls'] = list(Question.objects.filter(question_type=2).order_by('-pub_date'))

        polls = self.request.user.poll_participated.filter(m_poll=False, question_type=2)
        polls = polls.exclude(question_owner=self.request.user).order_by('-pub_date')
        ctx['polls_participated'] = list(polls)

        for poll in unshown:
            if poll in ctx['polls_created']:
                ctx['polls_created'].remove(poll)
            elif poll in ctx['polls_participated']:
                ctx['polls_participated'].remove(poll)

        self.request.session['questionType'] = 2
        return ctx


class CodeAllocationView(views.generic.ListView):
    template_name = 'allocation/allocation_tab_code.html'
    context_object_name = 'question_list'

    def get_queryset(self):
        qid = self.request.session.get('code_question_id')
        return Question.objects.filter(pk=qid, question_type=2).order_by('-pub_date')

    def get_context_data(self, **kwargs):
        ctx = super(CodeAllocationView, self).get_context_data(**kwargs)
        qid = self.request.session.get('code_question_id')

        ctx['folders'] = []
        ctx['polls_created'] = []
        ctx['active_polls'] = list(Question.objects.filter(question_type=2).order_by('-pub_date'))
        polls = Question.objects.filter(pk=qid, question_type=2)
        ctx['polls_participated'] = list(polls)

        self.request.session['questionType'] = 2
        return ctx


class AllocateResultsView(views.generic.DetailView):
    model = Question
    template_name = 'allocation/allocationResults/results_page.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.results_visible_after and timezone.now() < self.object.results_visible_after:
            return redirect("allocation:allocation_tab")
        return super().get(request, *args, **kwargs)

    def transformSubmittedRankings(self, items, submitted_rankings):
        for entry in submitted_rankings.items():
            key, values = entry
            if len(values) < len(items):
                temp = []
                for j in range(len(values)):
                    for entry in values[j]:
                        temp.append([entry])
                values = temp
                submitted_rankings[key] = values
        return submitted_rankings

    def getPreferencesList(self, pref_set):
        preferences = []
        for pref in pref_set.values():
            preferences.append(pref)
        return preferences

    def transformPreferences(self, items, preferences):
        for i in range(len(preferences)):
            if len(preferences[i]) < len(items):
                temp = []
                for j in range(len(preferences[i])):
                    for entry in preferences[i][j]:
                        temp.append([entry])
                preferences[i] = temp

        for i in range(len(preferences)):
            for j in range(len(preferences[i])):
                preferences[i][j] = preferences[i][j][0]
        return preferences

    def transformAllocatedItems(self, allocated_items):
        allocated_items_transformed = [
            ["" for j in range(len(allocated_items[i]))] for i in range(len(allocated_items))
        ]
        for i in range(len(allocated_items)):
            for j in range(len(allocated_items[i])):
                item_obj = allocated_items[i][j]
            if isinstance(item_obj, str):
                allocated_items_transformed[i][j] = item_obj[4:]
            elif hasattr(item_obj, 'item_text'):
                allocated_items_transformed[i][j] = item_obj.item_text
            else:
                allocated_items_transformed[i][j] = str(item_obj)
        return allocated_items_transformed

    def getSumOfAllocatedItems(self, allocated_items, submitted_rankings):
        sum_of_alloc_items_values = []
        allocated_items_with_values = []
        for i in range(len(allocated_items)):
            sum_of_values = 0
            items_with_values = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(allocated_items[i])):
                for k in range(len(submitted_rankings_values)):
                    if "score" in submitted_rankings_values[k][0]:
                        if submitted_rankings_values[k][0]["name"] == allocated_items[i][j]:
                            sum_of_values += submitted_rankings_values[k][0]["score"]
                            items_with_values.append((
                                submitted_rankings_values[k][0]["name"][4:],
                                submitted_rankings_values[k][0]["score"]
                            ))
            sum_of_alloc_items_values.append(sum_of_values)
            allocated_items_with_values.append(items_with_values)
        return allocated_items_with_values, sum_of_alloc_items_values

    def formatOptions(self, items):
        for i in range(len(items)):
            items[i] = items[i][4:]
        return items

    def getPrefWithValues(self, submitted_rankings):
        preferences_with_values = []
        for i in range(len(submitted_rankings)):
            curr_cand_preferences_with_values = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(submitted_rankings_values)):
                if "score" in submitted_rankings_values[j][0]:
                    curr_cand_preferences_with_values.append([
                        submitted_rankings_values[j][0]["name"][4:],
                        submitted_rankings_values[j][0]["score"]
                    ])
            preferences_with_values.append(curr_cand_preferences_with_values)
        return preferences_with_values

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        question = self.object

        if not question.response_set.exists():
            ctx['error_message'] = "No responses found. Users must submit preferences before viewing allocations."
            return ctx

        mechanism_info = self._prepare_mechanism_info(question)
        ctx.update(mechanism_info)

        user_data = self._prepare_user_data(question)
        ctx.update(user_data)

        current_user_id = self.request.user.id
        current_user_name = user_data['user_names'].get(current_user_id, "")
        ctx['current_user_name'] = current_user_name
        ctx['empty_string'] = ""

        curr_user_ranking = user_data['submitted_rankings'].get(current_user_id, [])
        ctx['curr_user_pref'] = []
        ctx['curr_user_pref_values'] = []

        for entry in curr_user_ranking:
            if not entry:
                continue
            val = entry[0]
            if isinstance(val, dict) and 'name' in val:
                ctx['curr_user_pref'].append(val['name'][4:])
                ctx['curr_user_pref_values'].append(val.get('score', 0))
            elif isinstance(val, str):
                ctx['curr_user_pref'].append(val[4:])
                ctx['curr_user_pref_values'].append(0)

        context_data = {
            'question_id': question.id,
            'mechanism_id': ctx['current_mechanism_id'],
            'preferences': user_data['preferences'],
            'sorted_user_ids': user_data['sorted_user_ids']
        }

        allocation_result, is_cache_hit = self._get_allocation_result(
            context_data, ctx['chosen_cls'], ctx['chosen_label']
        )
        ctx.update(allocation_result)

        if question.alloc_res_tables & 2 != 0:
            ctx["all_user_preferences"] = self._format_user_preferences(
                user_data['sorted_user_ids'],
                user_data['user_names'],
                user_data['submitted_rankings']
            )

        ctx["is_pareto_optimal"] = False
        if allocation_result.get('allocation_matrix') is not None and user_data.get('preferences'):
            try:
                V = np.array(user_data['preferences'])
                A = np.array(allocation_result['allocation_matrix'])
                ctx["is_pareto_optimal"] = is_po(V, A)
            except Exception as e:
                print("is_PO check failed:", e)

        sum_values = allocation_result.get('sum_of_alloc_items_values', [])
        if sum_values:
            ctx["utilitarian_welfare"] = sum(sum_values)
            ctx["egalitarian_welfare"] = min(sum_values)

        current_user_index = None
        if allocation_result.get('allocated_items') and user_data.get('preferences'):
            preferences_with_values = self.getPrefWithValues(user_data['submitted_rankings'])
            allocated_items_with_values, _ = self.getSumOfAllocatedItems(
                self.transformAllocatedItems(allocation_result['allocated_items']),
                user_data['submitted_rankings']
            )
            envy_matrix = computeEnvyUptoEF1(
                user_data['preferences'],
                allocated_items_with_values,
                preferences_with_values
            )
            ctx['envy_matrix'] = envy_matrix

            allocated_items = allocation_result.get("allocated_items", [])
            items_obj = allocation_result.get("items_obj", [])
            sorted_user_ids = user_data["sorted_user_ids"]
            item_texts = [item.item_text for item in items_obj]

            if current_user_id in sorted_user_ids:
                current_user_index = sorted_user_ids.index(current_user_id)
                user_alloc_items = allocated_items[current_user_index] if current_user_index < len(allocated_items) else []
                ctx["curr_user_bundle"] = user_alloc_items

            if current_user_index is not None and current_user_index < len(user_data['preferences']):
                raw_ranking = user_data['submitted_rankings'].get(sorted_user_ids[current_user_index], [])
                ranking_dict = {}
                for entry in raw_ranking:
                    if entry and isinstance(entry[0], dict):
                        name = entry[0].get('name', '')
                        if name.startswith("item"):
                            ranking_dict[name[4:]] = entry[0].get('score', 0)

                total_value = sum(ranking_dict.get(item.item_text, 0) for item in user_alloc_items)
                ctx["curr_user_bundle_sum"] = total_value
            else:
                ctx["curr_user_bundle_sum"] = 0

        rank_histogram = [0] * len(item_texts) if 'item_texts' in dir() else []
        if allocation_result.get('allocation_matrix') is not None:
            allocation_matrix = allocation_result['allocation_matrix']
            sorted_user_ids = user_data['sorted_user_ids']
            items_obj = allocation_result.get("items_obj", [])
            item_texts = [item.item_text for item in items_obj]
            rank_histogram = [0] * len(item_texts)
            for i, row in enumerate(allocation_matrix):
                user_id = sorted_user_ids[i]
                raw_pref = user_data['submitted_rankings'].get(user_id, [])
                ranked_items = []
                for entry in raw_pref:
                    if isinstance(entry[0], dict):
                        name = entry[0].get("name", "")[4:]
                        score = entry[0].get("score", 0)
                        ranked_items.append((name, score))
                ranked_items.sort(key=lambda x: -x[1])
                item_to_rank = {name: rank for rank, (name, _) in enumerate(ranked_items)}
                for j, alloc in enumerate(row):
                    if alloc == 1:
                        item_name = item_texts[j]
                        if item_name in item_to_rank:
                            rank_histogram[item_to_rank[item_name]] += 1

        ctx["rank_histogram"] = rank_histogram
        return ctx

    def _prepare_mechanism_info(self, question):
        locked_alg_id = question.poll_algorithm
        alg_bitmask = question.alloc_algorithms

        all_mechanisms = [
            (1,  "Round Robin",      MechanismRoundRobinAllocation),
            (2,  "Max Nash Welfare", MechanismMaximumNashWelfare),
            (4,  "Market (EF1)",     MechanismMarketAllocation),
            (8,  "MarketEq (EQ1)",   MechanismMarketEqAllocation),
            (16, "Leximin",          MechanismLeximinAllocation),
            (32, "MNW Binary",       MechanismMaximumNashWelfareBinary),
        ]

        available_mechanisms = [
            (bit, label) for (bit, label, cls) in all_mechanisms if (alg_bitmask & bit) != 0
        ]
        if not available_mechanisms:
            available_mechanisms = [(1, "Round Robin")]

        requested_alg = self.request.GET.get("alg", None)
        if requested_alg is not None:
            try:
                requested_bit = int(requested_alg)
                current_mechanism_id = requested_bit if (alg_bitmask & requested_bit) != 0 else locked_alg_id
            except ValueError:
                current_mechanism_id = locked_alg_id
        else:
            current_mechanism_id = locked_alg_id

        chosen_cls = MechanismRoundRobinAllocation
        chosen_label = "Round Robin"
        for (bit, label, cls) in all_mechanisms:
            if bit == current_mechanism_id:
                chosen_cls = cls
                chosen_label = label
                break

        return {
            "available_mechanisms": available_mechanisms,
            "current_mechanism_id": current_mechanism_id,
            "current_mechanism": chosen_label,
            "chosen_cls": chosen_cls,
            "chosen_label": chosen_label,
            "selected_alloc_res_tables_sum": question.alloc_res_tables
        }

    def _prepare_user_data(self, question):
        response_set = question.response_set.all()
        user_names = {}
        user_pics = {}
        submitted_rankings = {}

        for resp in response_set:
            uid = resp.user_id
            if uid not in user_names:
                user_names[uid] = resp.user.first_name
                pic_path = resp.user.userprofile.profile_pic.name
                user_pics[uid] = f"/{pic_path}" if pic_path else ""
            submitted_rankings[uid] = json.loads(resp.behavior_data)["submitted_ranking"]

        sorted_user_ids = sorted(user_names.keys())
        preferences = self._extract_numeric_preferences(
            response_set, sorted_user_ids, question.item_set.count()
        )

        return {
            "candidates": [user_names[uid] for uid in sorted_user_ids],
            "profile_pics": [user_pics[uid] for uid in sorted_user_ids],
            "user_names": user_names,
            "submitted_rankings": submitted_rankings,
            "sorted_user_ids": sorted_user_ids,
            "preferences": preferences,
            "current_user_id": self.request.user.id
        }

    def _extract_numeric_preferences(self, response_set, sorted_user_ids, item_count):
        user_valuations_map = {}

        for resp in response_set:
            uid = resp.user_id
            raw_list = ast.literal_eval(resp.resp_str)
            behavior_dict = json.loads(resp.behavior_data or '{}')
            submitted_scores = behavior_dict.get("submitted_ranking", [])
            item_score_map = {}
            for group in submitted_scores:
                if group and isinstance(group[0], dict):
                    name = group[0].get("name", "")
                    score = group[0].get("score", 0)
                    item_score_map[name] = score

            numeric_vals = []
            for sublist in raw_list:
                for x in sublist:
                    if isinstance(x, str):
                        name = x
                    elif isinstance(x, dict) and "name" in x:
                        name = x["name"]
                    else:
                        name = None
                    if name:
                        val = item_score_map.get(name, 0.0)
                    else:
                        try:
                            val = float(x[4:]) if isinstance(x, str) and x.startswith("item") else 0.0
                        except Exception:
                            val = 0.0
                    numeric_vals.append(val)
            user_valuations_map[uid] = numeric_vals

        for uid in sorted_user_ids:
            if uid not in user_valuations_map or not user_valuations_map[uid]:
                user_valuations_map[uid] = [0.0] * item_count

        max_length = max(len(v) for v in user_valuations_map.values()) if user_valuations_map else item_count
        for uid in user_valuations_map:
            if len(user_valuations_map[uid]) < max_length:
                user_valuations_map[uid] += [0.0] * (max_length - len(user_valuations_map[uid]))

        return [user_valuations_map.get(uid, [0.0] * max_length) for uid in sorted_user_ids]

    def _process_allocation_result(self, result, preferences, sorted_user_ids, question_id):
        allocation_matrix = result.A
        question = Question.objects.get(id=question_id) if question_id else None
        items = list(question.item_set.all()) if question else []

        allocation_data = {
            'allocation_matrix': allocation_matrix,
            'items_obj': items,
        }

        allocated_items = []
        if allocation_matrix is not None:
            N = len(allocation_matrix)
            if N > 0:
                M = len(allocation_matrix[0])
                for i in range(N):
                    user_items = []
                    for j in range(M):
                        if allocation_matrix[i][j] == 1 and j < len(items):
                            user_items.append(items[j])
                        elif allocation_matrix[i][j] == 1:
                            user_items.append({'item_text': f"Item #{j}", 'id': -1})
                    allocated_items.append(user_items)
        allocation_data['allocated_items'] = allocated_items

        sum_values = []
        for i, prefs in enumerate(preferences):
            if i < len(allocation_matrix):
                utility = sum(prefs[j] * allocation_matrix[i][j] for j in range(len(prefs)))
                sum_values.append(utility)
        allocation_data['sum_of_alloc_items_values'] = sum_values

        return allocation_data

    def _get_allocation_result(self, context_data, mechanism_class, mechanism_label):
        cached_result, is_hit = AllocationCache.get_cached_result(context_data)
        if is_hit:
            logger.info(f"Cache hit for mechanism {mechanism_label}")
            return self._process_cached_allocation_data(cached_result), True

        logger.info(f"Cache miss for mechanism {mechanism_label}, computing allocation")
        start_time = timezone.now()
        try:
            mechanism = mechanism_class()
            result = mechanism.allocate(valuations=context_data['preferences'])
            allocation_data = self._process_allocation_result(
                result,
                context_data['preferences'],
                context_data['sorted_user_ids'],
                context_data.get('question_id')
            )
            AllocationCache.store_result(context_data, allocation_data)
            computation_time = (timezone.now() - start_time).total_seconds()
            logger.info(f"Allocation computed in {computation_time:.2f}s for {mechanism_label}")
            return allocation_data, False
        except Exception as e:
            logger.error(f"Error computing allocation with {mechanism_label}: {str(e)}", exc_info=True)
            n = len(context_data['preferences'])
            m = max(len(p) for p in context_data['preferences']) if context_data['preferences'] else 0
            return {
                'error_message': f"Could not compute allocation with {mechanism_label}: {str(e)}",
                'allocation_matrix': np.zeros((n, m)),
                'allocated_items': [[] for _ in range(n)],
                'sum_of_alloc_items_values': [0] * n
            }, False

    def _format_user_preferences(self, sorted_user_ids, user_names, submitted_rankings):
        all_user_prefs = []
        for uid in sorted_user_ids:
            username = user_names[uid]
            ranking = submitted_rankings[uid]
            cleaned = []
            for group in ranking:
                if group and isinstance(group[0], dict):
                    cleaned.append(group[0].get("name", "")[4:])
            all_user_prefs.append((username, cleaned))
        return all_user_prefs

    def _process_cached_allocation_data(self, cached_result, question_id=None):
        if not question_id:
            question_id = self.kwargs.get('pk')
        question = Question.objects.get(id=question_id)
        items = list(question.item_set.all())
        cached_result['items_obj'] = items
        if 'allocated_items' in cached_result:
            for i, agent_items in enumerate(cached_result['allocated_items']):
                for j, item_data in enumerate(agent_items):
                    if isinstance(item_data, dict) and 'id' in item_data and item_data['id'] > 0:
                        for item in items:
                            if item.id == item_data['id']:
                                cached_result['allocated_items'][i][j] = item
                                break
        return cached_result


class AllocationOrder(views.generic.DetailView):
    model = Question
    template_name = 'allocation/allocation_order.html'

    def get_queryset(self):
        return Question.objects.filter(pub_date__lte=timezone.now())

    def get_context_data(self, **kwargs):
        ctx = super(AllocationOrder, self).get_context_data(**kwargs)
        currentAllocationOrder = self.object.allocationvoter_set.all()
        tempOrderStr = self.request.GET.get('order', '')
        if tempOrderStr == "null":
            ctx['question_voters'] = self.object.question_voters.all()
            return ctx
        if len(currentAllocationOrder) > 0:
            ctx['currentSelection'] = currentAllocationOrder
        ctx['question_voters'] = self.object.question_voters.all()
        return ctx


def setAllocationOrder(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    if orderStr == "":
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    prefOrder = orderStr.split(",")
    if len(prefOrder) != len(question.question_voters.all()):
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    for voter in question.allocationvoter_set.all():
        voter.delete()

    item_num = 1
    for item in question.question_voters.all():
        arrayIndex = prefOrder.index("item" + str(item_num))
        if arrayIndex != -1:
            user = question.question_voters.all()[arrayIndex]
            voter, created = AllocationVoter.objects.get_or_create(
                question=question, user=user, response=None)
            voter.save()
        item_num += 1

    return HttpResponseRedirect(reverse('allocation:viewAllocationOrder', args=(question.id,)))


def stopAllocation(request, question_id):
    """Stop an allocation poll and compute the final allocation."""
    from .utils import getFinalAllocation
    question = get_object_or_404(Question, pk=question_id)

    if request.user != question.question_owner:
        return HttpResponseRedirect(reverse('polls:index'))

    question.status = 3
    getFinalAllocation(question)
    question.save()

    from polls.email import EmailThread
    if question.emailStart:
        email_class = EmailThread(request, question_id, 'stop')
        email_class.start()

    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
