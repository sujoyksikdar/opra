from .allocation_utils import *

import operator
import random
from gurobipy import Model, GRB, quicksum
from collections import deque

# *----------------------------------------- Allocation Algorithms -----------------------------------------*
import math
import numpy as np
import networkx as nx
from copy import deepcopy
from gurobipy import Model, GRB, quicksum

# ALLOCATION ALGORITHM FUNCTIONS HERE:
def allocation(pollAlgorithm, itemList, responseList):
    #make sure there is at least one response  
    if len(responseList) == 0:
        return

    if pollAlgorithm == 1:
        #SD early first
        return allocation_serial_dictatorship(itemList, responseList, early_first = 1)
    elif pollAlgorithm == 2:
        #SD late first
        return allocation_serial_dictatorship(itemList, list(reversed(responseList)), early_first = 0)
    elif pollAlgorithm == 3:
        return allocation_manual(itemList, responseList)

# iterate through each response and assign the highest ranking choice that is still available 
# List<String> items
# List<(String, Dict<String, int>)> responses is a list of tuples, where the first entry is the user and the second
#     entry is the dictionary. Each dictionary item maps to a rank (integer) 
# return Dict<String, String> allocationResults which maps users to items
def getAllocationResults(items, responses):
    allocationResults = {}
    for response in responses:
        # no more items left to allocate
        if len(items) == 0:
            return
        
        highestRank = len(items)
        myitem = items[0]

        # here we find the item remaining that this user ranked the highest
        username = response[0]
        preferences = response[1]
        for item in items:
            if preferences.get(item) < highestRank:
                highestRank = preferences.get(item)
                myitem = item

        print ("Allocating item " + myitem + " to user " + username)
        # assign item
        allocationResults[username] = myitem
        # remove the item from consideration for other students
        items.remove(myitem)                
    return allocationResults

# Serial dictatorship algorithm to allocate items to students for a given question.
# It takes as an argument the response set to run the algorithm on.
# The order of the serial dictatorship will be decided by increasing
# order of the timestamps on the responses for novel questions, and reverse
# order of the timestamps on the original question for follow-up questions.
def allocation_serial_dictatorship(itemList, responseList, early_first = 1):
    return getAllocationResults(itemList, responseList)

# the poll owner can specify an order to allocate choices to voters
def allocation_manual(itemList, responseList):
    return getAllocationResults(itemList, responseList)

class AllocationResult:
    """
    container for holding the results of allocations.
    """
    def __init__(self, status, A, U=None, w=None, prices=None):
        self.status = status
        self.A = A
        self.U = U
        self.w = w
        self.prices = prices


class MechanismAllocation:
    """
    parent class for all resource-allocation mechanisms in opra.
    """

    def allocate(self, valuations, **kwargs):
        """
        returns an allocation for the given valuations.
        must be overridden by child classes.
        """
        raise NotImplementedError("subclasses must override allocate().")


class MechanismRoundRobinAllocation(MechanismAllocation):
    """Round-robin allocation: each agent picks its top remaining item in turn."""

    def allocate(self, valuations, **kwargs):
        """
        Returns an AllocationResult with:
         - status=True
         - A: binary matrix
         - allocated_items: list of agent picks
         - U, w, prices: None (unused here)
        """
        
        # round robin allocation
        allocation_matrix = round_robin(valuations)
        
        return AllocationResult(
            status=True,
            A=allocation_matrix,
        )


class MechanismMaximumNashWelfare(MechanismAllocation):
    """
    implements maximum nash welfare using a solver pipeline.
    """

    def allocate(self, valuations, **kwargs):
        """
        returns an AllocationResult with:
         - status: True/False from the solver
         - A: final n x m binary allocation matrix
         - U: list of utilities for each agent
         - w: nash product
        """
        B_DEFAULT = 1000
        
        # convert valuations to a float numpy array
        V = np.array(valuations, dtype=float)

        # optional parameter b from kwargs (if used in the solver)
        B = kwargs.get("B", B_DEFAULT)
        # B = kwargs.get("B", config.B)

        # 1) restrict to columns with positive total value
        Vval, valued = get_valued_instance(V)

        # 2) restrict via a maximum-cardinality matching (hall's instance)
        Vhalls, matched = get_halls_instance(Vval)

        # 3) run the gurobi-based mnw solver on the reduced matrix
        status, w, U, A_halls = mnw_solve(Vhalls)

        # 4) recover the solution from the reduced instance
        A_hat = recover_from_halls(A_halls, Vval, matched)
        A = recover_from_valued(A_hat, V, valued)

        # return the result
        return AllocationResult(
            status=status,
            A=A,
            U=U,
            w=w
        )



