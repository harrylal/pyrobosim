"""
Room Representation for World Modeling
"""

import warnings
from shapely.geometry import Polygon, Point
from descartes.patch import PolygonPatch

from .search_graph import Node
from ..utils.pose import Pose
from ..utils.polygon import inflate_polygon


class Room:
    def __init__(self, coords, name=None, color=[0.4, 0.4, 0.4], wall_width=0.2, nav_poses=None):
        self.name = name
        self.wall_width = wall_width
        self.viz_color = color

        # Entities associated with the room
        self.hallways = []
        self.locations = []
        self.graph_nodes = []

        # Create the room polygon
        self.polygon = Polygon(coords)
        self.centroid = list(self.polygon.centroid.coords)[0]
        self.update_collision_polygons()
        self.update_visualization_polygon()

        # Create a navigation pose list -- if none specified, use the room centroid
        if nav_poses is not None:
            self.nav_poses = nav_poses
        else:
            self.nav_poses = [Pose(x=self.centroid[0], y=self.centroid[1])]

    def update_collision_polygons(self, inflation_radius=0):
        """ Updates collision polygons using the specified inflation radius """
        # Internal collision polygon:
        # Deflate the room polygon with the inflation radius and add each location's collision polygon.
        self.internal_collision_polygon = inflate_polygon(
            self.polygon, -inflation_radius)
        for loc in self.locations:
            self.internal_collision_polygon = self.internal_collision_polygon.difference(
                loc.collision_polygon)

        # External collision polygon:
        # Inflate the room polygon with the wall width
        self.external_collision_polygon = inflate_polygon(
            self.polygon, self.wall_width)

    def update_visualization_polygon(self):
        """ Updates visualization polygon for world plotting """
        self.buffered_polygon = inflate_polygon(self.polygon, self.wall_width)
        self.viz_polygon = self.buffered_polygon.difference(self.polygon)
        for h in self.hallways:
            self.viz_polygon = self.viz_polygon.difference(h.polygon)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.viz_patch = PolygonPatch(
                self.viz_polygon,
                fc=self.viz_color, ec=self.viz_color,
                lw=2, alpha=0.75, zorder=2)

    def get_collision_patch(self):
        """ Returns a PolygonPatch of collision polygon for debug """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return PolygonPatch(
                self.internal_collision_polygon,
                fc=[1, 0, 1], ec=[1, 0, 1],
                lw=2, alpha=0.5, zorder=2)

    def is_collision_free(self, pose):
        """ Checks whether a pose in the room is collision-free """
        if isinstance(pose, Pose):
            p = Point(pose.x, pose.y)
        else:
            p = Point(pose[0], pose[1])
        return self.internal_collision_polygon.intersects(p)

    def add_graph_nodes(self):
        """ Creates graph nodes for searching """
        self.graph_nodes = [Node(p, parent=self) for p in self.nav_poses]

    def __repr__(self):
        return f"Room: {self.name}"
