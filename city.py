import socket
import threading
import time
import math
from contextlib import closing
import queue
import multiprocessing

class City:
    def __init__(self, city_id, neighbours, coordinates, port):
        self.city_id = city_id
        self.neighbours = neighbours
        self.coordinates = coordinates
        self.port = port
        self.data = str(city_id)
        self.data_lock = threading.Lock()
        self.visited = set()
        self.distance = {neighbour: float('inf') for neighbour in neighbours}  # Distance to other cities
        self.distance[city_id] = 0  # Distance to itself is 0
        self.distance_lock = threading.Lock()
        self.distance_updated = multiprocessing.Event()
        self.manager = multiprocessing.Manager()
        self.bfs_queue = self.manager.Queue()

        # Initialize distances between cities
        for neighbour in neighbours:
            self.distance[neighbour] = self.calculate_distance(city_id, neighbour)

    def calculate_distance(self, city1, city2):
        lat1, lon1 = self.coordinates[city1]
        lat2, lon2 = self.coordinates[city2]

        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        # Haversine formula
        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = 6371 * c  # Radius of the Earth in kilometers

        return distance

    def broadcast(self):
        for neighbour in self.neighbours:
            if neighbour != self.city_id and neighbour not in self.visited:
                self.send_data(neighbour)

    def send_data(self, neighbour):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.connect((f'city_{neighbour}', 8000))
            with self.data_lock:
                if neighbour not in self.visited:
                    sock.send(str(self.city_id).encode())
                    self.visited.add(neighbour)

    def handle_client(self, client_socket, addr):
        request = client_socket.recv(1024)
        with self.data_lock:
            self.data += request.decode()
            print(f"City {self.city_id}: Accepted connection from {addr[0]}:{addr[1]}")
            print(f"City {self.city_id}: Updated data {self.data}")
        self.visited.add(self.city_id)  # Add current city to the visited set
        self.broadcast()
        client_socket.close()

    def bfs(self):
        while True:
            try:
                neighbour, distance = self.bfs_queue.get(timeout=1)
                if distance < self.distance[neighbour]:
                    self.update_distance(neighbour, distance)
                    for next_neighbour in self.neighbours:
                        if next_neighbour != self.city_id and next_neighbour not in self.visited:
                            self.bfs_queue.put((next_neighbour, distance + 1))
                self.bfs_queue.task_done()
            except queue.Empty:
                break

    def update_distance(self, neighbour, distance):
        with self.distance_lock:
            if distance < self.distance[neighbour]:
                self.distance[neighbour] = distance
                self.distance_updated.set()

    def run_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('0.0.0.0', self.port))
        server.listen(5)
        print(f"City {self.city_id}: Listening")
        while True:
            client, addr = server.accept()
            client_handler = threading.Thread(target=self.handle_client, args=(client, addr))
            client_handler.start()

    def run(self):
        server_thread = threading.Thread(target=self.run_server)
        server_thread.start()
        time.sleep(5)
        self.broadcast()

        # Start parallel BFS processes
        bfs_processes = []
        for _ in range(multiprocessing.cpu_count()):
            process = multiprocessing.Process(target=self.bfs)
            bfs_processes.append(process)
            process.start()

        for neighbour in self.neighbours:
            if neighbour != self.city_id:
                self.bfs_queue.put((neighbour, self.distance[self.city_id] + 1))

        self.bfs_queue.join()  # Wait for all BFS tasks to complete

        for process in bfs_processes:
            process.terminate()

        # Show distance between cities
        sorted_distances = sorted(self.distance.items(), key=lambda x: x[0])
        print(f"City {self.city_id}: Distance to other cities")
        total_distance = 0
        for neighbour, distance in sorted_distances:
            print(f"Received from City {neighbour}: {distance} km")
            if neighbour != self.city_id:
                total_distance += distance

        # Show final data of the city
        print(f"City {self.city_id}: Final data {self.data}")

        # Show total distance
        print(f"City {self.city_id}: Total Distance: {total_distance} km")


if __name__ == "__main__":
    import sys

    city_id = int(sys.argv[1])
    neighbours = list(map(int, sys.argv[2:]))
    coordinates = {
        1: (13.7563, 100.5018),  # Bangkok
        2: (51.5074, -0.1278),   # London
        3: (40.7128, -74.0060),  # New York
        4: (-33.8688, 151.2093)  # Sydney
    }

    city = City(city_id, neighbours, coordinates, 8000)
    city.run()

