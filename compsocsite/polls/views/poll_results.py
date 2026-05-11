import ast
import collections
import datetime
import itertools
import json
import logging
import random
import traceback
from functools import wraps

import numpy as np
from appauth.models import *
from django import views
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from groups.models import *
from multipolls.models import *
from prefpy.allocation_properties import is_po
from prefpy.egmm_mixpl import *
from prefpy.gmm_mixpl import *
from prefpy.mechanism import *

from ..email import setupEmail
from ..models import *
from ..utils import (buildResponseDict, colorLuminance, getPrefOrder,
                     interpretResponseDict)

# logger for cache
logger = logging.getLogger(__name__)

active_polls = []

def block_code_users(redirect_url="/polls/regular_polls/code"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.session.get("is_code_user"):
                return redirect(redirect_url)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


def getPollWinner(question):
    """
    Calculate winner of poll. 
    
    Parameter: Question object.
    Returns: string containing winner(s), mixture for k = 1, 2, 3.
    """
    print(f"\n[getPollWinner] STARTING for Question ID: {question.id} ('{question.question_text}')")
    try:
        all_responses = question.response_set.filter(active=1).order_by('-timestamp')
        (latest_responses, previous_responses) = categorizeResponses(all_responses)
        # Calculate results
        cand_map = getCandidateMapFromList(list(question.item_set.all()))
        results = getVoteResults(latest_responses, cand_map)
        print(f"  - [getPollWinner] getVoteResults finished. results length: {len(results)}")
        
        (vote_results, mixtures_pl1, mixtures_pl2, mixtures_pl3) = ([],[],[],[])
        if(len(results) == 4):
            (vote_results, mixtures_pl1, mixtures_pl2, mixtures_pl3) = results
        else : 
            print("  - [getPollWinner] ERROR: getVoteResults returned wrong number of items.")
            return "",json.dumps([]),json.dumps([]),json.dumps([])
        
        index_vote_results = question.poll_algorithm - 1
        # Bounds check
        if index_vote_results < 0 or index_vote_results >= len(vote_results):
            print(f"  - [getPollWinner] ERROR: index_vote_results {index_vote_results} out of range (size {len(vote_results)})")
            index_vote_results = 0 # Fallback to Plurality
            
        current_result = vote_results[index_vote_results]
        print(f"  - [getPollWinner] index_vote_results: {index_vote_results}, current_result size: {len(current_result)}")
    
        print(f"  - [getPollWinner] Calculation finished. current_result size: {len(current_result)}")
        winnerStr = ""
        
        # Transform result data into JSON strings and save in database
        
        # item_set = getCandidateMap(latest_responses[0])
        for index, score in current_result.items():
            # index 5 uses Simplified Bucklin, where score is rank.
            #   A low score means it has a high rank (e.g. rank 1 > rank 2),
            #   so the best score is the minimum.
            # All other indices rank score from highest to lowest, so the best score would be
            #   the maximum.
            if ((score == min(current_result.values()) and index_vote_results == 5)
                    or (score == max(current_result.values()) and index_vote_results != 5)):
                #add a comma to separate the winners
                if winnerStr != "":
                    winnerStr += ", "
                #add the winner
                winnerStr += cand_map[index].item_text
        
        print(f"  - [getPollWinner] Winners: {winnerStr}")

        if hasattr(question, 'finalresult'):
            try:
                print("  - [getPollWinner] Deleting existing finalresult...")
                question.finalresult.delete()
            except Exception as e:
                print(f"  - [getPollWinner] Note: Error deleting finalresult (might not exist): {e}")

        result = FinalResult(question=question, timestamp=timezone.now(),
                            result_string="", mov_string="", cand_num=question.item_set.all().count(),
                            node_string="", edge_string="", shade_string="")
        
        resultlist = []
        print("  - [getPollWinner] Calling getMarginOfVictory...")
        mov = getMarginOfVictory(latest_responses, cand_map)
        print(f"  - [getPollWinner] getMarginOfVictory finished. Size: {len(mov)}")
        movlist = [str(i) for i in mov]
        for x in range(0, len(vote_results)):
            for key, value in vote_results[x].items():
                resultlist.append(str(value))
            # resultstr += str(value)
            # resultstr += ","
    # for x in range(0, len(mov)):
    #     movstr += str(mov[x])
    #     movstr += ","
    # resultstr = resultstr[:-1]
    # movstr = movstr[:-1]
        (nodes, edges) = parseWmg(latest_responses, cand_map)
    # for node in nodes:
    #     for k, v in node.items():
    #         nodestr += k + "," + str(v) + ";"
    #     nodestr += "|"
    # nodestr = nodestr[:-2]
    # for edge in edges:
    #     for k, v in edge.items():
    #         edgestr += k + "," + str(v) + ";"
    #     edgestr += "|"
    # edgestr = edgestr[:-2]
        shadevalues = getShadeValues(vote_results)
    # for x in shadevalues:
    #     for y in x:
    #         shadestr += y + ";"
    #     shadestr += "|"
    # shadestr = shadestr[:-2]
        result.result_string = json.dumps(resultlist)
        result.mov_string = json.dumps(movlist)
        result.node_string = json.dumps(nodes)
        result.edge_string = json.dumps(edges)
        result.shade_string = json.dumps(shadevalues)
        print("  - [getPollWinner] Saving FinalResult...")
        result.save()
        
        # Resets new vote flag so that result is not computed again
        if question.new_vote:
            question.new_vote = False
        question.winner = winnerStr
        question.mixtures_pl1 = json.dumps(mixtures_pl1)
        question.mixtures_pl2 = json.dumps(mixtures_pl2)
        question.mixtures_pl3 = json.dumps(mixtures_pl3)
        print("  - [getPollWinner] Saving Question...")
        question.save()

        print("[getPollWinner] SUCCESSFUL completion.")
        return winnerStr, json.dumps(mixtures_pl1), json.dumps(mixtures_pl2), json.dumps(mixtures_pl3)
    except Exception as e:
        print(f"\n!!! [getPollWinner] CRITICAL ERROR: {e}")
        traceback.print_exc()
        return "", json.dumps([]), json.dumps([]), json.dumps([])


def interpretResult(finalresult):
    """
    Interpret result into strings that can be shown on the result page.
    
    Parameter: FinalResult object
    Returns: list of list of String containing data used on result page.
    """
    if finalresult is None:
        print("  [interpretResult] ERROR: finalresult is None")
        return [[], [], [], [], []]
        
    print(f"  [interpretResult] Processing finalresult ID: {finalresult.id}")
    candnum = finalresult.cand_num
    print(f"  [interpretResult] candnum: {candnum}")
    
    try:
        resultlist = json.loads(finalresult.result_string)
        print(f"  [interpretResult] resultlist loaded. size: {len(resultlist)}")
    except Exception as e:
        print(f"  [interpretResult] ERROR loading result_string: {e}")
        resultlist = []
        
    tempResults = []
    algonum = len(getListPollAlgorithms())
    if len(resultlist) < candnum*algonum:
        print(f"  [interpretResult] Result list too short ({len(resultlist)} < {candnum}*{algonum}). Setting algonum to 7.")
        algonum = 7
        
    if len(resultlist) > 0:
        try:
            for x in range(0, algonum):
                tempList = []
                for y in range(x*candnum, (x+1)*candnum):
                    tempList.append(resultlist[y])
                tempResults.append(tempList)
        except Exception as e:
            print(f"  [interpretResult] ERROR during resultlist processing: {e}")
            
    try:
        tempMargin = json.loads(finalresult.mov_string)
        tempShades = json.loads(finalresult.shade_string)
        temp_nodes = json.loads(finalresult.node_string)
        tempEdges = json.loads(finalresult.edge_string)
        print("  [interpretResult] All JSON fields loaded successfully.")
    except Exception as e:
        print(f"  [interpretResult] ERROR loading other JSON fields: {e}")
        tempMargin, tempShades, temp_nodes, tempEdges = [], [], [], []
        
    return [tempResults, tempMargin, tempShades, temp_nodes, tempEdges]


def recalculateResult(request, question_id):
    """Called when poll owner wants to recalculate result manually."""
    
    question = get_object_or_404(Question, pk=question_id)
    getPollWinner(question)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def isPrefReset(request):
    """Reset order in two-column UI. No longer used."""
    # reset link would have '?order=null' at the end
    orderStr = request.GET.get('order', '')
    if orderStr == "null":
        return True
    return False


def getCurrentSelection(mostRecentResponse):
    """
    Given a response, return current ranking data that can be loaded on voting UIs.
    
    Parameter: Response object.
    Returns: List<List<Item>>
    """
    responseDict = {}
    responseDict = buildResponseDict(mostRecentResponse, mostRecentResponse.question,
                                    getPrefOrder(mostRecentResponse.resp_str,
                                    mostRecentResponse.question))
    rd = responseDict
    array = []
    for itr in range(mostRecentResponse.question.item_set.all().count()):
        array.append([])
    for itr in rd:
        if rd[itr] != 1000:
            array[rd[itr] - 1].append(itr)
    return array


def getUnrankedCandidates(resp):
    """Simiar to getCurrentSelection; gets unranked alternatives."""
    
    rd = buildResponseDict(resp, resp.question, getPrefOrder(resp.resp_str, resp.question))
    array = []
    for itr in rd:
        if rd[itr] == 1000:
            array.append(itr)
    if len(array) == 0:
        return None
    return array


class DetailView(views.generic.DetailView):
    """Define poll voting page view."""
    
    model = Question
    template_name = 'polls/detail.html'

    def get_order(self, ctx):
        """Define the initial order to be displayed on the page."""
        
        default_order = list(ctx['object'].item_set.all())
        random.shuffle(default_order)
        return default_order

    def get_context_data(self, **kwargs):
        ctx = super(DetailView, self).get_context_data(**kwargs)
        ctx['lastcomment'] = ""

        #Case for anonymous user
        if self.request.user.get_username() == "":
            if isPrefReset(self.request):
                ctx['items'] = self.object.item_set.all()
                return ctx
            # check the anonymous voter
            if 'anonymousvoter' in self.request.session and 'anonymousid' in self.request.session:
                # sort the responses from latest to earliest
                anon_id = self.request.session['anonymousid']
                curr_anon_resps = self.object.response_set.filter(anonymous_id=anon_id, active=1).reverse()
                if len(curr_anon_resps) > 0:
                    # get the voter's most recent selection
                    mostRecentAnonymousResponse = curr_anon_resps[0]
                    if mostRecentAnonymousResponse.comment:
                        ctx['lastcomment'] = mostRecentAnonymousResponse.comment
                    ctx['currentSelection'] = getCurrentSelection(curr_anon_resps[0])
                    ctx['unrankedCandidates'] = getUnrankedCandidates(curr_anon_resps[0])
                    ctx['itr'] = itertools.count(1, 1)
                    items_ano = []
                    for item in ctx['currentSelection']:
                        for i in item:
                            items_ano.append(i)
                    if not ctx['unrankedCandidates'] == None:
                        for item in ctx['unrankedCandidates']:
                            items_ano.append(item)
                    ctx['items'] = items_ano
            else:
                # load choices in the default order
                ctx['items'] = self.object.item_set.all()
            return ctx

        # Get the responses for the current logged-in user from latest to earliest
        currentUserResponses = self.object.response_set.filter(user=self.request.user, active=1).reverse()

        if len(currentUserResponses) > 0:
            latest_response = currentUserResponses[0] #storing last submission to fetch after submit
            ctx['submitted_ranking'] = latest_response.behavior_data
            if currentUserResponses[0].comment:
                ctx['lastcomment'] = currentUserResponses[0].comment

        # reset button
        if isPrefReset(self.request):
            ctx['items'] = self.get_order(ctx)
            return ctx

        # check if the user submitted a vote earlier and display that for modification
        if len(currentUserResponses) > 0 and self.request.user.get_username() != "":
            ctx['currentSelection'] = getCurrentSelection(currentUserResponses[0])
            ctx['itr'] = itertools.count(1, 1)
            ctx['unrankedCandidates'] = getUnrankedCandidates(currentUserResponses[0])
            items = []
            for item in ctx['currentSelection']:
                for i in item:
                    items.append(i)
            if not ctx['unrankedCandidates'] == None:
                for item in ctx['unrankedCandidates']:
                    items.append(item)
            ctx['items'] = items
        else:
            # no history so display the list of choices
            ctx['items'] = self.get_order(ctx)
        
        return ctx
    
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


def addPreferenceValueToResp(objs):
    for i in range(len(objs)):
        response, prefOrder = objs[i]

        # convert behavior_data to json and extract submitted_ranking
        behavior_data = json.loads(response.behavior_data)
        submitted_rankings = behavior_data.get("submitted_ranking", [])

        # Initialize empty set
        scores = set()

        # Extract the scores from submitted_rankings and add it to the scores set
        for tier in submitted_rankings:
            for jsonObj in tier:
                if isinstance(jsonObj, dict) and "score" in jsonObj:
                    scores.add(jsonObj["score"])

        scores = sorted(list(scores))[-1::-1] if scores else []

        # Add score as the first element in the tier-list
        for i in range(len(scores) if len(scores) < len(prefOrder) else len(prefOrder)):
            prefOrder[i].insert(0, scores[i])

        # print(prefOrder, scores)

    return objs


@method_decorator(block_code_users("/polls/regular_polls/code"), name="dispatch")
class PollInfoView(views.generic.DetailView):
    model = Question
    template_name = 'polls/pollinfo.html'

    def getUsersFromLatestCSV(self, recentCSVText, existingUsers):
        registeredUsers, unRegisteredUsers=[],[]
        if(recentCSVText is not None): 
            userIDsFromCSV = recentCSVText.split(",")
            userIDsFromCSV = [userID.strip() for userID in userIDsFromCSV]

            existingUserIDs = [user.username for user in existingUsers]

            for userID in userIDsFromCSV:
                if userID in existingUserIDs:
                    registeredUsers.append(userID)
                else:
                    unRegisteredUsers.append(userID)

        return registeredUsers, unRegisteredUsers

    def get_context_data(self, **kwargs):
        ctx = super(PollInfoView, self).get_context_data(**kwargs)
        curr_question = self.object
        emailInvite = Email.objects.filter(question=self.object, type=1)
        setupEmail(self.object)
        if Email.objects.filter(question=self.object).count() > 0:
            ctx['emailInvite'] = Email.objects.filter(question=self.object, type=1)[0]
            ctx['emailDelete'] = Email.objects.filter(question=self.object, type=2)[0]
            ctx['emailStart'] = Email.objects.filter(question=self.object, type=3)[0]
            ctx['emailStop'] = Email.objects.filter(question=self.object, type=4)[0]
            ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=4)[0]
            if len(Email.objects.filter(question=self.object, type=5)) > 0:
                ctx['emailInviteCSV'] = Email.objects.filter(question=self.object, type=5)[0]
        ctx['users'] = User.objects.filter(userprofile__is_code_user=False)
        ctx['items'] = self.object.item_set.all()
        ctx['groups'] = Group.objects.all()
        ctx['poll_algorithms'] = getListPollAlgorithms()
        ctx['alloc_methods'] = getAllocMethods()
        twos = []
        for i in range(0, max(len(ctx['poll_algorithms']), len(ctx['alloc_methods']))):
            twos.append(2 ** i)
        ctx['twos'] = twos
        ctx['bools'] = self.object.vote_rule

        # display this user's history
        currentUserResponses = self.object.response_set.filter(user=self.request.user,active=1).order_by('-timestamp')
        if len(currentUserResponses) > 0:
            ctx['user_latest_responses'] = getSelectionList([currentUserResponses[0]])
            if(curr_question.question_type == 2): ctx['user_latest_responses'] = addPreferenceValueToResp(ctx['user_latest_responses'])

        ctx['user_previous_responses'] = getSelectionList(currentUserResponses[1:])
        if(curr_question.question_type == 2): 
            ctx['user_previous_responses'] = addPreferenceValueToResp(ctx['user_previous_responses'])

        # get history of all users
        all_responses = self.object.response_set.filter(active=1).order_by('-timestamp')
        (latest_responses, previous_responses) = categorizeResponses(all_responses)
        ctx['latest_responses'] = getSelectionList(latest_responses)
        ctx['previous_responses'] = getSelectionList(previous_responses)
        if(curr_question.question_type == 2): 
            ctx['latest_responses'] = addPreferenceValueToResp(ctx['latest_responses'])
            ctx['previous_responses'] = addPreferenceValueToResp(ctx['previous_responses'])

        # get deleted votes
        deleted_resps = self.object.response_set.filter(active=0).order_by('-timestamp')
        (latest_deleted_resps,previous_deleted_resps) = categorizeResponses(deleted_resps)
        ctx['latest_deleted_resps'] = getSelectionList(latest_deleted_resps)
        ctx['previous_deleted_resps'] = getSelectionList(previous_deleted_resps)
        if(curr_question.question_type == 2):
            ctx['latest_deleted_resps'] = addPreferenceValueToResp(ctx['latest_deleted_resps'])
            ctx['previous_deleted_resps'] = addPreferenceValueToResp(ctx['previous_deleted_resps'])

        if self.object.question_voters.all().count() > 0:
            progressPercentage = len(latest_responses) / self.object.question_voters.all().count()
            progressPercentage = progressPercentage * 100
            ctx['progressPercentage'] = progressPercentage
        ctx['request_list'] = self.object.signuprequest_set.filter(status=1)

        # alloc_res_tables contains display options for results of an allocation
        selected_alloc_res_tables_sum = curr_question.alloc_res_tables
        ctx['selected_alloc_res_tables_sum'] = selected_alloc_res_tables_sum

        # Registered and unRegisteredUsers
        registeredUsers, unRegisteredUsers = self.getUsersFromLatestCSV(curr_question.recentCSVText, ctx['users'])
        ctx['registeredUsers'] = registeredUsers
        ctx['unRegisteredUsers'] = unRegisteredUsers
        ctx['recentCSVText'] = curr_question.recentCSVText

        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


