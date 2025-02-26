import numpy as np
import networkx as nx
from copy import deepcopy
from gurobipy import Model, GRB, quicksum

def round_robin(V, items=None):
    """
    performs a round-robin allocation.
    each agent picks its top item in turn until none remain.

    returns (allocated_items, allocation_matrix).
    """
    V = np.array(V, dtype=object)
    n, m = V.shape

    # if items not given, assume V[0] is item labels
    if items is None:
        items = V[0]

    remaining = np.array(items, dtype=object)
    allocated_items = [[] for _ in range(n)]
    agent_idx = 0

    # pick items in a cycle
    while remaining.size > 0:
        top_item = V[agent_idx][0]
        allocated_items[agent_idx].append(top_item)

        # remove chosen item
        remaining = np.delete(remaining, np.where(remaining == top_item))
        new_vals = np.empty((n, remaining.size), dtype=object)
        for j in range(n):
            new_vals[j] = np.delete(V[j], np.where(V[j] == top_item))
        V = new_vals

        agent_idx = (agent_idx + 1) % n

    # build binary allocation matrix
    allocation_matrix = [[0]*m for _ in range(n)]
    for j in range(n):
        for item in allocated_items[j]:
            col_idx = np.where(items == item)[0][0]
            allocation_matrix[j][col_idx] = 1

    return allocated_items, allocation_matrix


def get_valued_instance(V):
    """
    restricts columns to those with positive total value.
    returns (Vprime, valued_indices).
    """
    n, m = V.shape
    valued = [i for i in range(m) if np.sum(V[:, i]) > 0]
    Vprime = V[:, valued]
    return Vprime, valued


def nw(V, A):
    """
    computes nash welfare = product of agent utilities.
    returns (nw_value, utilities_list).
    """
    n, m = V.shape
    U = []
    for j in range(n):
        U.append(np.dot(V[j, :], A[j, :]))

    if all(u == 0 for u in U):
        return 0, U

    # product of positive utilities only
    prod_val = 1
    for u in U:
        if u > 0:
            prod_val *= float(u)

    return prod_val, U


def mnw_solve(V):
    """
    gurobi-based solver for maximum nash welfare.
    returns (status, w, U, A).
    """
    n, m = V.shape
    model = Model('mnw')
    model.setParam('OutputFlag', 0)

    xvars = {}
    for j in range(n):
        for i in range(m):
            xvars[j, i] = model.addVar(vtype=GRB.BINARY, name=f"x_{j}_{i}")

    wvars = {}
    for j in range(n):
        wvars[j] = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name=f"w_{j}")

    # each item assigned exactly once
    for i in range(m):
        model.addConstr(quicksum(xvars[j, i] for j in range(n)) == 1)

    # force each agent to get at least 1 total unit
    for j in range(n):
        model.addConstr(1 <= quicksum(V[j, i] * xvars[j, i] for i in range(m)))

    # approximate log-based constraints
    for j in range(n):
        for k in range(1, config.B):
            model.addConstr(
                wvars[j] <= np.log(k)
                + (np.log(k+1) - np.log(k))
                * (quicksum(V[j, i] * xvars[j, i] for i in range(m)) - k)
            )

    model.setObjective(quicksum(wvars[j] for j in range(n)), GRB.MAXIMIZE)
    model.optimize()

    status = (model.Status == GRB.OPTIMAL)
    A = np.zeros((n, m), dtype=int)

    for j in range(n):
        for i in range(m):
            A[j, i] = int(round(xvars[j, i].X))

    w, U = nw(V, A)
    return status, w, U, A


def construct_alloc_graph(V, A):
    """
    constructs a directed graph where edge (j->k) if j's row has a 1
    in the same place as k's allocation.
    returns (graph, edge_labels).
    """
    n, m = V.shape
    G = nx.DiGraph()
    G.add_nodes_from(range(n))
    edge_labels = {}

    for j in range(n):
        for k in range(n):
            if j == k:
                continue
            for i in range(m):
                if V[j, i] == 1 and A[k, i] == 1:
                    G.add_edge(j, k)
                    edge_labels[(j, k)] = i
                    break
    return G, edge_labels


