import numpy as np



"""
changes made to run 

removed intial compsocsite, and swapped from voting mech to allocation

"""

from prefpy.allocation_mechanism import ( 
    MechanismRoundRobinAllocation,
    MechanismMaximumNashWelfare,
    MechanismMarketAllocation,
    MechanismLeximinAllocation,
    MechanismMarketEqAllocation,
    MechanismMaximumNashWelfareBinary,
    MechanismMarketEQ1PO
)

from prefpy.allocation_properties import *
from prefpy.allocation_utils import *
from .test_mechanism import TestMechanism

# ------------------------------------------------------------------------
#  round robin allocation tests
# ------------------------------------------------------------------------

class TestRoundRobinAllocation(TestMechanism):
    """test round robin allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismRoundRobinAllocation()
        self.properties = ['ef1', 'valid']  # round robin always satisfies ef1
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='ef1'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_round_robin_basic(self):
        """test if the round robin mechanism works correctly"""
        # basic test with allocations from setup
        pass

    def test_properties(self):
        """test required and other properties for round robin"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('po')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eq1')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  maximum nash welfare (mnw) allocation tests
# ------------------------------------------------------------------------

class TestMaximumNashWelfare(TestMechanism):
    """test maximum nash welfare allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismMaximumNashWelfare()
        self.properties = ['po', 'valid']  # mnw always satisfies po
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='po'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_mnw_basic(self):
        """basic test for mnw mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            # compute nash welfare
            nw_value, utilities = nw(V, A)
            
            print(f"\n{'=' * 70}\nmnw basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
            print(f"nash welfare: {nw_value}")
            print(f"utilities: {utilities}")
    
    def test_properties(self):
        """test required and other properties for mnw"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('ef1')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eq1')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  market allocation tests
# ------------------------------------------------------------------------

class TestMarketAllocation(TestMechanism):
    """test market-based allocation mechanism (ef1 + po)"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismMarketAllocation()
        self.properties = ['ef1', 'po', 'valid']  # market should satisfy ef1 and po
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='ef1'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_market_basic(self):
        """basic test for market mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            print(f"\n{'=' * 70}\nmarket basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
    
    def test_properties(self):
        """test required and other properties for market"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eq1')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  leximin allocation tests
# ------------------------------------------------------------------------

class TestLeximinAllocation(TestMechanism):
    """test leximin allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismLeximinAllocation()
        self.properties = ['po', 'efx', 'eq1', 'eqx', 'dupeq1', 'dupeqx', 'valid']
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='po'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_leximin_basic(self):
        """basic test for leximin mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            print(f"\n{'=' * 70}\nleximin basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
    
    def test_properties(self):
        """test required and other properties for leximin"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('ef1')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eq1')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  market equilibrium allocation tests
# ------------------------------------------------------------------------

class TestMarketEqAllocation(TestMechanism):
    """test market-based equitable allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismMarketEqAllocation()
        self.properties = ['po', 'eq1', 'dupeq1', 'valid']
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='po'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_market_eq_basic(self):
        """basic test for market-eq mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            print(f"\n{'=' * 70}\nmarket equilibrium basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
    
    def test_properties(self):
        """test required and other properties for market-eq"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('ef1')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  maximum nash welfare binary allocation tests
# ------------------------------------------------------------------------

class TestMaximumNashWelfareBinary(TestMechanism):
    """test maximum nash welfare binary allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismMaximumNashWelfareBinary()
        self.properties = ['po', 'valid']  # mnw binary should satisfy po
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='po'):
        """test if all allocations satisfy a specific property"""
        # use caching mechanism
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_mnw_binary_basic(self):
        """basic test for mnw binary mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            # compute nash welfare
            nw_value, utilities = nw(V, A)
            
            print(f"\n{'=' * 70}\nmnw binary basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
            print(f"nash welfare: {nw_value}")
            print(f"utilities: {utilities}")
    
    def test_properties(self):
        """test required and other properties for mnw binary"""
        # check required properties
        super().test_properties()
        
        # check other interesting properties
        self.test_property('ef1')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eq1')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')


# ------------------------------------------------------------------------
#  market eq1+po allocation tests
# ------------------------------------------------------------------------

class TestMarketEq1PoAllocation(TestMechanism):
    """test custom market eq1+po allocation mechanism"""
    
    def setUp(self):
        """initialize tests with instances and required properties"""
        self.mechanism = MechanismMarketEQ1PO() 
        
        self.properties = ['po', 'eq1', 'valid'] 
        
        # Load Dirichlet instances instead of basic instances
        try:
            self.load_dirichlet_instances()
        except FileNotFoundError:
            # Fall back to basic instances if Dirichlet instances aren't available
            print("Dirichlet instances not found, falling back to basic instances")
            self.load_instances()
        
        self.generate_allocations()
    
    def test_property(self, property_name='po'):
        """test if all allocations satisfy a specific property"""
        # Note: Your test suite repeats this caching logic in every class. 
        # This should ideally just live in TestMechanism, but we keep it here to match your pattern.
        property_key = f"tested_{property_name}"
        if hasattr(self, property_key):
            return getattr(self, property_key)
            
        result = super().test_property(property_name)
        setattr(self, property_key, result)
        return result
    
    def test_market_eq1po_basic(self):
        """basic test for your custom mechanism"""
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            print(f"\n{'=' * 70}\ncustom eq1+po basic test ({idx+1})\n{'=' * 70}")
            print(f"valuations:\n{V}")
            print(f"allocation:\n{A}")
    
    def test_properties(self):
        """test required and other properties for custom mechanism"""
        # check  PO and EQ1
        super().test_properties()
        
        # check other interesting properties to see what else it accidentally satisfies
        self.test_property('ef1')
        self.test_property('efx')
        self.test_property('eq')
        self.test_property('eqx')
        self.test_property('dupeq1')
        self.test_property('dupeqx')

# direct execution
if __name__ == '__main__':
    import unittest
    unittest.main()