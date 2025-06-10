import threading
import time
import random
import os
from dataclasses import dataclass
from typing import List, Tuple, Set, Optional
from enum import Enum
from collections import deque

class SimulationState(Enum):
    NORMAL = "normal"
    EVAC = "evacuando"
    FINISHED = "finalizado"

@dataclass
class Position:
    x: int
    y: int
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))
    
    def distance_to(self, other: 'Position') -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)

class Door:
    def __init__(self, position: Position, id: int):
        self.position = position
        self.id = id
        self.evacuated_people = 0
        self.evacuated_list = []
        self.lock = threading.Lock()
    
    def evacuate_person(self, person_id: int):
        with self.lock:
            self.evacuated_people += 1
            self.evacuated_list.append(person_id)
            print(f"🚪 Pessoa {person_id} evacuada pela porta {self.id}")

class Environment:
    def __init__(self, width: int, height: int, num_people: int, num_doors: int, time_limit: int):
        self.width = width
        self.height = height
        self.num_people = num_people
        self.num_doors = num_doors
        self.time_limit = time_limit
        
        self.state = SimulationState.NORMAL
        self.state_lock = threading.Lock()
        
        self.occupied_positions: Set[Position] = set()
        self.position_lock = threading.Lock()
        
        self.people: List['Person'] = []
        self.doors: List[Door] = []
        self.people_threads: List[threading.Thread] = []
        self.running = True
        
        self.total_evacuated = 0
        self.stats_lock = threading.Lock()
        self.evacuation_logs = []
        self.log_lock = threading.Lock()
        
        self._setup_doors()
        self._setup_people()
    
    def _setup_doors(self):
        possible_positions = []
        
        for x in range(1, self.width - 1):
            possible_positions.extend([Position(x, 0), Position(x, self.height - 1)])
        
        for y in range(1, self.height - 1):
            possible_positions.extend([Position(0, y), Position(self.width - 1, y)])
        
        selected_positions = random.sample(possible_positions, min(self.num_doors, len(possible_positions)))
        
        for i, pos in enumerate(selected_positions):
            door = Door(pos, i + 1)
            self.doors.append(door)
            self.occupied_positions.add(pos)
    
    def _setup_people(self):
        for i in range(self.num_people):
            position = self._get_random_free_position()
            if position:
                person = Person(i + 1, position, self)
                self.people.append(person)
                self.occupied_positions.add(position)
    
    def _get_random_free_position(self) -> Optional[Position]:
        max_attempts = 100
        attempts = 0
        
        while attempts < max_attempts:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            pos = Position(x, y)
            
            if pos not in self.occupied_positions:
                return pos
            
            attempts += 1
        
        return None
    
    def get_state(self) -> SimulationState:
        with self.state_lock:
            return self.state
    
    def set_state(self, new_state: SimulationState):
        with self.state_lock:
            self.state = new_state
    
    def is_position_free(self, position: Position) -> bool:
        with self.position_lock:
            return position not in self.occupied_positions
    
    def move_person(self, person_id: int, old_pos: Position, new_pos: Position) -> bool:
        with self.position_lock:
            if new_pos in self.occupied_positions:
                return False
            
            self.occupied_positions.remove(old_pos)
            self.occupied_positions.add(new_pos)
            return True
    
    def remove_person(self, position: Position):
        with self.position_lock:
            if position in self.occupied_positions:
                self.occupied_positions.remove(position)
    
    def find_best_door_and_path(self, position: Position) -> Tuple[Optional[Door], List[Position]]:
        best_door = None
        best_path = []
        shortest_distance = float('inf')
        
        for door in self.doors:
            path = self._find_path(position, door.position)
            if path and len(path) < shortest_distance:
                shortest_distance = len(path)
                best_door = door
                best_path = path
        
        return best_door, best_path
    
    def _find_path(self, start: Position, end: Position) -> List[Position]:
        if start == end:
            return []
        
        queue = deque([(start, [])])
        visited = {start}
        
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        max_iterations = 500
        iterations = 0
        
        while queue and iterations < max_iterations:
            iterations += 1
            current, path = queue.popleft()
            
            for dx, dy in directions:
                new_x = current.x + dx
                new_y = current.y + dy
                new_pos = Position(new_x, new_y)
                
                if new_pos == end:
                    return path + [new_pos]
                
                if (0 <= new_x < self.width and 0 <= new_y < self.height and
                    new_pos not in visited):
                    
                    if (new_pos == end or 
                        (1 <= new_x < self.width - 1 and 1 <= new_y < self.height - 1 and 
                         self.is_position_free(new_pos))):
                        
                        visited.add(new_pos)
                        queue.append((new_pos, path + [new_pos]))
        
        return []
    
    def add_evacuation_log(self, person_id: int, door_id: int):
        with self.log_lock:
            self.evacuation_logs.append(f"Pessoa {person_id} → Porta {door_id}")
    
    def increment_evacuated(self):
        with self.stats_lock:
            self.total_evacuated += 1
    
    def start_simulation(self):
        print(f"🏢 Iniciando simulação:")
        print(f"   Ambiente: {self.width}x{self.height}")
        print(f"   Pessoas: {self.num_people}")
        print(f"   Portas: {self.num_doors}")
        print(f"   Tempo limite: {self.time_limit}s")
        print(f"   Posições das portas: {[(d.position.x, d.position.y) for d in self.doors]}")
        print()
        
        for person in self.people:
            thread = threading.Thread(target=person.run)
            self.people_threads.append(thread)
            thread.start()
        
        status_thread = threading.Thread(target=self._status_monitor)
        status_thread.start()
        
        time.sleep(self.time_limit)
        
        self.set_state(SimulationState.EVAC)
        print(f"\n🚨 EVACUAÇÃO INICIADA! Tempo limite atingido.")

        evacuation_timeout = 30
        start_time = time.time()
        
        while (self.total_evacuated < self.num_people and 
               time.time() - start_time < evacuation_timeout):
            time.sleep(0.5)
        
        self.running = False
        self.set_state(SimulationState.FINISHED)
        
        for thread in self.people_threads:
            thread.join(timeout=2)
        
        status_thread.join(timeout=2)
        
        self._print_final_stats()
    
    def _status_monitor(self):
        while self.running and self.get_state() != SimulationState.FINISHED:
            self._clear_screen()
            self._print_environment()
            time.sleep(1)
    
    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _print_environment(self):
        print(f"Estado: {self.get_state().value.upper()}")
        print(f"Evacuados: {self.total_evacuated}/{self.num_people}")
        print()
        
        grid = [['⬜' for _ in range(self.width)] for _ in range(self.height)]
        
        for x in range(self.width):
            grid[0][x] = '⬛'
            grid[self.height-1][x] = '⬛'
        for y in range(self.height):
            grid[y][0] = '⬛'
            grid[y][self.width-1] = '⬛'
        
        for door in self.doors:
            grid[door.position.y][door.position.x] = f'🚪'
        
        with self.position_lock:
            for pos in self.occupied_positions:
                if pos not in [door.position for door in self.doors]:
                    if 0 <= pos.y < self.height and 0 <= pos.x < self.width:
                        grid[pos.y][pos.x] = '👤'
        
        for row in grid:
            print(' '.join(row))
        
        print()
        for door in self.doors:
            print(f"Porta {door.id}: {door.evacuated_people} pessoas evacuadas")
        
        with self.log_lock:
            if self.evacuation_logs:
                print("\n📝 Últimas evacuações:")
                for log in self.evacuation_logs[-5:]:
                    print(f"   {log}")
    
    def _print_final_stats(self):
        print(f"\n{'='*50}")
        print(f"SIMULAÇÃO FINALIZADA")
        print(f"{'='*50}")
        print(f"Total de pessoas: {self.num_people}")
        print(f"Pessoas evacuadas: {self.total_evacuated}")
        print(f"Taxa de evacuação: {(self.total_evacuated/self.num_people)*100:.1f}%")
        print()
        
        print("📊 Evacuação por porta:")
        for door in self.doors:
            print(f"  Porta {door.id}: {door.evacuated_people} pessoas")
            if door.evacuated_list:
                people_str = ", ".join(map(str, door.evacuated_list))
                print(f"    └─ Pessoas: {people_str}")
        
        print("\n📝 Histórico completo de evacuações:")
        with self.log_lock:
            for log in self.evacuation_logs:
                print(f"   {log}")

