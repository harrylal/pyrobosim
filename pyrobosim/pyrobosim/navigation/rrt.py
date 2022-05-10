"""
Implementation of the Rapidly-exploring Random Tree (RRT) 
algorithm for motion planning.
"""

import copy
import time
import numpy as np

from .search_graph import SearchGraph, Node, Edge
from ..utils.pose import Pose

class RRTPlanner:

    # Default params
    max_connection_dist = 0.5
    max_nodes_sampled = 1000
    max_time = 5
    rewire_radius = 1.0

    def __init__(self, world, bidirectional=False, rrt_connect=False, rrt_star=False):
        # Algorithm options
        self.bidirectional = bidirectional
        self.rrt_connect = rrt_connect
        self.rrt_star = rrt_star

        self.world = world
        self.reset()

    def reset(self):
        """ Resets the search trees """
        self.graph = SearchGraph(world=self.world)
        self.graph_goal = SearchGraph(world=self.world)
        self.planning_time = 0.0
        self.nodes_sampled = 0
        self.n_rewires = 0

    def plan(self, start, goal):
        self.reset()

        # Create the start and goal nodes
        n_start = Node(start, parent=None)
        n_goal = Node(goal, parent=None)
        self.graph.nodes = {n_start}
        if self.bidirectional:
            self.graph_goal.nodes = {n_goal}

        t_start = time.time()
        goal_found = False
        while not goal_found:
            # Sample a node
            q_sample = self.sample_configuration()
            self.nodes_sampled += 1

            # Connect aa new node to the parent
            n_near = self.graph.nearest_node(q_sample)
            n_new = self.new_node(n_near, q_sample)
            connected_node = self.graph.connect(n_near, n_new)
            if connected_node:
                self.graph.nodes.add(n_new)

            # If bidirectional, also connect a new node to the parent of the goal graph
            if self.bidirectional:
                n_near_goal = self.graph_goal.nearest_node(q_sample)
                n_new_goal = self.new_node(n_near_goal, q_sample)
                connected_node_goal = self.graph_goal.connect(n_near_goal, n_new_goal)
                if connected_node_goal:
                    self.graph_goal.nodes.add(n_new_goal)
            else:
                connected_node_goal = False

            # Optional rewire, if RRT* is enabled
            if self.rrt_star:
                if connected_node:
                    self.rewire_node(self.graph, n_new)
                if connected_node_goal:
                    self.rewire_node(self.graph_goal, n_new_goal)

            # See if the new nodes can directly connect to the goal.
            # This is done either as a single connection within max distance, or using RRT-Connect.
            if self.bidirectional:
                if connected_node:
                    # If we added a node to the start tree, try connect to the goal tree
                    n_goal_goal_tree = self.graph_goal.nearest_node(n_new.pose)
                    goal_found, n_goal_start_tree = self.try_connect_until(self.graph, n_new, n_goal_goal_tree)

                if connected_node_goal and not goal_found:
                    # If we added a node to the goal tree, try connect to the start tree
                    n_goal_start_tree = self.graph.nearest_node(n_new_goal.pose)
                    goal_found, n_goal_goal_tree = self.try_connect_until(self.graph_goal, n_new_goal, n_goal_start_tree)

            elif connected_node:
                goal_found, _ = self.try_connect_until(self.graph, n_new, n_goal)

            # Check max nodes samples or max time elapsed
            self.planning_time = time.time() - t_start
            if self.planning_time > self.max_time or self.nodes_sampled > self.max_nodes_sampled:
                break
            
        # Now back out the path
        if self.bidirectional:
            n = n_goal_start_tree
        else:
            n = n_goal
        path = [n]
        path_built = False
        while not path_built:
            if n.parent is None:
                path_built = True
            else:
                n = n.parent
                path.append(n)
        path.reverse()
        if self.bidirectional:
            n = n_goal_goal_tree
            path_built = False
            while not path_built:
                if n.parent is None:
                    path_built = True
                else:
                    n = n.parent
                    path.append(n)
        return path         

    def sample_configuration(self):
        """ Sample a random configuration from the world. """
        return self.world.sample_free_robot_pose_uniform()

    def new_node(self, n_near, q_sample):
        """ Creates a new node based on the nearest """
        q_start = n_near.pose
        dist = q_start.get_linear_distance(q_sample)

        step_dist = self.max_connection_dist
        if dist <= step_dist:
            q_new = q_sample
        else:
            theta = q_start.get_angular_distance(q_sample)
            q_new = Pose(x=q_start.x + step_dist * np.cos(theta),
                         y=q_start.y + step_dist * np.sin(theta))

        return Node(q_new, parent=n_near, cost=n_near.cost + dist)

    def rewire_node(self, graph, n_tgt):
        """ 
        Rewires a node by checking vicinity. 
        This is the key modification for RRT*.
        """
        # First, find the node to rewire, if any
        n_rewire = None
        for n in graph.nodes:
            dist = n.pose.get_linear_distance(n_tgt.pose)
            if (n != n_tgt) and (dist <= self.rewire_radius):
                alt_cost = n.cost + dist
                if (alt_cost < n_tgt.cost) and \
                    graph.check_connectivity(n, n_tgt):
                    n_rewire = n
                    n_tgt.cost = alt_cost

        # If we found a rewire node, do the rewire
        if n_rewire is not None:
            n_tgt.parent = n_rewire
            for e in graph.edges.copy():
                if e.n0 == n_tgt or e.n1 == n_tgt:
                    graph.edges.remove(e)
            graph.edges.add(Edge(n_tgt, n_tgt.parent))
            self.n_rewires += 1

    def try_connect_until(self, graph, n_curr, n_tgt):
        """
        Try to connect a node "n_curr" to a target node "n_tgt".
        This will keep extending the current node towards the target if 
        RRT-Connect is enabled, or else will just try once.
        """
        # Needed for bidirectional RRT so the connection node can be in both trees.
        if self.bidirectional:
            n_tgt = copy.deepcopy(n_tgt)

        while True:
            dist = n_curr.pose.get_linear_distance(n_tgt.pose)

            # First, try directly connecting to the goal
            if dist < self.max_connection_dist and self.graph.connect(n_curr, n_tgt):
                n_tgt.parent = n_curr
                graph.nodes.add(n_tgt)
                return True, n_tgt

            if self.rrt_connect:
                # If using RRT-Connect, keep trying to connect until we succeed or fail.
                n_new = self.new_node(n_curr, n_tgt.pose)
                if graph.connect(n_curr, n_new):
                    graph.nodes.add(n_new)
                    n_curr = n_new
                else:
                    return False, n_curr
            else:
                # If not using RRT-Connect, we only get one chance to connect to the target.
                return False, n_curr
