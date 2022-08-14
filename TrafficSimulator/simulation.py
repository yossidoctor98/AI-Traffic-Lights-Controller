from copy import deepcopy
from itertools import chain
from statistics import mean
from typing import List, Dict, Tuple, Set, Optional

from scipy.spatial import distance

from TrafficSimulator.road import Road
from TrafficSimulator.traffic_signal import TrafficSignal
from TrafficSimulator.vehicle_generator import VehicleGenerator
from TrafficSimulator.window import Window


class Simulation:
    def __init__(self, max_gen=None):
        self.t = 0.0  # Time
        self.dt = 1 / 60  # Time step
        self.roads: List[Road] = []
        self.generators: List[VehicleGenerator] = []
        self.traffic_signals: List[TrafficSignal] = []

        self.collision_detected: bool = False
        self.n_vehicles_generated: int = 0
        self.n_vehicles_on_map: int = 0

        self._gui: Optional[Window] = None
        self._non_empty_roads: Set[int] = set()
        self._intersections: Dict[int, Set[int]] = {}  # {Road index: [intersecting roads' indexes]}
        self._max_gen: Optional[int] = max_gen  # Vehicle generation limit
        self._waiting_times: List[float] = []  # for vehicles that completed the journey

    @property
    def gui_closed(self) -> bool:
        return self._gui and self._gui.closed

    @property
    def non_empty_roads(self) -> Set[int]:
        return self._non_empty_roads

    @property
    def completed(self) -> bool:
        """
        Whether a terminal state (as defined under the MDP of the task) is reached.
        """
        reached_limit = self._max_gen and self.n_vehicles_generated == self._max_gen and \
                        not self.n_vehicles_on_map
        return self.collision_detected or reached_limit

    @property
    def intersections(self) -> Dict[int, Set[int]]:
        """
        Reduces the intersections' dict to non-empty roads
        :return: a dictionary of {non-empty road index: [non-empty intersecting roads indexes]}
        """
        output: Dict[int, Set[int]] = {}
        non_empty_roads: Set[int] = self._non_empty_roads
        for road in non_empty_roads:
            if road in self._intersections:
                intersecting_roads = self._intersections[road].intersection(non_empty_roads)
                if intersecting_roads:
                    output[road] = intersecting_roads
        return output

    def init_gui(self) -> None:
        """ Initializes the GUI and updates the display """
        if not self._gui:
            self._gui = Window(self)
        self._gui.update()

    def _loop(self, n: int) -> None:
        """ Performs n simulation updates. Terminates early upon completion or GUI closing"""
        for _ in range(n):
            self.update()
            if self.completed or self.gui_closed:
                return

    def run(self, action: None, n: int = 200) -> None:
        """ Performs n simulation updates. Terminates early upon completion or GUI closing
        :param n: the number of simulation updates to perform, 200 by default
        :param action: an action from a reinforcement learning environment action space
        """
        if action:
            self._update_signals()
            self._loop(200)
            if self.completed or self.gui_closed:
                return
            self._update_signals()
        self._loop(n)  # Todo: set 100 for fixed cycle

    def get_average_wait_time(self) -> float:
        """ Returns the average wait time of vehicles
        that completed the journey and aren't on the map """
        if not self._waiting_times:
            return 0
        return mean(self._waiting_times)

    def detect_collisions(self) -> None:
        """ Detects collisions by checking all non-empty intersecting vehicle paths.
        Updates the self.collision_detected attribute """
        radius = 2
        for main_road, intersecting_roads in self.intersections.items():
            vehicles = self.roads[main_road].vehicles
            intersecting_vehicles = chain.from_iterable(
                self.roads[i].vehicles for i in intersecting_roads)
            for vehicle in vehicles:
                for intersecting in intersecting_vehicles:
                    if distance.euclidean(vehicle.position, intersecting.position) < radius:
                        self.collision_detected = True
                        return

    def add_intersections(self, intersections_dict: Dict[int, Set[int]]) -> None:
        self._intersections |= intersections_dict

    def add_road(self, start: int, end: int) -> None:
        road = Road(start, end, index=len(self.roads))
        self.roads.append(road)

    def add_roads(self, roads: List[Tuple[int, int]]) -> None:
        for road in roads:
            self.add_road(*road)

    def add_generator(self, vehicle_rate, paths: List[List]) -> None:
        inbound_roads: List[Road] = [self.roads[roads[0]] for weight, roads in paths]
        inbound_dict: Dict[int: Road] = {road.index: road for road in inbound_roads}
        vehicle_generator = VehicleGenerator(vehicle_rate, paths, inbound_dict)
        self.generators.append(vehicle_generator)

    def add_traffic_signal(self, roads: List[List[int]], cycle: List[Tuple],
                           slow_distance: float, slow_factor: float, stop_distance: float) -> None:
        roads: List[List[Road]] = [[self.roads[i] for i in road_group] for road_group in roads]
        traffic_signal = TrafficSignal(roads, cycle, slow_distance, slow_factor, stop_distance)
        self.traffic_signals.append(traffic_signal)

    def _update_signals(self) -> None:
        for traffic_signal in self.traffic_signals:
            traffic_signal.update()

    def update(self) -> None:
        # Update every road
        for i in self._non_empty_roads:
            self.roads[i].update(self.dt, self.t)

        # Add vehicles
        for gen in self.generators:
            if self._max_gen and self.n_vehicles_generated == self._max_gen:
                break
            road_index = gen.update(self.t, self.n_vehicles_generated)
            if road_index is not None:
                self.n_vehicles_generated += 1
                self.n_vehicles_on_map += 1
                self._non_empty_roads.add(road_index)

        # Check roads for out-of-bounds vehicle
        new_non_empty_roads = set()
        empty_roads = set()
        for i in self._non_empty_roads:
            road = self.roads[i]
            lead = road.vehicles[0]
            # If first vehicle is out of road bounds
            if lead.x >= road.length:
                # If vehicle has a next road
                if lead.current_road_index + 1 < len(lead.path):
                    # Update current road to next road
                    lead.current_road_index += 1
                    # Create a copy and reset some vehicle properties
                    new_vehicle = deepcopy(lead)
                    new_vehicle.x = 0
                    # Add it to the next road
                    next_road_index = lead.path[lead.current_road_index]
                    new_non_empty_roads.add(next_road_index)
                    self.roads[next_road_index].vehicles.append(new_vehicle)
                    # Remove it from its road
                    road.vehicles.popleft()
                    if not road.vehicles:
                        empty_roads.add(road.index)
                else:
                    # Remove it from its road
                    removed_vehicle = road.vehicles.popleft()
                    # Remove from non_empty_roads if it has no vehicles
                    if not road.vehicles:
                        empty_roads.add(road.index)
                    self.n_vehicles_on_map -= 1
                    # Update the log
                    wait_time = removed_vehicle.get_total_waiting_time(self.t)
                    self._waiting_times.append(wait_time)

        self._non_empty_roads -= empty_roads
        self._non_empty_roads |= new_non_empty_roads
        self.detect_collisions()

        # Increment time
        self.t += self.dt

        # Update the display
        if self._gui:
            self._gui.update()
