import os
import json
import numpy as np

# Dirichlet instance generator
def generate_positive_dirichlet_instance(m, n, B=1000):
    """generate dirichlet instance with integer values summing to budget B"""
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

def generate_random_instances(n_instances=100, agent_counts=[2, 3, 4], item_counts=[3, 5, 7], budget=1000):
    """
    generate random test instances using dirichlet distribution
    
    args:
        n_instances: total number of instances to generate
        agent_counts: list of possible agent counts
        item_counts: list of possible item counts
        budget: budget for each agent
        
    returns:
        dictionary of instances with descriptive keys
    """
    instances = {}
    instance_counter = 0
    
    # generate instances with varying agent/item counts
    for _ in range(n_instances):
        # randomly select counts
        n_agents = np.random.choice(agent_counts)
        n_items = np.random.choice(item_counts)
        
        # generate instance
        V = generate_positive_dirichlet_instance(n_items, n_agents, B=budget)
        
        # create descriptive name
        instance_name = f"dirichlet_{n_agents}agents_{n_items}items_{instance_counter}"
        instances[instance_name] = V.tolist()  # convert for json
        instance_counter += 1
    
    return instances

def save_instances(instances, filename="dirichlet_instances.json"):
    """save generated instances to json file"""
    # ensure directory exists
    test_instances_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_instances')
    os.makedirs(test_instances_dir, exist_ok=True)
    
    # create output path
    output_path = os.path.join(test_instances_dir, filename)
    
    # save to file
    with open(output_path, 'w') as f:
        json.dump(instances, f, indent=2)
    
    print(f"generated {len(instances)} instances saved to {output_path}")
    return output_path

if __name__ == "__main__":
    # generate and save 100 instances
    instances = generate_random_instances(n_instances=100)
    save_instances(instances)