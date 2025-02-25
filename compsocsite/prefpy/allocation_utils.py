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