class Person:
    def __init__(self, id: int, position: Position, environment: Environment):
        self.id = id
        self.position = position
        self.environment = environment
        self.move_delay = random.uniform(0.5, 1.5)
        self.current_path = []
        self.target_door = None
    
    def run(self):
        while self.environment.running:
            state = self.environment.get_state()
            
            if state == SimulationState.NORMAL:
                self._random_movement()
            elif state == SimulationState.EVAC:
                if self._evacuate():
                    break
            elif state == SimulationState.FINISHED:
                break
            
            time.sleep(self.move_delay)
    
    def _random_movement(self):
        possible_moves = self._get_possible_moves()
        if possible_moves:
            new_position = random.choice(possible_moves)
            if self.environment.move_person(self.id, self.position, new_position):
                self.position = new_position
    
    def _evacuate(self) -> bool:
        if not self.current_path or not self.target_door:
            self.target_door, self.current_path = self.environment.find_best_door_and_path(self.position)
            
            if not self.target_door or not self.current_path:
                return False
        
        if self.current_path and self.position.distance_to(self.current_path[0]) == 1:
            next_position = self.current_path.pop(0)
            
            if next_position == self.target_door.position:
                self.environment.remove_person(self.position)
                self.target_door.evacuate_person(self.id)
                self.environment.add_evacuation_log(self.id, self.target_door.id)
                self.environment.increment_evacuated()
                return True
            
            if self.environment.move_person(self.id, self.position, next_position):
                self.position = next_position
            else:
                self.current_path = []
                self.target_door = None
        else:
            self.current_path = []
            self.target_door = None
        
        return False
    
    def _get_possible_moves(self) -> List[Position]:
        moves = []
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        
        for dx, dy in directions:
            new_x = self.position.x + dx
            new_y = self.position.y + dy
            
            if (1 <= new_x < self.environment.width - 1 and 
                1 <= new_y < self.environment.height - 1):
                
                new_pos = Position(new_x, new_y)
                if self.environment.is_position_free(new_pos):
                    moves.append(new_pos)
        
        return moves