class AllocateResultsView(views.generic.DetailView):
    model = Question
    template_name = 'polls/allocationResults/results_page.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.results_visible_after and timezone.now() < self.object.results_visible_after:
            return redirect("polls:allocation_tab")   #to /polls/allocation_tab/
        return super().get(request, *args, **kwargs)

    def getItemsObjects(self):
        items = [] 
        items_obj=[]
        for item in list(self.object.item_set.all()):
            items.append("item"+item.item_text)
            items_obj.append(item)
        return items,items_obj
    
    def getDataFromResponseSet(self, response_set):
        pref_set = {}
        candidates={}
        submitted_rankings={}
        profile_pics = {}
        # extracting required information from response_set
        # using dictionary instead of list to avoid duplicate preferences in response_set
        for response in response_set:
            candidates[response.user_id] = response.user.first_name 
            url = response.user.userprofile.profile_pic.name;
            profile_pics[response.user_id] = "/"+url if url != None else ''
            pref_set[response.user_id] = ast.literal_eval(response.resp_str)
            submitted_rankings[response.user_id]  = json.loads(response.behavior_data)["submitted_ranking"]
        return pref_set, candidates, submitted_rankings, profile_pics
    
    def transformSubmittedRankings(self, items, submitted_rankings):
        #transform submitted rankings
        for entry in submitted_rankings.items():
            key,values = entry
            if(len(values) < len(items)):
                temp = []
                for j in range(len(values)):
                    for entry in values[j]:
                        temp.append([entry])
                values= temp
                submitted_rankings[key] = values
        return submitted_rankings
    
    def getPreferencesList(self, pref_set):
        preferences=[]
        # change the type of preferences so that it is compatible to 
        # store and retrieve from list
        for pref in pref_set.values(): preferences.append(pref)
        return preferences
        
    def transformPreferences(self, items, preferences):
        # transform Preferences
        for i in range(len(preferences)):
            if(len(preferences[i]) < len(items)):
                temp = []
                for j in range(len(preferences[i])):
                    for entry in preferences[i][j]:
                        temp.append([entry])
                preferences[i]= temp

        for i in range(len(preferences)):
            for j in range(len(preferences[i])):
                preferences[i][j] = preferences[i][j][0]
        return preferences

    def transformAllocatedItems(self, allocated_items):
        # transform allocated_items
        allocated_items_transformed = [["" for j in range(len(allocated_items[i]))] for i in range(len(allocated_items))]
        for i in range(len(allocated_items)):
            for j in range(len(allocated_items[i])):
                item_obj = allocated_items[i][j]
            if isinstance(item_obj, str):
                allocated_items_transformed[i][j] = item_obj[4:]  # "itemcake" → "cake"
            elif hasattr(item_obj, 'item_text'):
                allocated_items_transformed[i][j] = item_obj.item_text
            else:
                allocated_items_transformed[i][j] = str(item_obj)
        return allocated_items_transformed
    
    def getSumOfAllocatedItems(self, allocated_items, submitted_rankings):
        # Computing allocated items and Sum of values of allocated items for each candidate
        sum_of_alloc_items_values = []
        allocated_items_with_values =[]
        for i in range(len(allocated_items)):
            sum_of_values = 0
            items_with_values = []
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(allocated_items[i])):
                #submitted_rankings_values = list(submitted_rankings.values())[i]
                for k in range(len(submitted_rankings_values)):
                    if "score" in submitted_rankings_values[k][0]:
                        if(submitted_rankings_values[k][0]["name"] == allocated_items[i][j]):
                            sum_of_values+=submitted_rankings_values[k][0]["score"]
                            items_with_values.append((submitted_rankings_values[k][0]["name"][4:], submitted_rankings_values[k][0]["score"]))
            sum_of_alloc_items_values.append(sum_of_values)
            allocated_items_with_values.append(items_with_values)
        return allocated_items_with_values, sum_of_alloc_items_values
    
    def formatOptions(self, items):
        # remove 'item' from 'itemOption' string
        for i in range(len(items)):
            items[i] = items[i][4:]
        return items

    def getPrefWithValues(self, submitted_rankings):
        # computing preferences with values for each candidate
        preferences_with_values = []
        for i in range(len(submitted_rankings)):
            curr_cand_preferences_with_values=[]
            submitted_rankings_values = list(submitted_rankings.values())[i]
            for j in range(len(submitted_rankings_values)):
                if "score" in submitted_rankings_values[j][0]:
                    curr_cand_preferences_with_values.append([submitted_rankings_values[j][0]["name"][4:], submitted_rankings_values[j][0]["score"]])
            preferences_with_values.append(curr_cand_preferences_with_values)
        return preferences_with_values
    
    def computeEnvyUptoEF1(self, preferences, allocated_items_with_values,preferences_with_values):
        # compute envy matrix
        envy_matrix = [[(0,0) for j in range(len(preferences))] for i in range(len(preferences))]
        for i in range(len(allocated_items_with_values)):
            for j in range(len(allocated_items_with_values)):
                if i!=j:
                    envy,sum2 = self.getEnvy(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                    envy_matrix[i][j]  = (envy,sum2)
                    if envy_matrix[i][j][0] < 0:
                        ef1_val = self.getEF1(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                        if ef1_val == "EF1":
                            envy_matrix[i][j] = ("EF1",sum2)
                else:
                    envy_matrix[i][j] = (0,0)
        return envy_matrix
    
    def computePureEF1(self, preferences, allocated_items_with_values, preferences_with_values):
        # compute envy free upto 1 item matrix
        ef1_matrix = [[0 for j in range(len(preferences))] for i in range(len(preferences))]
        for i in range(len(allocated_items_with_values)):
            for j in range(len(allocated_items_with_values)):
                if i!=j:
                    ef1_matrix[i][j] = self.getEF1(preferences_with_values[i], allocated_items_with_values[i], preferences_with_values[j],allocated_items_with_values[j])
                else:
                    ef1_matrix[i][j] = 0

    def getEnvy(self, pref1, allocated_items1, pref2, allocated_items2):  

        # cand 1 sum
        sum1 = 0
        print("allocated_items1:", allocated_items1)

        for item,val in allocated_items1:
            sum1+=val

        # cand 2 sum with cand 1 preferences
        sum2 = 0
        for item1, val1 in allocated_items2:
            for item2, val2 in pref1:
                if(item1 == item2):sum2+=val2
            
        return sum1-sum2,sum2

    def getEF1(self, pref1, allocated_items1, pref2, allocated_items2):
        for i in range(len(allocated_items2)):

            copy_allocated_items2 = allocated_items2.copy()
            copy_allocated_items2.remove(allocated_items2[i])

            # cand 1 sum
            sum1 = 0
            for item,val in allocated_items1:
                sum1+=val

            # cand 2 sum with cand 1 preferences
            sum2 = 0
            for item1, val1 in copy_allocated_items2:
                for item2, val2 in pref1:
                    if(item1 == item2):sum2+=val2

            EF1_val = sum1-sum2   
            if EF1_val >= 0:
                return "EF1"
        return "Not EF1"
    
    def getAllocatedItemObjects(self, item_objs, items_texts):
        allocated_items_objs = []
        for obj in item_objs:
            for item_name in items_texts:
                if item_name == obj.item_text:
                    allocated_items_objs.append(obj)
        return allocated_items_objs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        question = self.object  # the current question instance

        # if no responses, nothing to show
        if not question.response_set.exists():
            ctx['error_message'] = "No responses found. Users must submit preferences before viewing allocations."
            return ctx
        
        # get mechanism information and prepare context
        mechanism_info = self._prepare_mechanism_info(question)
        ctx.update(mechanism_info)
        
        # get user responses and preferences
        user_data = self._prepare_user_data(question)
        ctx.update(user_data)
        
        current_user_id = self.request.user.id
        current_user_name = user_data['user_names'].get(current_user_id, "")
        ctx['current_user_name'] = current_user_name
        ctx['empty_string'] = ""

        curr_user_ranking = user_data['submitted_rankings'].get(current_user_id, [])
        ctx['curr_user_pref'] = []
        ctx['curr_user_pref_values'] = []

        for entry in curr_user_ranking: #support for twocol & onecol
            if not entry:
                continue
            val = entry[0]
            if isinstance(val, dict) and 'name' in val:
                ctx['curr_user_pref'].append(val['name'][4:])  # Strip "item" prefix
                ctx['curr_user_pref_values'].append(val.get('score', 0))
            elif isinstance(val, str):
                ctx['curr_user_pref'].append(val[4:])  #for string like "itemcake"
                ctx['curr_user_pref_values'].append(0)
        # create context data dictionary for caching
        context_data = {
            'question_id': question.id,
            'mechanism_id': ctx['current_mechanism_id'],
            'preferences': user_data['preferences'],
            'sorted_user_ids': user_data['sorted_user_ids']
        }
        
        # get cached result or compute new allocation
        allocation_result, is_cache_hit = self._get_allocation_result(
            context_data, 
            ctx['chosen_cls'], 
            ctx['chosen_label']
        )
        
        # Update context with allocation results
        ctx.update(allocation_result)
        
        # Add additional UI-specific data
        if question.alloc_res_tables & 2 != 0:
            ctx["all_user_preferences"] = self._format_user_preferences(
                user_data['sorted_user_ids'],
                user_data['user_names'],
                user_data['submitted_rankings']
            )
        
        # Check Pareto Optimality
        ctx["is_pareto_optimal"] = False
        if allocation_result.get('allocation_matrix') is not None and user_data.get('preferences'):
            try:
                V = np.array(user_data['preferences'])
                A = np.array(allocation_result['allocation_matrix'])
                ctx["is_pareto_optimal"] = is_po(V, A)
            except Exception as e:
                print("is_PO check failed:", e)

        # Compute Welfare Metrics
        sum_values = allocation_result.get('sum_of_alloc_items_values', [])
        if sum_values:
            utilitarian_welfare = sum(sum_values)
            egalitarian_welfare = min(sum_values)
            ctx["utilitarian_welfare"] = utilitarian_welfare
            ctx["egalitarian_welfare"] = egalitarian_welfare
        
        # Compute envy matrix and add to context
        if allocation_result.get('allocated_items') and user_data.get('preferences'):
            preferences_with_values = self.getPrefWithValues(user_data['submitted_rankings'])

            allocated_items_with_values, _ = self.getSumOfAllocatedItems(
                self.transformAllocatedItems(allocation_result['allocated_items']),
                user_data['submitted_rankings']
            )
            envy_matrix = self.computeEnvyUptoEF1(
                user_data['preferences'],
                allocated_items_with_values,
                preferences_with_values
            )
            ctx['envy_matrix'] = envy_matrix
            #allocation bundle
            allocated_items = allocation_result.get("allocated_items", [])
            items_obj = allocation_result.get("items_obj", [])
            sorted_user_ids = user_data["sorted_user_ids"]
            item_texts = [item.item_text for item in items_obj]

            if current_user_id in sorted_user_ids:
                current_user_index = sorted_user_ids.index(current_user_id)
                user_alloc_items = allocated_items[current_user_index] if current_user_index < len(allocated_items) else []

                ctx["curr_user_bundle"] = user_alloc_items

            if current_user_index < len(user_data['preferences']):
                raw_ranking = user_data['submitted_rankings'].get(sorted_user_ids[current_user_index], [])
                ranking_dict = {}
                for entry in raw_ranking:
                    if entry and isinstance(entry[0], dict):
                        name = entry[0].get('name', '')
                        if name.startswith("item"):
                            item_text = name[4:]  # Strip prefix
                            score = entry[0].get('score', 0)
                            ranking_dict[item_text] = score

                total_value = 0
                for item in user_alloc_items:
                    score = ranking_dict.get(item.item_text, 0)
                    total_value += score

                ctx["curr_user_bundle_sum"] = total_value
            else:
                ctx["curr_user_bundle_sum"] = 0 #preference ordering for firrst choice
        # # First-choice analysis
        # first_choices_data = []
        # if allocation_result.get('allocation_matrix') is not None:
        #     allocation_matrix = allocation_result['allocation_matrix']
        #     preferences = user_data['preferences']
        #     user_rankings = user_data['submitted_rankings']
        #     for i, row in enumerate(allocation_matrix):  # For each agent
        #         user_id = sorted_user_ids[i]
        #         raw_pref = user_rankings.get(user_id, [])
        #         # Create {item_text: score} map
        #         item_val_map = {}
        #         for entry in raw_pref:
        #             if isinstance(entry[0], dict):
        #                 name = entry[0].get("name", "")[4:]  # Remove "item" prefix
        #                 score = entry[0].get("score", 0)
        #                 item_val_map[name] = score
        #         aligned_valuations = [item_val_map.get(item, 0) for item in item_texts]
        #         # Get that agent's valuation vector
        #         print(f"✅ User {i}: {aligned_valuations} | Alloc: {row} | Max: {max(aligned_valuations)}")
        #         max_val = max(aligned_valuations)  # Their most preferred item's value
        #         count = 0
        #         for j, alloc in enumerate(row):  # Loop through their allocated items
        #             if alloc == 1 and aligned_valuations[j] == max_val:
        #                 count += 1
        #         first_choices_data.append(count)

        # ctx["first_choices_data"] = first_choices_data

        rank_histogram = [0] * len(item_texts)  # Ranks 1 to N
        if allocation_result.get('allocation_matrix') is not None:
            allocation_matrix = allocation_result['allocation_matrix']
            preferences = user_data['preferences']
            user_rankings = user_data['submitted_rankings']
            for i, row in enumerate(allocation_matrix):  # For each user
                user_id = sorted_user_ids[i]
                raw_pref = user_rankings.get(user_id, [])

                # Map item_text -> score
                ranked_items = []
                for entry in raw_pref:
                    if isinstance(entry[0], dict):
                        name = entry[0].get("name", "")[4:]  # Remove "item" prefix
                        score = entry[0].get("score", 0)
                        ranked_items.append((name, score))

                # Sort items in descending preference (highest score = rank 1)
                ranked_items.sort(key=lambda x: -x[1])
                item_to_rank = {name: rank for rank, (name, _) in enumerate(ranked_items)}  # 0-based

                # Go through user's allocated items
                for j, alloc in enumerate(row):
                    if alloc == 1:
                        item_name = item_texts[j]
                        if item_name in item_to_rank:
                            rank = item_to_rank[item_name]
                            rank_histogram[rank] += 1
        
        ctx["rank_histogram"] = rank_histogram
        
        return ctx
    
    def _prepare_mechanism_info(self, question):
        """Prepare mechanism selection information"""
        # question model
        locked_alg_id = question.poll_algorithm
        alg_bitmask = question.alloc_algorithms
        
        # define known allocation mechanisms
        all_mechanisms = [
            (1,  "Round Robin",       MechanismRoundRobinAllocation),
            (2,  "Max Nash Welfare",  MechanismMaximumNashWelfare),
            (4,  "Market (EF1)",      MechanismMarketAllocation),
            (8,  "MarketEq (EQ1)",    MechanismMarketEqAllocation),
            (16, "Leximin",           MechanismLeximinAllocation),
            (32, "MNW Binary",        MechanismMaximumNashWelfareBinary),
            (64, "Market EQ1 PO",     MechanismMarketEQ1PO),
        ]

        # build a list of allowed (bit, label) from the bitmask
        available_mechanisms = []
        for (bit, label, cls) in all_mechanisms:
            if (alg_bitmask & bit) != 0:
                available_mechanisms.append((bit, label))
        
        # if no algorithms are selected, fall back to Round Robin
        if not available_mechanisms:
            # Fall back to Round Robin if no algorithms are selected
            available_mechanisms = [(1, "Round Robin")]
        
        # requested ?alg=...
        requested_alg = self.request.GET.get("alg", None)
        if requested_alg is not None:
            try:
                requested_bit = int(requested_alg)
                # if that bit is not in the poll's bitmask, revert to locked
                if (alg_bitmask & requested_bit) == 0:
                    current_mechanism_id = locked_alg_id
                else:
                    current_mechanism_id = requested_bit
            except ValueError:
                current_mechanism_id = locked_alg_id
        else:
            current_mechanism_id = locked_alg_id

        # Find which mechanism class is chosen
        chosen_cls = None
        chosen_label = "Unknown"
        for (bit, label, cls) in all_mechanisms:
            if bit == current_mechanism_id:
                chosen_cls = cls
                chosen_label = label
                break

        # If none matched, default to round robin
        if not chosen_cls:
            chosen_cls = MechanismRoundRobinAllocation
            chosen_label = "Round Robin"
        
        return {
            "available_mechanisms": available_mechanisms,
            "current_mechanism_id": current_mechanism_id,
            "current_mechanism": chosen_label,
            "chosen_cls": chosen_cls,
            "chosen_label": chosen_label,
            "selected_alloc_res_tables_sum": question.alloc_res_tables
        }

    def _prepare_user_data(self, question):
        """Extract user responses and preferences"""
        response_set = question.response_set.all()
        current_user_id = self.request.user.id

        # Build map of user ids -> name/pic
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
        
        # Build a matrix of numeric valuations
        preferences = self._extract_numeric_preferences(
            response_set, 
            sorted_user_ids, 
            question.item_set.count()
        )
        
        return {
            "candidates": [user_names[uid] for uid in sorted_user_ids],
            "profile_pics": [user_pics[uid] for uid in sorted_user_ids],
            "user_names": user_names,
            "submitted_rankings": submitted_rankings,
            "sorted_user_ids": sorted_user_ids,
            "preferences": preferences,
            "current_user_id": current_user_id
        }

    def _extract_numeric_preferences(self, response_set, sorted_user_ids, item_count):
        """Extract numeric preference values from responses"""
        user_valuations_map = {}
        
        # Process each response
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
                for x in sublist:  # handle multiple items per tier
                    if isinstance(x, str):  # raw_list
                        name=x
                    elif isinstance(x, dict) and "name" in x:
                        name=x["name"]
                    if name:
                        val=item_score_map.get(name,0.0)
                    else:
                        try:
                            val = float(x[4:]) if isinstance(x, str) and x.startswith("item") else 0.0
                        except:
                            val = 0.0
                    numeric_vals.append(val)
            user_valuations_map[uid] = numeric_vals

        # Fix for empty preferences
        for uid in sorted_user_ids:
            if uid not in user_valuations_map or not user_valuations_map[uid]:
                user_valuations_map[uid] = [0.0] * item_count
        
        # Make sure all preference lists have the same length
        max_length = max([len(vals) for vals in user_valuations_map.values()]) if user_valuations_map else item_count
        for uid in user_valuations_map:
            if len(user_valuations_map[uid]) < max_length:
                user_valuations_map[uid] += [0.0] * (max_length - len(user_valuations_map[uid]))

        # Convert to a 2d list in user-id sorted order
        preferences = []
        for uid in sorted_user_ids:
            preferences.append(user_valuations_map.get(uid, [0.0] * max_length))
        
        return preferences

    def _process_allocation_result(self, result, preferences, sorted_user_ids, question_id):
        """Process allocation result into template context data"""
        # Extract allocation matrix
        allocation_matrix = result.A  # shape: (num_agents, num_items)
        
        # Get question and items
        question = Question.objects.get(id=question_id) if question_id else None
        items = list(question.item_set.all()) if question else []
        
        # Create basic allocation data
        allocation_data = {
            'allocation_matrix': allocation_matrix,
            'items_obj': items,
        }
        
        # Reconstruct allocated items
        allocated_items = []
        if allocation_matrix is not None:
            N = len(allocation_matrix)
            if N > 0:
                M = len(allocation_matrix[0])
                for i in range(N):
                    user_items = []
                    for j in range(M):
                        if allocation_matrix[i][j] == 1 and j < len(items):
                            # Store the actual Item object
                            user_items.append(items[j])
                        elif allocation_matrix[i][j] == 1:
                            # Fallback for items beyond the range
                            user_items.append({'item_text': f"Item #{j}", 'id': -1})
                    allocated_items.append(user_items)
        allocation_data['allocated_items'] = allocated_items
        
        # Calculate sum of values for each agent
        sum_values = []
        for i, prefs in enumerate(preferences):
            if i < len(allocation_matrix):
                utility = sum(prefs[j] * allocation_matrix[i][j] for j in range(len(prefs)))
                sum_values.append(utility)
        
        allocation_data['sum_of_alloc_items_values'] = sum_values
        
        return allocation_data

    def _get_allocation_result(self, context_data, mechanism_class, mechanism_label):
        """Get cached allocation or compute a new one"""
        # # Try to get from cache
        cached_result, is_hit = AllocationCache.get_cached_result(context_data)
        
        if is_hit:
            logger.info(f"Cache hit for mechanism {mechanism_label}")
            print(f"\n>>> CACHE HIT: Using cached result for {mechanism_label} <<<\n")
            # return cached_result, True
            # Process the cached data to ensure it's in the right format for the template
            processed_result = self._process_cached_allocation_data(cached_result)
            return processed_result, True
        
        # If not in cache, compute allocation
        logger.info(f"Cache miss for mechanism {mechanism_label}, computing allocation")
        print(f"\n>>> CACHE MISS: Computing new result for {mechanism_label} <<<\n")
        start_time = timezone.now()
        
        try:
            # Run the allocation mechanism
            mechanism = mechanism_class()
            result = mechanism.allocate(valuations=context_data['preferences'])
            
            # Process the allocation result
            allocation_data = self._process_allocation_result(
                result, 
                context_data['preferences'],
                context_data['sorted_user_ids'],
                context_data.get('question_id')
            )
            
            # Store in cache
            AllocationCache.store_result(context_data, allocation_data)
            
            # Log performance
            end_time = timezone.now()
            computation_time = (end_time - start_time).total_seconds()
            logger.info(f"Allocation computed in {computation_time:.2f}s for mechanism {mechanism_label}")
            print(f"Allocation computed in {computation_time:.2f}s for mechanism {mechanism_label}")
            
            return allocation_data, False
            
        except Exception as e:
            logger.error(f"Error computing allocation with {mechanism_label}: {str(e)}", exc_info=True)
            print(f"\n>>> ERROR computing allocation with {mechanism_label}: {str(e)} <<<\n")
            
            # Create fallback allocation
            n = len(context_data['preferences'])
            m = max([len(p) for p in context_data['preferences']]) if context_data['preferences'] else 0
            empty_matrix = np.zeros((n, m))
            
            # Return error data
            error_data = {
                'error_message': f"Could not compute allocation with {mechanism_label}: {str(e)}",
                'allocation_matrix': empty_matrix,
                'allocated_items': [[] for _ in range(n)],
                'sum_of_alloc_items_values': [0] * n
            }
            
            return error_data, False

    def _format_user_preferences(self, sorted_user_ids, user_names, submitted_rankings):
        """Format user preferences for display"""
        all_user_prefs = []
        for uid in sorted_user_ids:
            username = user_names[uid]
            ranking = submitted_rankings[uid]
            cleaned = []
            for group in ranking:
                if group and isinstance(group[0], dict):
                    item_name = group[0].get("name", "")[4:]
                    cleaned.append((item_name))
            all_user_prefs.append((username, cleaned))
        return all_user_prefs

    def _process_cached_allocation_data(self, cached_result, question_id=None):
        """Process cached allocation data to work with the template"""
        if not question_id:
            question_id = self.kwargs.get('pk')
            
        question = Question.objects.get(id=question_id)
        items = list(question.item_set.all())
        
        # Store items_obj reference
        cached_result['items_obj'] = items
        # Convert dictionary items back to Item objects
        if 'allocated_items' in cached_result:
            for i, agent_items in enumerate(cached_result['allocated_items']):
                for j, item_data in enumerate(agent_items):
                    if isinstance(item_data, dict) and 'id' in item_data and item_data['id'] > 0:
                        # Find matching item by ID
                        for item in items:
                            if item.id == item_data['id']:
                                cached_result['allocated_items'][i][j] = item
                                break
        
        return cached_result


class ConfirmationView(views.generic.DetailView):
    model = Question
    template_name = 'polls/confirmation.html'


class VoteResultsView(views.generic.DetailView):
    model = Question
    template_name = 'polls/vote_rule.html'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        print(f"\n[VoteResultsView] GET Request for Poll ID: {self.object.id}")
        if self.object.results_visible_after and timezone.now() < self.object.results_visible_after:
            print(f"  - Results not yet visible. Current time: {timezone.now()}, Visible after: {self.object.results_visible_after}")
            return redirect("polls:regular_polls")   #to /polls/regular_polls/
        return super().get(request, *args, **kwargs)
        
    def get_context_data(self, **kwargs):
        print(f"[VoteResultsView] get_context_data called for Poll: {self.object.question_text}")
        ctx = super(VoteResultsView, self).get_context_data(**kwargs)
        
        cand_map = getCandidateMapFromList(list(self.object.item_set.all()))
        ctx['cand_map'] = cand_map
        print(f"  - [get_context_data] cand_map: {cand_map}")

        response_count = list(self.object.response_set.all())
        print(f"  - Total responses found: {len(response_count)}")
        if len(response_count) == 0:
            return ctx
            
        if self.object.status != 4 and self.object.new_vote == True:
            print("  - [Recompute Trigger] new_vote flag is True. Calling getPollWinner...")
            getPollWinner(self.object)
            
        final_result = self.object.finalresult
        print(f"  - final_result timestamp: {final_result.timestamp if final_result else 'None'}")

        if self.object.mixtures_pl1 == "":
            print("  - [Recompute Trigger] Mixtures missing. Calling getPollWinner...")
            getPollWinner(self.object)
            
        if self.object.mixtures_pl1 != "":
            mixtures_pl1 = json.loads(self.object.mixtures_pl1)
            mixtures_pl2 = json.loads(self.object.mixtures_pl2)
            mixtures_pl3 = json.loads(self.object.mixtures_pl3)
            print(f"  - Mixtures loaded. pl1 size: {len(mixtures_pl1)}")
        else:
            mixtures_pl1 = [[]]
            mixtures_pl2 = []
            mixtures_pl3 = []
            print("  - No mixtures available.")

        print("  - [get_context_data] Calling interpretResult...")
        try:
            l = interpretResult(final_result)
        except Exception as e:
            print(f"  - [get_context_data] ERROR during interpretResult: {e}")
            traceback.print_exc()
            l = [[], [], [], [], []]
        
        poll_algorithms = []
        algorithm_links = []
        vote_results = []
        margin_victory = []
        shade_values = []

        start_poll_algorithms = getListPollAlgorithms()
        start_algorithm_links = getListAlgorithmLinks()
        to_show = self.object.vote_rule
        print(f"  - vote_rule bitmask: {to_show}")
        
        itr = 0
        poll_alg_num = self.object.poll_algorithm
        while to_show > 0:
            if to_show % 2 == 1:
                poll_algorithms.append(start_poll_algorithms[itr])
                algorithm_links.append(start_algorithm_links[itr])
                vote_results.append(l[0][itr])
                shade_values.append(l[2][itr])
                if itr < len(l[1]):
                    margin_victory.append(l[1][itr])
                to_show = to_show - 1
            elif itr < self.object.poll_algorithm - 1:
                poll_alg_num -= 1
            to_show = int(to_show / 2)
            itr += 1
            
        print(f"  - Algorithms to display: {poll_algorithms}")
        
        ctx['poll_algorithms'] = poll_algorithms
        ctx['poll_alg_num'] = poll_alg_num
        ctx['algorithm_links'] = algorithm_links
        ctx['vote_results'] = vote_results
        ctx['margin_victory'] = margin_victory
        ctx['shade_values'] = shade_values
        ctx['wmg_nodes'] = l[3]
        ctx['wmg_edges'] = l[4]
        ctx['time'] = final_result.timestamp
        ctx['margin_len'] = len(margin_victory)

        m = len(mixtures_pl1) - 1
        ctx['mixtures_pl1'] = mixtures_pl1
        ctx['mixtures_pl2'] = mixtures_pl2
        ctx['mixtures_pl3'] = mixtures_pl3
        
        # Get previous winners for the history table
        previous_results = self.object.voteresult_set.all()
        print(f"  - previous_results count: {len(previous_results)}")
        ctx['previous_winners'] = []
        for pw in previous_results:
            try:
                obj = {}
                obj['title'] = str(pw.timestamp.time())
                candnum = pw.cand_num
                resultstr = pw.result_string
                movstr = pw.mov_string
                if resultstr == "" and movstr == "":
                    continue
                resultlist = resultstr.split(",")
                movlist = movstr.split(",")
                tempResults = []
                algonum = len(getListPollAlgorithms())
                if len(resultlist) < candnum*algonum:
                    algonum = 7
                if len(resultlist) > 0:
                    for x in range(0, algonum):
                        tempList = []
                        for y in range(x*candnum, (x+1)*candnum):
                            tempList.append(resultlist[y])
                        tempResults.append(tempList)
                obj['vote_results'] = tempResults
                tempMargin = []
                for margin in movlist:
                    tempMargin.append(margin)
                obj['margin_victory'] = tempMargin
                ctx['previous_winners'].append(obj)
            except Exception as e:
                print(f"  - ERROR processing previous result {pw.id}: {e}")
                
        print("[VoteResultsView] get_context_data FINISHED successfully.")
        return ctx


def getListPollAlgorithms():
    return ["Plurality", "Borda", "Veto", "K-approval (k = 3)", "Simplified Bucklin",
            "Copeland", "Maximin","MaxiMin-Duplicate", "STV", "Baldwin", "Coombs", "Black", "Ranked Pairs",
            "Plurality With Runoff", "Borda Mean", "Simulated Approval"]


def getListAlgorithmLinks():
    return ["https://en.wikipedia.org/wiki/Plurality_voting_method",
            "https://en.wikipedia.org/wiki/Borda_count", "", "",
            "https://en.wikipedia.org/wiki/Bucklin_voting",
            "https://en.wikipedia.org/wiki/Copeland%27s_method",
            "https://en.wikipedia.org/wiki/Minimax_Condorcet",
            "https://en.wikipedia.org/wiki/Single_transferable_vote",
            "https://en.wikipedia.org/wiki/Nanson%27s_method#Baldwin_method",
            "https://en.wikipedia.org/wiki/Coombs%27_method","","","","",""]


def getAllocMethods():
    return [
        "Round Robin",
        "Maximum Nash Welfare",
        "Market",
        "MarketEq",
        "Leximin",
        "MNW Binary",
        "Market EQ1 PO",
    ]


def getViewPreferences():
    return [
        # "Everyone can see all votes at all times",
        "Everyone can see all preferences", 
        "Everyone can only see own preference",
        "Nothing"
            ]


def getViewUserInfo():
    return [
        "Only username of users will be shown",
        "Only numbers of users will be shown",
        "Nothing"
    ]


def getViewPreferencesForAllocation():
    return ["This is Duplicate view pref"]


def getWinnersFromIDList(idList):
    winners = {}
    for i in idList:
        try:
            q = Question.objects.get(pk=i)
            winners[i] = q.winner
        except Question.DoesNotExist:
            pass
    return winners


def parseWmg(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return ([], [])

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return ([], [])

    # make sure there's at least one response
    if len(latest_responses) == 0:
        return ([], [])

    # get nodes (the options)
    nodes = []
    for rowIndex in cand_map:
        data = {}
        data['id'] = rowIndex
        data['value'] = 1
        data['label'] = cand_map[rowIndex].item_text
        nodes.append(data)

    # get edges from the weighted majority graph
    wmg = pollProfile.getWmg()
    edges = []
    for rowIndex in wmg:
        row = wmg[rowIndex]
        for colIndex in row:
            value = row[colIndex]
            if value > 0:
                data = {}
                data['from'] = rowIndex
                data['to'] = colIndex
                data['value'] = value
                data['title'] = str(value)
                edges.append(data)

    return (nodes, edges)


def getSelectionList(responseList):
    selectList = []
    for response in responseList:
        selectList.append((response, getCurrentSelection(response)))
    return selectList


def categorizeResponses(all_responses):
    latest_responses = []
    previous_responses = []

    if len(all_responses) > 0:
        #the first response must be the most recent
        latest_responses.append(all_responses[0])

    others = all_responses[1:]

    #the outer loop goes through all the responses
    for response1 in others:
        #for anonymous users, check anonymous name instead of username
        if response1.user == None:
            add = True
            for response2 in latest_responses:
                if response1.anonymous_voter and response2.anonymous_voter:
                    if response1.anonymous_id == response2.anonymous_id:
                        add = False
                        previous_responses.append(response1)
                        break
            if add:
                latest_responses.append(response1)

        else:
            add = True
            #check if the user has voted multiple times
            for response2 in latest_responses:
                if not response2.user == None:
                    if response1.user.username == response2.user.username:
                        add = False
                        previous_responses.append(response1)
                        break

            #this is the most recent vote
            if add:
                latest_responses.append(response1)
    return (latest_responses, previous_responses)


def getCandidateMap(response):
    d = {}
    if response.dictionary_set.all().count() > 0:
        d = Dictionary.objects.get(response=response)
    else:
        d = buildResponseDict(response, response.question,
                                getPrefOrder(response.resp_str, response.question))
    d = interpretResponseDict(d)
    cand_map = {}

    counter = 0
    for item in d.items():
        cand_map[counter] = item[0]
        counter += 1
    return cand_map


def getCandidateMapFromList(candlist):
    cand_map = {}
    counter = 0
    for item in candlist:
        cand_map[counter] = item
        counter += 1
    return cand_map


def getPreferenceGraph(response, cand_map):
    pref_graph = {}
    dictionary = {}
    if response.dictionary_set.all().count() > 0:
        dictionary = Dictionary.objects.get(response=response)
    else:
        dictionary = buildResponseDict(response, response.question,
                                        getPrefOrder(response.resp_str, response.question))
    dictionary = interpretResponseDict(dictionary)
    for cand1Index in cand_map:
        tempDict = {}
        for cand2Index in cand_map:
            if cand1Index == cand2Index:
                continue

            cand1 = cand_map[cand1Index]
            cand2 = cand_map[cand2Index]
            cand1Rank = dictionary.get(cand1)
            cand2Rank = dictionary.get(cand2)
            #lower number is better (i.e. rank 1 is better than rank 2)
            if cand1Rank < cand2Rank:
                tempDict[cand2Index] = 1
            elif cand2Rank < cand1Rank:
                tempDict[cand2Index] = -1
            else:
                tempDict[cand2Index] = 0
        pref_graph[cand1Index] = tempDict

    return pref_graph


def getPollProfile(latest_responses, cand_map):
    if len(latest_responses) == 0:
        return None

    pref_list = []
    for response in latest_responses:
        pref_graph = getPreferenceGraph(response, cand_map)
        userPref = Preference(pref_graph)
        pref_list.append(userPref)
    return Profile(cand_map, pref_list)


def translateSingleWinner(winner, cand_map):
    result = {}
    if isinstance(winner, collections.Iterable):
        return translateWinnerList(winner,cand_map)
    for cand in cand_map.keys():
        if cand == winner:
            result[cand] = 1
        else:
            result[cand] = 0
    return result


def translateWinnerList(winners, cand_map):
    result = {}
    for cand in cand_map.keys():
        if cand in winners:
            result[cand] = 1
        else:
            result[cand] = 0
    return result


def translateBinaryWinnerList(winners, cand_map):
    result = {}
    if len(cand_map.keys()) != len(winners):
        return result
    for cand in cand_map.keys():
        if winners[cand] == 1:
            result[cand] = 1
        else:
            result[cand] = 0
    return result


def getVoteResults(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return []

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return []

    print(">>> Starting mechanism calculations... <<<")
    scoreVectorList = []
    print(">>> Calculating Plurality... <<<")
    scoreVectorList.append(MechanismPlurality().getCandScoresMap(pollProfile))
    print(">>> Calculating Borda... <<<")
    scoreVectorList.append(MechanismBorda().getCandScoresMap(pollProfile))
    print(">>> Calculating Veto... <<<")
    scoreVectorList.append(MechanismVeto().getCandScoresMap(pollProfile))
    print(">>> Calculating K-Approval... <<<")
    scoreVectorList.append(MechanismKApproval(3).getCandScoresMap(pollProfile))
    print(">>> Calculating Simplified Bucklin... <<<")
    scoreVectorList.append(MechanismSimplifiedBucklin().getCandScoresMap(pollProfile))
    print(">>> Calculating Copeland... <<<")
    scoreVectorList.append(MechanismCopeland(1).getCandScoresMap(pollProfile))
    print(">>> Calculating Maximin... <<<")
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    print(">>> Calculating Maximin (Duplicate)... <<<")
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))

    #STV, Baldwin, Coombs give list of integers as output
    print(">>> Calculating STV... <<<")
    stv = MechanismSTV().STVwinners(pollProfile)
    print(">>> Calculating Baldwin... <<<")
    baldwin = MechanismBaldwin().baldwin_winners(pollProfile)
    print(">>> Calculating Coombs... <<<")
    coombs = MechanismCoombs().coombs_winners(pollProfile)
    #print("test8")
    print(">>> Calculating Black... <<<")
    black = MechanismBlack().black_winner(pollProfile)
    #print("test7")
    print(">>> Calculating Ranked Pairs... <<<")
    ranked = MechanismRankedPairs().ranked_pairs_cowinners(pollProfile)
    print(">>> Calculating Plurality Runoff... <<<")
    pwro = MechanismPluralityRunOff().PluRunOff_cowinners(pollProfile)
    print(">>> Calculating Borda Mean... <<<")
    bordamean = MechanismBordaMean().Borda_mean_winners(pollProfile)
    print(">>> Calculating Simulated Approval... <<<")
    simapp, sim_scores = MechanismBordaMean().simulated_approval(pollProfile)
    # print("pwro=", pwro)
    #print("test6")
    print(">>> Translating winners... <<<")
    scoreVectorList.append(translateWinnerList(stv, cand_map))
    scoreVectorList.append(translateWinnerList(baldwin, cand_map))
    scoreVectorList.append(translateWinnerList(coombs, cand_map))
    scoreVectorList.append(translateWinnerList(black, cand_map))
    scoreVectorList.append(translateWinnerList(ranked, cand_map))
    scoreVectorList.append(translateWinnerList(pwro, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(bordamean, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(simapp, cand_map))

    #for Mixtures
    #print("test1")
    print(">>> Preparing for Mixtures... <<<")
    rankings = pollProfile.getOrderVectorsEGMM()
    m = len(rankings[0])
    #print("test2")
    print(">>> Calculating EGMM Mixtures (k=1)... <<<")
    mixtures_pl1 = egmm_mixpl(rankings, m, k=1, itr=10)[0].tolist()
    #print("test3")
    print(">>> Calculating EGMM Mixtures (k=2)... <<<")
    mixtures_pl2 = egmm_mixpl(rankings, m, k=2, itr=10).tolist()
    #print("test4")
    print(">>> Calculating EGMM Mixtures (k=3)... <<<")
    mixtures_pl3 = egmm_mixpl(rankings, m, k=3, itr=10).tolist()
    #print("test5")
    print(">>> All calculations finished! <<<")
    #gmm = GMMMixPLAggregator(list(pollProfile.cand_map.values()), use_matlab=False)

    return scoreVectorList, mixtures_pl1, mixtures_pl2, mixtures_pl3


def calculatePreviousResults(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.voteresult_set.clear()
    cand_map = getCandidateMapFromList(list(question.item_set.all()))
    previous_winners = question.oldwinner_set.all()
    for pw in previous_winners:

        result = VoteResult(question=question, timestamp=pw.response.timestamp,
                            result_string="", mov_string="",
                            cand_num=question.item_set.all().count())
        result.save()
        resultstr = ""
        movstr = ""
        responses = question.response_set.reverse()
        responses = responses.filter(timestamp__range=[datetime.date(1899, 12, 30),
                                    pw.response.timestamp], 
                                    active=1)
        (lr, pr) = categorizeResponses(responses)
        scorelist, mixtures_pl1, mixtures_pl2, mixtures_pl3 = getVoteResults(lr, cand_map)
        mov = getMarginOfVictory(lr, cand_map)
        for x in range(0, len(scorelist)):
            for key, value in scorelist[x].items():
                resultstr += str(value)
                resultstr += ","
        for x in range(0, len(mov)):
            movstr += str(mov[x])
            movstr += ","
        resultstr = resultstr[:-1]
        movstr = movstr[:-1]
        result.result_string = resultstr
        result.mov_string = movstr
        result.save()
    return HttpResponseRedirect(request.META.get('HTTP_REFERER'))


def getShadeValues(scoreVectorList):
    shadeValues = []

    for row in scoreVectorList:
        sortedRow = sorted(set(list(row.values())))
        highestRank = len(sortedRow) - 1

        newRow = []
        greenColor = "6cbf6c"
        whiteColor = "ffffff"
        for index in row:
            rank = sortedRow.index(row[index])

            if highestRank == 0:
                # must be the winner
                newRow.append("#" + greenColor)
                continue

            # make the colors closer to the left lighter (higher value) and toward the right
            #   darker (lower value)

            # the 5th row is Simplified Bucklin (lower score is better so reverse the colorings
            #   for this row)
            counter = len(shadeValues)
            if counter != 4:
                luminance = 1 - rank / float(highestRank)
            else:
                luminance = rank / float(highestRank)

            # set lowest rank to white
            if luminance == 1:
                newRow.append("#" + whiteColor)
                continue
            if luminance <= 0.5:
                luminance /= 2.0

            newRow.append(colorLuminance(greenColor, luminance))

        shadeValues.append(newRow)
    return shadeValues


def getMarginOfVictory(latest_responses, cand_map):
    print("    [getMarginOfVictory] Starting...")
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        print("    [getMarginOfVictory] pollProfile is None")
        return []

    #make sure no incomplete results are in the votes
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        print(f"    [getMarginOfVictory] Unsupported ElecType: {pollProfile.getElecType()}")
        return []
        
    marginList = []
    for x in range(0,len(getListPollAlgorithms())):
        marginList.append(-1)
        
    print("    [getMarginOfVictory] Calculating margins...")
    try:
        print("      - Plurality MoV...")
        marginList[0] = MechanismPlurality().getMov(pollProfile)
        print("      - Borda MoV...")
        marginList[1] = MechanismBorda().getMov(pollProfile)
        print("      - Veto MoV...")
        marginList[2] = MechanismVeto().getMov(pollProfile)
        print("      - K-Approval MoV...")
        marginList[3] = MechanismKApproval(3).getMov(pollProfile)
        print("      - Simplified Bucklin MoV...")
        marginList[4] = MechanismSimplifiedBucklin().getMov(pollProfile)
        #marginList[12] = MechanismPluralityRunOff().getMov(pollProfile)
        print("    [getMarginOfVictory] Calculations complete.")
    except Exception as e:
        print(f"    [getMarginOfVictory] ERROR during MoV calculation: {e}")
        traceback.print_exc()

    return marginList


def getKTScore(user, otherUser):
    kendall_tau = 0
    num = 0
    questions = Question.objects.all().filter(question_voters=otherUser).filter(question_voters=user)
    for q in questions:
        userResponse = q.response_set.filter(user=user).reverse()
        other_user_response = q.response_set.filter(user=otherUser).reverse()
        if len(userResponse) > 0 and len(other_user_response) > 0:
            num = num + 1
            userResponse = get_object_or_404(Dictionary, response=userResponse[0])
            other_user_response = get_object_or_404(Dictionary, response=other_user_response[0])
            kendall_tau += getKendallTauScore(userResponse, other_user_response)

    if num != 0:
        kendall_tau /= num
    if kendall_tau == 0:
        kendall_tau = .25
    else:
        kendall_tau = 1/(1 + kendall_tau)
    return kendall_tau


def getRecommendedOrder(other_user_responses, request, default_order):
    # no responses
    if len(other_user_responses) == 0:
        return default_order

    # if the poll owner added more choices during the poll, then reset using the default order
    itemsLastResponse = len(getCandidateMap(other_user_responses[0]))
    itemsCurrent = default_order.count()
    if itemsLastResponse != itemsCurrent:
        return default_order

    # iterate through all the responses
    preferences = []
    for resp in other_user_responses:
        user = request.user
        otherUser = resp.user

        # get current user and other user preferences
        KT = getKTScore(user, otherUser)
        pref_graph = getPreferenceGraph(resp, cand_map)
        preferences.append(Preference(pref_graph, KT))

    cand_map = getCandidateMap(other_user_responses[0])
    pollProfile = Profile(cand_map, preferences)

    # incomplete answers
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return default_order

    # return the order based off of ranking
    pref = MechanismBorda().getCandScoresMap(pollProfile)
    l = list(sorted(pref.items(), key=lambda kv: (kv[1], kv[0])))
    final_list = []
    for p in reversed(l):
        final_list.append(cand_map[p[0]])
    return final_list


class AllocationOrder(views.generic.DetailView):
    model = Question
    template_name = 'polls/allocation_order.html'
    def get_context_data(self, **kwargs):
        ctx = super(AllocationOrder, self).get_context_data(**kwargs)
        currentAllocationOrder = self.object.allocationvoter_set.all()
        tempOrderStr = self.request.GET.get('order', '')
        if tempOrderStr == "null":
            ctx['question_voters'] = self.object.question_voters.all()
            return ctx

        # check if the user submitted a vote earlier and display that for modification
        if len(currentAllocationOrder) > 0:
            ctx['currentSelection'] = currentAllocationOrder

        ctx['question_voters'] = self.object.question_voters.all()
        return ctx
    def get_queryset(self):
        """
        Excludes any questions that aren't published yet.
        """
        return Question.objects.filter(pub_date__lte=timezone.now())


def setAllocationOrder(request, question_id):
    question = get_object_or_404(Question, pk=question_id)

    # get the voter order
    orderStr = request.POST["pref_order"]
    prefOrder = getPrefOrder(orderStr, question)
    if orderStr == "":
        # the user must rank all voters
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    prefOrder = orderStr.split(",")
    if len(prefOrder) != len(question.question_voters.all()):
        # the user must rank all voters
        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))

    #reset allocation order
    for voter in question.allocationvoter_set.all():
        voter.delete()

    # find ranking student gave for each item under the question
    item_num = 1
    for item in question.question_voters.all():
        arrayIndex = prefOrder.index("item" + str(item_num))
        if arrayIndex != -1:
            user = question.question_voters.all()[arrayIndex]
            # add pref to list
            voter, created = AllocationVoter.objects.get_or_create(question=question,
                                                                   user=user, response=None)
            voter.save()

        item_num += 1

    return HttpResponseRedirect(reverse('polls:viewAllocationOrder', args=(question.id,)))
