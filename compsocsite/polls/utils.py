import ast
import collections
import datetime
import itertools
import json
import logging
import random
import traceback
import numpy as np

from django.utils import timezone
from django.shortcuts import get_object_or_404
from prefpy.mechanism import *
from prefpy.gmm_mixpl import *
from prefpy.egmm_mixpl import *

from appauth.models import *
from groups.models import *
from multipolls.models import *
from .models import *


def colorLuminance(hexVal, lum):
    #convert to decimal and change luminosity
    rgb = "#"
    for i in range(0, 3):
        c = int(hexVal[i * 2 : i * 2 + 2], 16)
        c = round(min(max(0, c + (c * float(lum))), 255))
        c = hex(int(c))
        rgb += ("00" + str(c))[len(str(c)):]
    return rgb

def getPrefOrder(orderStr, question):
    # empty string
    if orderStr == "" or orderStr is None:
        return None
    if ";;|;;" in orderStr:
        current_array = orderStr.split(";;|;;")
        final_order = []
        length = 0
        for item in current_array:
            if item != "":
                curr = item.split(";;")
                final_order.append(curr)
                length += len(curr)
    else:
        final_order = json.loads(orderStr)
    
    return final_order


def buildResponseDict(response, question, prefOrder):
    d = {}
    if prefOrder is None:
        return d
    
    # find ranking user gave for each item under the question
    for item in question.item_set.all():
        rank = 1
        flag = True
        for l in prefOrder:
            string = "item" + str(item)
            if l[0].get("name") == string:
                d[item] = rank
                flag = False
                break
            rank += 1
        if flag:
            d[item] = 1000
    return d


def interpretResponseDict(dict_obj):
    max_val = -1
    for k, v in dict_obj.items():
        if v > max_val and v != 1000:
            max_val = v
    for k, v in dict_obj.items():
        if v == 1000:
            dict_obj[k] = max_val + 1
    return dict_obj


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
        (nodes, edges) = parseWmg(latest_responses, cand_map)
        shadevalues = getShadeValues(vote_results)
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


def isPrefReset(request):
    """Reset order in two-column UI. No longer used."""
    orderStr = request.GET.get('order', '')
    if orderStr == "null":
        return True
    return False


def getCurrentSelection(mostRecentResponse):
    """
    Given a response, return current ranking data that can be loaded on voting UIs.
    """
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


