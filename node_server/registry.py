class NodeRegistry:

    register(node_id, node_type, connection)

    unregister(node_id)

    get_node(node_id)

    list_nodes(type=None)