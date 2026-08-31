import json

with open('Klotski-Webpage/data.json', 'r') as f:
    content = f.read()
    content = content.replace('var nodes_to_use = ', '')
    data = json.loads(content)
    print(f'Total nodes: {len(data)}')
    # Check solution distances
    solution_dists = [v['solution_dist'] for v in data.values()]
    print(f'Max solution_dist: {max(solution_dists)}')
    print(f'Min solution_dist: {min(solution_dists)}')
    print(f'Nodes at solution (dist=0): {sum(1 for d in solution_dists if d == 0)}')
