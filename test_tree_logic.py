lines = []
def _draw_tree(node_dict, is_last_list):
    node = node_dict["node"]
    children = node_dict["children"]
    
    prefix_parts = []
    if is_last_list:
        for is_last in is_last_list[:-1]:
            prefix_parts.append("    " if is_last else "│   ")
        prefix_parts.append("└── " if is_last_list[-1] else "├── ")
        
    prefix = "".join(prefix_parts)
    lines.append(prefix + str(node))
    
    for i, child_dict in enumerate(children):
        is_last = (i == len(children) - 1)
        _draw_tree(child_dict, is_last_list + [is_last])

tree = {
    "node": "Root",
    "children": [
        {
            "node": "Child 1",
            "children": [
                {"node": "Grandchild 1", "children": []},
                {"node": "Grandchild 2", "children": []}
            ]
        },
        {
            "node": "Child 2",
            "children": []
        }
    ]
}

_draw_tree(tree, [])
print("\n".join(lines))