def max_match_allocation(V):
    """
    finds an allocation by maximum bipartite matching on top agents/items.
    returns an n x m binary matrix.
    """
    n, m = V.shape
    G = nx.Graph()
    agent_nodes = [('a', j) for j in range(n)]
    G.add_nodes_from(agent_nodes, bipartite=0)
    item_nodes = [('g', i) for i in range(m)]
    G.add_nodes_from(item_nodes, bipartite=1)

    edges = []
    for j in range(n):
        for i in range(m):
            if V[j, i] == np.max(V[:, i]):
                edges.append((('a', j), ('g', i)))
    G.add_edges_from(edges)

    top_nodes = {node for node, d in G.nodes(data=True) if d['bipartite'] == 0}
    M = nx.bipartite.maximum_matching(G, top_nodes=top_nodes)
    A = np.zeros((n, m), dtype=int)

    for match in M:
        if match[0][0] == 'a':
            j = match[0][1]
            i = M[match][1]
            A[j, i] = 1

    # fill unallocated items greedily
    for i in range(m):
        if np.sum(A[:, i]) == 0:
            j = np.argmax(V[:, i])
            A[j, i] = 1
    return A


def get_halls_instance(V):
    """
    restricts to rows that get matched in a max-card allocation.
    returns (Vprime, matched_row_indices).
    """
    A = max_cardinality_allocation(V)
    matched = [j for j in range(V.shape[0]) if np.sum(A[j, :]) > 0]
    Vprime = V[matched, :]
    return Vprime, matched


def recover_from_halls(Xprime, V, matched):
    """
    rebuilds the solution from matched subset back to all agents.
    returns a full n x m matrix.
    """
    n, m = V.shape
    X = np.zeros((n, m), dtype=int)
    for idx, j in enumerate(matched):
        X[j, :] = Xprime[idx, :]
    return X


def recover_from_valued(Xprime, V, valued):
    """
    rebuilds solution from valued columns to original columns.
    returns an n x m matrix.
    """
    n, m = V.shape
    X = np.zeros((n, m), dtype=int)
    for col_idx, real_col in enumerate(valued):
        X[:, real_col] = Xprime[:, col_idx]
    for i in range(m):
        if i not in valued:
            X[0, i] = 1
    return X


def max_cardinality_allocation(V):
    """
    bipartite matching for all items with positive values.
    returns an n x m binary matrix.
    """
    n, m = V.shape
    G = nx.Graph()
    agent_nodes = [('a', j) for j in range(n)]
    G.add_nodes_from(agent_nodes, bipartite=0)
    item_nodes = [('g', i) for i in range(m)]
    G.add_nodes_from(item_nodes, bipartite=1)

    edges = []
    for j in range(n):
        for i in range(m):
            if V[j, i] > 0:
                edges.append((('a', j), ('g', i)))
    G.add_edges_from(edges)

    top_nodes = {node for node, d in G.nodes(data=True) if d['bipartite'] == 0}
    M = nx.bipartite.maximum_matching(G, top_nodes=top_nodes)
    A = np.zeros((n, m), dtype=int)

    for match in M:
        if match[0][0] == 'a':
            j = match[0][1]
            i = M[match][1]
            A[j, i] = 1

    # fill any unallocated items greedily
    for i in range(m):
        if np.sum(A[:, i]) == 0:
            j = np.argmax(V[:, i])
            A[j, i] = 1
    return A


def mat2set(A):
    """
    converts an n x m binary matrix into a dict of sets: agent -> set of item indices.
    """
    alloc = {}
    for i, row in enumerate(A):
        alloc[i] = np.nonzero(row)[0]
    return alloc


def compute_utilities(V, A):
    """
    builds an n x n matrix of utilities, where U[j,k] is agent j's utility for agent k's bundle.
    """
    n, m = V.shape
    U = np.zeros((n, n))
    for j in range(n):
        for k in range(n):
            U[j, k] = np.dot(V[j, :], A[k, :])
    return U



# ---------------------------------- Market helpers ----------------------------------

import numpy as np
import networkx as nx
from copy import deepcopy
from gurobipy import GRB

