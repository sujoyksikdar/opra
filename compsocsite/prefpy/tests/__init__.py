"""
test package for prefpy allocation mechanisms.

contains tests for allocation mechanisms:
- round robin
- maximum nash welfare
- market-based (ef1 + po)
- leximin
- market equilibrium (eq1 + po)
- mnw binary

tests check that each:
- produces valid allocations
- satisfies required properties
- gets evaluated on other fairness criteria
"""

# make test classes available
from .test_mechanism import TestMechanism
from .test_allocation_mechanisms import (
    TestRoundRobinAllocation,
    TestMaximumNashWelfare,
    TestMarketAllocation,
    TestLeximinAllocation,
    TestMarketEqAllocation,
    TestMaximumNashWelfareBinary
)