# Aims to find an EF1 + PO (envy-free up to 1 item + Pareto optimal) allocation using a three-phase iterative price-adjustment algorithm
class MechanismMarketAllocation(MechanismAllocation):
    """
    implements a market-based ef1 + po allocation mechanism
      1) restrict to valued columns,
      2) further restrict via halls instance,
      3) solve the reduced problem with market_solve,
      4) recover full solution.
    """

    def allocate(self, valuations, **kwargs):
        V = np.array(valuations, dtype=float)
        
        # 1) restrict to columns with positive total value
        Vval, valued = get_valued_instance(V)
        
        # 2) restrict via a maximum-cardinality matching (hall's instance)
        Vhalls, matched = get_halls_instance(Vval)
        
        # 3) solve the reduced problem with market_solve
        status, X_halls, prices = market_solve(Vhalls)
        
        # 4) recover the full solution
        X_hat = recover_from_halls(X_halls, Vval, matched)
        
        # 5) recover the full solution
        A = recover_from_valued(X_hat, V, valued)
        
        # return the result
        return AllocationResult(
            status=status,
            A=A,
            prices=prices
        )


class MechanismLeximinAllocation(MechanismAllocation):
    """
    implements a leximin allocation using an ilp pipeline.
    """

    def allocate(self, valuations, **kwargs):
        V = np.array(valuations, dtype=float)
        B = kwargs.get("B", 1000)
        chores = kwargs.get("chores", False)
        
        # 1) restrict to columns with positive total value
        Vval, valued = get_valued_instance(V)
        
        # 2) restrict via a maximum-cardinality matching (hall's instance)
        Vhalls, matched = get_halls_instance(Vval)
        
        # 3) solve the reduced problem with leximin_solve
        status, sw, U, A_halls = leximin_solve(Vhalls, B=B, chores=chores)
        
        # 4) recover the solution from the reduced instance
        A_hat = recover_from_halls(A_halls, Vval, matched)
        
        # 5) recover the full solution
        A = recover_from_valued(A_hat, V, valued)
        
        # return the result
        return AllocationResult(
            status=status,
            A=A,
            U=U,
            w=sw
        )


#Aims for an EQ1 (or a similarly equitable) + PO style of outcome, based on a similar idea of iterative price adjustments, but with conditions ensuring equity (or a variant called "equitability-up-to-one-item"

class MechanismMarketEqAllocation(MechanismAllocation):
    """
    implements a market-based eq1 + po (or similar) allocation mechanism.
    uses the pipeline:
      1) restrict to valued columns,
      2) restrict via halls,
      3) call market_eq_solve on the reduced instance,
      4) recover the full solution.
    """

    def allocate(self, valuations, **kwargs):
        V = np.array(valuations, dtype=float)
        
        # 1) restrict to columns with positive total value  
        Vval, valued = get_valued_instance(V)
        
        # 2) restrict via a maximum-cardinality matching (hall's instance)
        Vhalls, matched = get_halls_instance(Vval)
        
        # 3) call market_eq_solve on the reduced instance
        status, X_halls, prices = market_eq_solve(Vhalls)
        
        # 4) recover the full solution
        X_hat = recover_from_halls(X_halls, Vval, matched)
        
        # 5) recover the full solution  
        A = recover_from_valued(X_hat, V, valued)
        
        # return the result
        return AllocationResult(
            status=status,
            A=A,
            prices=prices
        )

class MechanismMaximumNashWelfareBinary(MechanismAllocation):
    """
    implements the 'mnw_binary' approach from fairdivision, which iteratively
    improves an allocation for binary valuations via swaps.
    it uses the standard pipeline:
      1) restrict to valued columns,
      2) restrict via halls instance,
      3) run mnw_binary on the reduced matrix,
      4) recover to the original instance.
    """

    def allocate(self, valuations, **kwargs):
        V = np.array(valuations, dtype=float)
        
        # 1) restrict to columns with positive total value
        Vval, valued = get_valued_instance(V)
        
        # 2) restrict via a maximum-cardinality matching (hall's instance)
        Vhalls, matched = get_halls_instance(Vval)
        
        # 3) run solve_mnw_binary on the reduced matrix
        A_halls = solve_mnw_binary(Vhalls)
        
        # 4) recover to the original instance
        A_hat = recover_from_halls(A_halls, Vval, matched)
        A = recover_from_valued(A_hat, V, valued)
        
        # 5) compute the nash product and utilities
        w, U = nw(V, A)
        
        # return the result
        status = True
        return AllocationResult(status=status, A=A, U=U, w=w)