def addPreferenceValueToResp(objs):
    for i in range(len(objs)):
        response, prefOrder = objs[i]
        behavior_data = json.loads(response.behavior_data)
        submitted_rankings = behavior_data.get("submitted_ranking", [])
        scores = set()
        for tier in submitted_rankings:
            for jsonObj in tier:
                if isinstance(jsonObj, dict) and "score" in jsonObj:
                    scores.add(jsonObj["score"])
        scores = sorted(list(scores))[-1::-1] if scores else []
        for i in range(len(scores) if len(scores) < len(prefOrder) else len(prefOrder)):
            prefOrder[i].insert(0, scores[i])
    return objs


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
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return ([], [])
    if len(latest_responses) == 0:
        return ([], [])
    nodes = []
    for rowIndex in cand_map:
        data = {}
        data['id'] = rowIndex
        data['value'] = 1
        data['label'] = cand_map[rowIndex].item_text
        nodes.append(data)
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
        latest_responses.append(all_responses[0])
    others = all_responses[1:]
    for response1 in others:
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
            for response2 in latest_responses:
                if not response2.user == None:
                    if response1.user.username == response2.user.username:
                        add = False
                        previous_responses.append(response1)
                        break
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
    if isinstance(winner, collections.abc.Iterable if hasattr(collections, 'abc') else collections.Iterable):
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
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return []
    scoreVectorList = []
    scoreVectorList.append(MechanismPlurality().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismBorda().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismVeto().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismKApproval(3).getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismSimplifiedBucklin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismCopeland(1).getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    scoreVectorList.append(MechanismMaximin().getCandScoresMap(pollProfile))
    stv = MechanismSTV().STVwinners(pollProfile)
    baldwin = MechanismBaldwin().baldwin_winners(pollProfile)
    coombs = MechanismCoombs().coombs_winners(pollProfile)
    black = MechanismBlack().black_winner(pollProfile)
    ranked = MechanismRankedPairs().ranked_pairs_cowinners(pollProfile)
    pwro = MechanismPluralityRunOff().PluRunOff_cowinners(pollProfile)
    bordamean = MechanismBordaMean().Borda_mean_winners(pollProfile)
    simapp, sim_scores = MechanismBordaMean().simulated_approval(pollProfile)
    scoreVectorList.append(translateWinnerList(stv, cand_map))
    scoreVectorList.append(translateWinnerList(baldwin, cand_map))
    scoreVectorList.append(translateWinnerList(coombs, cand_map))
    scoreVectorList.append(translateWinnerList(black, cand_map))
    scoreVectorList.append(translateWinnerList(ranked, cand_map))
    scoreVectorList.append(translateWinnerList(pwro, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(bordamean, cand_map))
    scoreVectorList.append(translateBinaryWinnerList(simapp, cand_map))
    rankings = pollProfile.getOrderVectorsEGMM()
    m = len(rankings[0])
    mixtures_pl1 = egmm_mixpl(rankings, m, k=1, itr=10)[0].tolist()
    mixtures_pl2 = egmm_mixpl(rankings, m, k=2, itr=10).tolist()
    mixtures_pl3 = egmm_mixpl(rankings, m, k=3, itr=10).tolist()
    return scoreVectorList, mixtures_pl1, mixtures_pl2, mixtures_pl3


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
                newRow.append("#" + greenColor)
                continue
            counter = len(shadeValues)
            if counter != 4:
                luminance = 1 - rank / float(highestRank)
            else:
                luminance = rank / float(highestRank)
            if luminance == 1:
                newRow.append("#" + whiteColor)
                continue
            if luminance <= 0.5:
                luminance /= 2.0
            newRow.append(colorLuminance(greenColor, luminance))
        shadeValues.append(newRow)
    return shadeValues


def getMarginOfVictory(latest_responses, cand_map):
    pollProfile = getPollProfile(latest_responses, cand_map)
    if pollProfile == None:
        return []
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return []
    marginList = []
    for x in range(0,len(getListPollAlgorithms())):
        marginList.append(-1)
    try:
        marginList[0] = MechanismPlurality().getMov(pollProfile)
        marginList[1] = MechanismBorda().getMov(pollProfile)
        marginList[2] = MechanismVeto().getMov(pollProfile)
        marginList[3] = MechanismKApproval(3).getMov(pollProfile)
        marginList[4] = MechanismSimplifiedBucklin().getMov(pollProfile)
    except Exception as e:
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
    if len(other_user_responses) == 0:
        return default_order
    cand_map = getCandidateMap(other_user_responses[0])
    itemsLastResponse = len(cand_map)
    itemsCurrent = default_order.count()
    if itemsLastResponse != itemsCurrent:
        return default_order
    preferences = []
    for resp in other_user_responses:
        user = request.user
        otherUser = resp.user
        KT = getKTScore(user, otherUser)
        pref_graph = getPreferenceGraph(resp, cand_map)
        preferences.append(Preference(pref_graph, KT))
    pollProfile = Profile(cand_map, preferences)
    if pollProfile.getElecType() != "soc" and pollProfile.getElecType() != "toc":
        return default_order
    pref = MechanismBorda().getCandScoresMap(pollProfile)
    l = list(sorted(pref.items(), key=lambda kv: (kv[1], kv[0])))
    final_list = []
    for p in reversed(l):
        final_list.append(cand_map[p[0]])
    return final_list


def getInitialAllocationOrder(question, latest_responses):
    if len(latest_responses) == 0:
        return
    counter = len(question.item_set.all())
    for user_response in list(reversed(latest_responses)):
        if counter == 0:
            return
        counter -= 1
        voter, created = AllocationVoter.objects.get_or_create(question=user_response.question, user=user_response.user)
        voter.response = user_response
        voter.save()
    return


def getCurrentAllocationOrder(question, latest_responses):
    allocation_order = []
    if question.m_poll == True:
        multipoll = question.multipoll_set.all()[0]
        firstSubpoll = multipoll.questions.all()[0]
        allocation_order = firstSubpoll.allocationvoter_set.all()
        if len(allocation_order) == 0:
            getInitialAllocationOrder(question, latest_responses)
        else:
            for alloc_item in allocation_order:
                voter, created = AllocationVoter.objects.get_or_create(question=question, user=alloc_item.user)
                voter.response = question.response_set.reverse().filter(user=alloc_item.user)[0]
                voter.save()
        allocation_order = question.allocationvoter_set.all()
    else:
        allocation_order = question.allocationvoter_set.all()
        if len(allocation_order) == 0 or len(allocation_order) != len(latest_responses):
            getInitialAllocationOrder(question, latest_responses)
            allocation_order = question.allocationvoter_set.all()
    return allocation_order


def getResponseOrder(allocation_order):
    response_set = []
    for order_item in allocation_order:
        question = order_item.question
        user = order_item.user
        if question.response_set.reverse().filter(user=user, active=1).count() == 0:
            continue
        response = question.response_set.reverse().filter(user=user, active=1)[0]
        order_item.response = response
        order_item.save()
        response_set.append(response)
    return response_set


def assignAllocation(question, allocationResults):
    for username, item in allocationResults.items():
        currentUser = User.objects.filter(username=username).first()
        allocatedItem = question.item_set.get(item_text=item)
        mostRecentResponse = question.response_set.reverse().filter(user=currentUser, active=1)[0]
        mostRecentResponse.allocation = allocatedItem
        mostRecentResponse.save()
    return


def getFinalAllocation(question):
    response_set = question.response_set.filter(active=1).order_by('-timestamp')
    (latest_responses, previous_responses) = categorizeResponses(response_set)
    if len(latest_responses) == 0:
        return
    allocation_order = getCurrentAllocationOrder(question, latest_responses)
    response_set = getResponseOrder(allocation_order)
    item_set = latest_responses[0].question.item_set.all()
    itemList = []
    for item in item_set:
        itemList.append(item.item_text)
    responseList = []
    for response in response_set:
        tempDict = {}
        dictionary = {}
        if response.dictionary_set.all().count() > 0:
            dictionary = Dictionary.objects.get(response=response)
        else:
            dictionary = buildResponseDict(response, response.question,
                                            getPrefOrder(response.resp_str,
                                            response.question))
        dictionary = interpretResponseDict(dictionary)
        for item, rank in dictionary.items():
            tempDict[item.item_text] = rank
        responseList.append((response.user.username, tempDict))
    allocationResults = allocation(question.poll_algorithm, itemList, responseList)
    assignAllocation(question, allocationResults)