def round_instance(V):
    """
    rounds valuations for numeric stability.
    returns (Vprime, eps).
    """
    (n, m) = V.shape
    vmax = np.max(V)
    eps = 1.0 / (6.0 * (m**3) * vmax)
    Vprime = np.zeros((n, m))
    for j in range(n):
        for i in range(m):
            if V[j, i] > 0:
                Vprime[j, i] = (1 + eps) ** np.ceil(np.log(V[j, i]) / np.log(1 + eps))
    return Vprime, eps

def is3epef1(X, prices, eps):
    """
    checks if X is 3*eps-ef1 w.r.t. prices.
    returns True/False.
    """
    (n, m) = X.shape
    spending = np.array([np.dot(prices, X[j]) for j in range(n)])
    min_spend = np.min(spending)
    for j in range(n):
        # if agent j has <=1 item, no need to remove anything
        if np.sum(X[j]) <= 1:
            continue
        # compute j's spend minus one item
        possible_spends = [spending[j] - prices[i] for i in range(m) if X[j, i] > 0]
        # if all those spends remain strictly above (1+3*eps)*min_spend => fail
        if all(s > (1.0 + 3.0 * eps) * min_spend for s in possible_spends):
            return False
    return True

def market_phase1(V, eps):
    """
    phase 1: assign each item to the agent with highest value.
    prices = assigned value. check if 3*eps-ef1 is satisfied.
    returns (status, X, p).
    """
    (n, m) = V.shape
    X = np.zeros((n, m))
    p = np.zeros(m)
    for i in range(m):
        j_star = np.argmax(V[:, i])
        X[j_star, i] = 1
        p[i] = V[j_star, i]
    # check if the result is already 3*eps-ef1
    if is3epef1(X, p, eps):
        return True, X, p
    return False, X, p

def bpb(V, prices):
    """
    computes bang-per-buck for each agent/item.
    returns a matrix bb[j,i] = V[j,i]/prices[i].
    """
    (n, m) = V.shape
    BB = np.zeros((n, m))
    for j in range(n):
        for i in range(m):
            BB[j, i] = V[j, i] / prices[i]
    return BB

def build_mbb_graph(V, prices):
    """
    builds the MBB (most-bang-per-buck) directed graph.
    returns (G_MBB, MBB_edges, MBB_lists).
    """
    (n, m) = V.shape
    BB = bpb(V, prices)
    edges = []
    MBB_lists = []
    for j in range(n):
        row = BB[j, :]
        best_bpb = np.max(row)
        # find items i with best bpb
        best_items = np.where(row == best_bpb)[0]
        MBB_lists.append(best_items)
        for i in best_items:
            edges.append((('a', j), ('g', i)))
    G = nx.DiGraph()
    agent_nodes = [('a', j) for j in range(n)]
    item_nodes = [('g', i) for i in range(m)]
    G.add_nodes_from(agent_nodes + item_nodes)
    G.add_edges_from(edges)
    return G, edges, MBB_lists

def augment_mbb_graph(G_MBB, X):
    """
    adds edges item->agent if agent holds that item in X.
    returns the augmented graph.
    """
    (n, m) = X.shape
    new_edges = []
    for j in range(n):
        for i in range(m):
            if X[j, i] > 0:
                new_edges.append((('g', i), ('a', j)))
    G_aug = deepcopy(G_MBB)
    G_aug.add_edges_from(new_edges)
    return G_aug

def build_augmented_mbb_graph(V, X, prices):
    """
    builds the augmented MBB graph = MBB edges + item->agent from X.
    """
    G_MBB, _, _ = build_mbb_graph(V, prices)
    return augment_mbb_graph(G_MBB, X)

def build_hierarchy(jstar, G, X):
    """
    builds BFS-like layers from agent jstar in the augmented graph.
    returns a dict H[level] = list of agents at that level.
    """
    (n, m) = X.shape
    H = {l: [] for l in range(n)}
    for k in range(n):
        try:
            dist = nx.shortest_path_length(G, source=('a', jstar), target=('a', k))
            level = dist // 2
            H[level].append(k)
        except nx.NetworkXNoPath:
            pass
    return H

