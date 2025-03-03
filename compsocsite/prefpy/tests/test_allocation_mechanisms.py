# test_allocation_mechanisms.py

from django.test import TestCase
import numpy as np

from prefpy.mechanism import (
    MechanismRoundRobinAllocation,
    MechanismMaximumNashWelfare,
    MechanismMarketAllocation,
    MechanismLeximinAllocation,
    MechanismMarketEqAllocation,
    MechanismMaximumNashWelfareBinary
)

# import property checks (ef, ef1, po, etc.)
from prefpy.allocation_properties import *


class TestAllocationMechanismsBase(TestCase):
    """
    base class for allocation mechanism tests.
    defines common valuation matrices for general working checks.
    """

    @classmethod
    def setUpClass(cls):
        """
        initializes general test matrices shared across all allocation algorithms.
        """
        super().setUpClass()
        
        # 2 agents, 2 items
        cls.V1 = np.array([
            [3, 1],
            [1, 3]
        ], dtype=float)

        # 2 agents, 3 items
        cls.V2 = np.array([
            [10, 5, 2],
            [5, 10, 2]
        ], dtype=float)

        # 3-agent scenario
        cls.V3 = np.array([
            [4, 2, 1],
            [2, 5, 3],
            [1, 3, 6]
        ], dtype=float)

    def check_allocation_validity(self, V, A):
        """
        ensures allocation matrix is valid (each item assigned exactly once).
        """
        self.assertTrue(valid_allocation(V, A), "allocation is invalid: some items are not assigned correctly.")

    def test_matrix_shapes(self):
        """
        ensures valuation matrices are correctly defined.
        """
        for V in [self.V1, self.V2, self.V3]:
            self.assertIsInstance(V, np.ndarray)
            self.assertGreaterEqual(V.shape[0], 2)  # at least 2 agents
            self.assertGreaterEqual(V.shape[1], 2)  # at least 2 items


# ------------------------------------------------------------------------
#  round robin allocation tests
# ------------------------------------------------------------------------

class TestRoundRobinAllocation(TestAllocationMechanismsBase):
    """
    tests for round robin allocation mechanism.
    """

    def setUp(self):
        """ initialize round robin allocation mechanism. """
        self.rr_alloc = MechanismRoundRobinAllocation()

    def test_round_robin_basic(self):
        """ test if round robin mechanism runs successfully. """
        for V in [self.V1, self.V2, self.V3]:
            result = self.rr_alloc.allocate(V)
            self.assertTrue(result.status, "round robin allocation failed to return a valid result.")

            A = np.array(result.A)

            # check that allocation matrix is valid
            self.check_allocation_validity(V, A)

            print("\n" + "=" * 70)
            print("ROUND ROBIN BASIC TEST")
            print("=" * 70 + "\n")
            print("Valuations:\n", V)
            print("Allocation Matrix (A):\n", A)
            print()

    def test_round_robin_ef1(self):
        """ check if round robin always satisfies EF1 (envy-freeness up to one item). """
        for V in [self.V1, self.V2, self.V3]:
            result = self.rr_alloc.allocate(V)
            self.assertTrue(result.status, "round robin allocation failed.")

            A = np.array(result.A)

            # round robin is known to always satisfy EF1
            self.assertTrue(is_ef1(V, A), "round robin should always be EF1 but failed.")

            print("\n" + "=" * 70)
            print("ROUND ROBIN EF1 CHECK")
            print("=" * 70 + "\n")
            print("Valuations:\n", V)
            print("Allocation Matrix (A):\n", A)
            print(f"EF1: {is_ef1(V, A)}\n")

    def test_round_robin_po(self):
        """ check if round robin produces a pareto optimal allocation. """
        for V in [self.V1, self.V2, self.V3]:
            result = self.rr_alloc.allocate(V)
            self.assertTrue(result.status, "round robin allocation failed.")

            A = np.array(result.A)

            # round robin is not guaranteed to be PO, but we still check
            po_flag = is_po(V, A)

            print("\n" + "=" * 70)
            print("ROUND ROBIN PO CHECK")
            print("=" * 70 + "\n")
            print("Valuations:\n", V)
            print("Allocation Matrix (A):\n", A)
            print(f"PO: {po_flag}\n")



# ------------------------------------------------------------------------
#  maximum nash welfare (mnw) allocation tests (skeleton)
# ------------------------------------------------------------------------

class TestMaximumNashWelfare(TestAllocationMechanismsBase):
    """
    tests for the maximum nash welfare (mnw) mechanism.
    """

    def setUp(self):
        """ initialize mnw allocation mechanism. """
        self.mnw_alloc = MechanismMaximumNashWelfare()

    def test_mnw_basic(self):
        """ test if mnw mechanism runs successfully. """
        pass


# ------------------------------------------------------------------------
#  market allocation tests (skeleton)
# ------------------------------------------------------------------------

class TestMarketAllocation(TestAllocationMechanismsBase):
    """
    tests for market-based allocation mechanism.
    """

    def setUp(self):
        """ initialize market allocation mechanism. """
        self.market_alloc = MechanismMarketAllocation()

    def test_market_basic(self):
        """ test if market allocation mechanism runs successfully. """
        pass


# ------------------------------------------------------------------------
#  leximin allocation tests (skeleton)
# ------------------------------------------------------------------------

class TestLeximinAllocation(TestAllocationMechanismsBase):
    """
    tests for leximin allocation.
    """

    def setUp(self):
        """ initialize leximin allocation mechanism. """
        self.leximin_alloc = MechanismLeximinAllocation()

    def test_leximin_basic(self):
        """ test if leximin mechanism runs successfully. """
        pass


# ------------------------------------------------------------------------
#  market equilibrium allocation tests (skeleton)
# ------------------------------------------------------------------------

class TestMarketEqAllocation(TestAllocationMechanismsBase):
    """
    tests for market equilibrium allocation.
    """

    def setUp(self):
        """ initialize market equilibrium allocation mechanism. """
        self.market_eq_alloc = MechanismMarketEqAllocation()

    def test_market_eq_basic(self):
        """ test if market equilibrium mechanism runs successfully. """
        pass


# ------------------------------------------------------------------------
#  maximum nash welfare binary allocation tests (skeleton)
# ------------------------------------------------------------------------

class TestMaximumNashWelfareBinary(TestAllocationMechanismsBase):
    """
    tests for maximum nash welfare binary allocation.
    """

    def setUp(self):
        """ initialize mnw binary allocation mechanism. """
        self.mnw_binary_alloc = MechanismMaximumNashWelfareBinary()

    def test_mnw_binary_basic(self):
        """ test if mnw binary mechanism runs successfully. """
        pass