def main():
    print("=== SIMULAÇÃO DE EVACUAÇÃO COM THREADS ===\n")
    
    try:
        width = int(input("Largura do ambiente (mínimo 10): ") or "15")
        height = int(input("Altura do ambiente (mínimo 10): ") or "10")
        num_people = int(input("Número de pessoas (máximo 20): ") or "8")
        num_doors = int(input("Número de portas (mínimo 2): ") or "3")
        time_limit = int(input("Tempo limite em segundos (antes da evacuação): ") or "10")
        
        width = max(10, width)
        height = max(10, height)
        num_people = min(20, max(1, num_people))
        num_doors = max(2, min(num_doors, (width + height - 4) * 2))
        time_limit = max(5, time_limit)
        
        print(f"\nParâmetros confirmados:")
        print(f"Ambiente: {width}x{height}")
        print(f"Pessoas: {num_people}")
        print(f"Portas: {num_doors}")
        print(f"Tempo limite: {time_limit}s")
        
        input("\nPressione Enter para iniciar...")
        
        environment = Environment(width, height, num_people, num_doors, time_limit)
        environment.start_simulation()
        
    except KeyboardInterrupt:
        print("\n\nSimulação interrompida pelo usuário.")
    except Exception as e:
        print(f"\nErro durante a simulação: {e}")

if __name__ == "__main__":
    main()