def market_phase2(V, eps, X, prices):
    """
    phase 2: attempt to fix envy by swapping an item from a higher spender to jstar.
    returns (status, next_phase, X, prices, jstar).
    """
    (n, m) = X.shape
    spending = np.array([np.dot(prices, X[j]) for j in range(n)])
    jstar = np.argmin(spending)
    G_aug = build_augmented_mbb_graph(V, X, prices)
    H = build_hierarchy(jstar, G_aug, X)
    level = 1
    while level in H and len(H[level]) > 0 and not is3epef1(X, prices, eps):
        for k in H[level]:
            # all shortest paths from jstar->k
            paths = nx.all_shortest_paths(G_aug, source=('a', jstar), target=('a', k))
            for path in paths:
                # path example: a->g->a->g->a
                # last item is path[-2] if that is a 'g'
                if len(path) < 3:
                    continue
                if path[-2][0] != 'g':
                    continue
                i = path[-2][1]   # item index
                # agent who had it is path[-3]
                if path[-3][0] != 'a':
                    continue
                holder = path[-3][1]
                # check if giving item i from k to jstar helps
                if spending[k] - prices[i] > (1 + eps)*spending[jstar]:
                    # do the reallocation
                    X[k, i] -= 1
                    X[holder, i] += 1
                    return False, 2, X, prices, jstar
        level += 1

    if is3epef1(X, prices, eps):
        return True, 0, X, prices, jstar
    return False, 3, X, prices, jstar

def market_phase3(V, eps, X, prices, jstar):
    """
    phase 3: scale prices of certain items in jstar's hierarchy to reduce envy.
    returns (status, next_phase, X, prices).
    """
    (n, m) = X.shape
    spending = np.array([np.dot(prices, X[j]) for j in range(n)])
    G_aug = build_augmented_mbb_graph(V, X, prices)
    H = build_hierarchy(jstar, G_aug, X)
    # gather agents/items in jstar's 'hierarchy'
    H_agents = []
    for lvl in H:
        H_agents.extend(H[lvl])
    H_items = []
    for j in H_agents:
        for i in range(m):
            if X[j, i] > 0:
                H_items.append(i)
    other_items = [i for i in range(m) if i not in H_items]
    # compute scale factors a1, a2, a3
    BB = bpb(V, prices)
    mbb = [np.max(BB[j]) for j in range(n)]
    # a1: min ratio of bang-per-buck if agent tries an outside item
    candidates = []
    for j in H_agents:
        for i in other_items:
            if V[j, i] > 0:
                ratio = mbb[j] / (V[j, i]/prices[i])
                candidates.append(ratio)
    a1 = min(candidates) if candidates else 0
    # a2: scale so jstar's spending can catch an outside agent
    a2 = np.inf
    if spending[jstar] > 0:
        outsiders = [x for x in range(n) if x not in H_agents]
        if outsiders:
            leftover = []
            for k in outsiders:
                # best item to remove from k
                remove_vals = [prices[i] for i in range(m) if X[k, i] > 0]
                if remove_vals:
                    leftover.append(spending[k] - max(remove_vals))
            if leftover:
                a2 = max(leftover)/spending[jstar]
    # a3: scale to surpass some outside agent
    a3 = np.inf
    if spending[jstar] > 0:
        outsiders = [x for x in range(n) if x not in H_agents]
        if outsiders:
            jhat = outsiders[np.argmin(spending[outs] for outs in outsiders)]
            ratio = spending[jhat]/spending[jstar]
            s = 0
            while (1+eps)**s <= ratio:
                s += 1
            a3 = (1+eps)**s
    # pick a
    a = min(a1, a2, a3)
    # scale prices of items in H_items
    for i in H_items:
        prices[i] *= a
    if a == a2:
        return True, 0, X, prices
    return False, 2, X, prices



# ---------------------------------- Leximin helpers ----------------------------------

import numpy as np
from copy import deepcopy
from gurobipy import Model, GRB, quicksum

