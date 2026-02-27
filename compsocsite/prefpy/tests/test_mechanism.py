import json
import os
import numpy as np
import unittest

from prefpy.allocation_properties import is_ef1, is_efx, is_ef, is_po, is_eq, is_eq1, is_eqx, is_dupeq1, is_dupeqx

class TestMechanism(unittest.TestCase):
    """base test class for allocation mechanisms"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instances = []
        self.properties = []
        self.allocations = []
        self.mechanism = None
        self._tested_properties = {}  # cache for tested properties
        self.property_map = {
            'ef1': is_ef1,
            'efx': is_efx,
            'ef': is_ef,
            'po': is_po,
            'eq': is_eq,
            'eq1': is_eq1,
            'eqx': is_eqx,
            'dupeq1': is_dupeq1,
            'dupeqx': is_dupeqx,
            'valid': self.check_allocation_validity
        }
    
    def load_instances(self, filename=None):
        """load test instances from json file"""
        if filename is None:
            # Check if INSTANCE_FILE env var is set, default to basic_instances.json
            filename = os.environ.get('INSTANCE_FILE', 'basic_instances.json')
        
        # look in tests/test_instances directory
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_instances', filename)
        
        # only log path once
        if not hasattr(self, '_path_logged'):
            print(f"looking for test instances at: {file_path}")
            self._path_logged = True
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # convert to numpy arrays
        instances = []
        for key, matrix in data.items():
            instances.append(np.array(matrix, dtype=float))
        
        self.instances = instances
        return self.instances
    
    def load_dirichlet_instances(self, filename='dirichlet_instances.json'):
        """load Dirichlet test instances from json file"""
        # look in tests/test_instances directory
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_instances', filename)
        
        print(f"loading Dirichlet test instances from: {file_path}")
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # convert to numpy arrays
        instances = []
        for key, matrix in data.items():
            instances.append(np.array(matrix, dtype=float))
        
        self.instances = instances
        return self.instances
    
    def check_allocation_validity(self, V, A):
        """check if allocation is valid (each item assigned exactly once)"""
        n_agents, n_items = V.shape
        
        # check dimensions match
        self.assertEqual(A.shape[0], n_agents, "number of agents in allocation doesn't match valuation")
        self.assertEqual(A.shape[1], n_items, "number of items in allocation doesn't match valuation")
        
        # check each item is assigned exactly once
        for j in range(n_items):
            self.assertEqual(np.sum(A[:, j]), 1, f"item {j} is not assigned exactly once")
        
        return True
    
    def generate_allocations(self):
        """generate allocations for all instances using the mechanism"""
        if self.mechanism is None:
            raise ValueError("mechanism not set")
        
        self.allocations = []
        for idx, V in enumerate(self.instances):
            result = self.mechanism.allocate(V)
            self.assertTrue(result.status, f"mechanism failed on instance {idx}")
            self.allocations.append(np.array(result.A))
        
        return self.allocations
    
    def test_property(self, property_name=None):
        """test if all allocations satisfy a specific property"""
        # use cached result if available
        property_key = f"tested_{property_name}"
        if property_key in self._tested_properties:
            return self._tested_properties[property_key]
            
        # default to first property or 'valid'
        if property_name is None:
            if self.properties:
                property_name = self.properties[0]
            else:
                property_name = 'valid'
        
        if not self.allocations:
            self.generate_allocations()
        
        if property_name not in self.property_map:
            raise ValueError(f"unknown property: {property_name}")
        
        property_check = self.property_map[property_name]
        
        all_pass = True
        for idx, (V, A) in enumerate(zip(self.instances, self.allocations)):
            # call the property check function
            satisfied = property_check(V, A)
            
            # output details
            print(f"\nchecking {property_name} for instance {idx}:")
            print(f"valuation matrix:\n{V}")
            print(f"allocation matrix:\n{A}")
            print(f"{property_name} satisfied: {satisfied}")
            
            # assert if required property
            if property_name in self.properties:
                self.assertTrue(satisfied, 
                               f"property {property_name} not satisfied for instance {idx}")
            
            all_pass = all_pass and satisfied
        
        # cache the result
        self._tested_properties[property_key] = all_pass
        return all_pass
    
    def test_properties(self):
        """test if all allocations satisfy all required properties"""
        for property_name in self.properties:
            self.test_property(property_name)
    
    def load_specific_instance(self, instance_name, filename='basic_instances.json'):
        """load a specific test instance by name"""
        # look in tests/test_instances directory
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_instances', filename)
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if instance_name not in data:
            raise ValueError(f"instance {instance_name} not found in {filename}")
        
        return np.array(data[instance_name], dtype=float)

    def add_custom_property(self, name, check_function):
        """add a custom property checker"""
        self.property_map[name] = check_function

# Dirichlet instance generator
def generate_positive_dirichlet_instance(m, n, B=1000):
    """generate dirichlet instance with integer values summing to budget B"""
    import numpy as np
    V = list()
    for j in range(n):
        vals = np.random.dirichlet([10 for i in range(m)])
        vals = vals + 0.001
        vals = [np.ceil(B*v) for v in vals]
        while np.sum(vals) > B:
            i = np.random.randint(low=0, high=m)
            if vals[i] > 1:
                vals[i] = vals[i] - 1
        V.append(vals)
    V = np.array(V)
    return V