def leximin_solve(V, B=1000, chores=False):
    """
    solves a leximin allocation problem on valuations V.
    V: n x m float array of valuations.
    B: bounding parameter (e.g. config.B).
    chores: if True, valuations are for chores (<=0). otherwise, goods.

    returns (status, sw, U, A):
      status : bool (True if gurobi found an optimal solution)
      sw     : sum of utilities in the final allocation
      U      : list of each agent's utility
      A      : n x m binary allocation matrix
    """
    (n, m) = V.shape
    b_levels = []
    A = np.zeros((n, m))
    U = [0]*n
    status = False

    # we iterate from k=1..n, gradually lifting the minimum utility
    for k in range(1, n+1):
        model = Model(f'leximin_{k}')
        model.setParam('OutputFlag', 0)
        model.setParam('TimeLimit', 300)

        # if k=1, bvar can range from -B..B for chores or 0..B for goods
        # otherwise, bvar must be >= the previously found bound
        if k == 1:
            lower_bound = -1 * int(chores)*B
        else:
            lower_bound = b_levels[k-2]

        bvar = model.addVar(lb=lower_bound,
                            ub=(1 - int(chores)) * B,
                            vtype=GRB.CONTINUOUS,
                            name='b')

        # xvars[j,i] = 1 if item i is allocated to agent j
        xvars = {}
        for j in range(n):
            for i in range(m):
                xvars[j, i] = model.addVar(lb=0, ub=1, vtype=GRB.BINARY,
                                           name=f'x_{j}_{i}')

        # uvars[j] = total utility of agent j
        uvars = {}
        for j in range(n):
            if chores:
                lb_j = -B
                ub_j = 0
            else:
                lb_j = 0
                ub_j = B
            uvars[j] = model.addVar(lb=lb_j, ub=ub_j,
                                    vtype=GRB.CONTINUOUS,
                                    name=f'u_{j}')

        # yvars[j,l] indicates whether agent j's utility >= bvar at iteration l
        # zvars[l] counts how many agents have utility >= bvar at iteration l
        yvars = {}
        zvars = {}
        for lvl in range(k):
            zvars[lvl] = model.addVar(lb=0, ub=n, vtype=GRB.INTEGER,
                                      name=f'z_{lvl}')
            for j in range(n):
                yvars[j, lvl] = model.addVar(lb=0, ub=1, vtype=GRB.BINARY,
                                             name=f'y_{j}_{lvl}')

        # each item allocated exactly once
        for i in range(m):
            model.addConstr(quicksum(xvars[j, i] for j in range(n)) == 1)

        # link uvars[j] to actual valuations
        for j in range(n):
            model.addConstr(uvars[j] == quicksum(V[j, i]*xvars[j, i]
                                                for i in range(m)))

        # ensure at least k-l+1 agents are >= bvar at level l
        # if l < k-1, we fix bvar to previously found bound b_levels[l]
        for lvl in range(k-1):
            bound_l = b_levels[lvl]
            for j in range(n):
                # yvars[j,lvl] = 1 if uvars[j] >= bound_l
                model.addConstr(yvars[j, lvl] >= (1 + uvars[j] - bound_l)/B)
                model.addConstr(yvars[j, lvl] <= (B + uvars[j] - bound_l)/B)
            model.addConstr(zvars[lvl] == quicksum(yvars[j, lvl]
                                                   for j in range(n)))
            model.addConstr(zvars[lvl] >= n - lvl)

        # for the final level k-1, we compare with bvar
        for j in range(n):
            model.addConstr(yvars[j, k-1] >= (1 + uvars[j] - bvar)/B)
            model.addConstr(yvars[j, k-1] <= (B + uvars[j] - bvar)/B)
        model.addConstr(zvars[k-1] == quicksum(yvars[j, k-1]
                                               for j in range(n)))
        model.addConstr(zvars[k-1] >= n - (k-1))

        # objective: maximize bvar
        model.setObjective(bvar, GRB.MAXIMIZE)
        model.optimize()

        if model.Status != GRB.OPTIMAL:
            return False, None, None, None  # not feasible

        # store the found bound
        b_levels.append(bvar.X)

        # build final allocation
        A_tmp = np.zeros((n, m))
        for j in range(n):
            for i in range(m):
                A_tmp[j, i] = round(xvars[j, i].X)
        A_tmp = A_tmp.astype(int)

        # we keep going until k=n, but store the final
        A = A_tmp
        U = [float(np.dot(V[j], A[j])) for j in range(n)]

        status = True

    sw = sum(U)
    return status, sw, U, A
