#Permite criar e controlar múltiplas threads(linhas de código) (pessoas) simultaneamente
import threading

# Provê funcçoes relacionadas a medida e tempo, como a espera das pessoas para
# poderem encontrar a saída
import time

#Permite usar funções para gerar números aleatórios. Neste projeto é usado para
#posicionar as "pessoas" e/ou decidir o tempo de espera de cada thread da "pessoa"
import random

#Dá acesso a operações do sistema operacional, como limpar a tela do terminal 
import os

#Importa o decorador @dataclass, que facilita a definição de classes cujos objetos
#simplesmente armazenam dados, em vez de serem escritas manualmente, gerando automaticamente
#este código
from dataclasses import dataclass

#List[int] diz “espera-se uma lista de inteiros”, por exemplo.  
#Tuple[X, Y] indica uma tupla com dois elementos, do tipo X e Y.  
#Set[T] indica um conjunto de objetos do tipo T.  
#Optional[T] significa “ou T, ou None” (quando algo pode não existir).
from typing import List, Tuple, Set, Optional

#Importa a classe base Enum, que permite definir conjuntos de constantes nomeadas.
#É usada para representar estados como, NORMLA, EVC, FINISHED.
from enum import Enum

#Traz a estrutura de dados deque, otimizada para enfileirr e desenfileirar em ambas as pontas.
from collections import deque

#Em vez de usar números ou strings “soltas” para representar estados da simulação,
#usa-se esse Enum para garantir que só existam exatamente esses três estados possíveis.  
#Em várias partes do código, testamos if state == SimulationState.NORMAL: ou
#if state == SimulationState.EVAC:, etc., tornando o código mais claro.
class SimulationState(Enum):
    NORMAL = "normal"
    EVAC = "evacuando"
    FINISHED = "finalizado"

#vai gerar automaticamente métodos
#Atributos x e y  
#Representam as coordenadas de um ponto no ambiente bidimensional.  
@dataclass
class Position:
    x: int
    y: int
    
    #Define como o Python verifica se duas instâncias de Position são “iguais”.
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    
    #Permite que objetos Position sejam usados como chaves em um set ou em um dicionário (dict).  
    #Isso é importante porque queremos armazenar, por exemplo, quais posições estão ocupadas em um Set[Position].  
    #O hash((self.x, self.y)) transforma a tupla (x, y) em um valor inteiro que identifica unicamente aquela posição.
    def __hash__(self):
        return hash((self.x, self.y))
    
    #Retorna a distância de Manhattan entre as posições
    #Serve para saber “quão longe” está uma pessoa de uma porta, aproximando quem está mais próximo.
    def distance_to(self, other: 'Position') -> int:
        return abs(self.x - other.x) + abs(self.y - other.y)


class Door:
    #Armazena a posição da porta no ambiente.
    #Cada porta recebe um identificador inteiro único, para sabermos qual porta foi usada para evacuar cada pessoa.
    def __init__(self, position: Position, id: int):
        self.position = position
        self.id = id
        #Contador de quantas pessoas já passaram por esta porta.
        self.evacuated_people = 0
        #Lista que armazena o ID de cada pessoa que passou por esta porta, na ordem em que foram evacuadas.
        self.evacuated_list = []
        #Garante que, quando uma thread estiver executando , nenhuma outra thread possa modificar os mesmos dados ao mesmo tempo, 
        self.lock = threading.Lock()
    
    def evacuate_person(self, person_id: int):
        #Abre um bloco crítico: somente uma thread por vez pode entrar aqui. Se outra thread já estiver dentro desse bloco,
        #a nova aguardará até que a primeira saia.
        with self.lock:
            #Incrementa em 1 o contador de pessoas que saíram por esta porta
            self.evacuated_people += 1
            #Adiciona o identificador da pessoa à lista de evacuação desta porta
            self.evacuated_list.append(person_id)
            #Mostra no terminal uma mensagem informando qual pessoa e qual porta
            print(f"🚪 Pessoa {person_id} evacuada pela porta {self.id}")

#Modela todo o ambiente retangular, portas, pessoas, gerencia posições ocupadas e controla o fluxo da simulação 
class Environment:

    #Parâmetros de entrada
    def __init__(self, width: int, height: int, num_people: int, num_doors: int, time_limit: int):

        #Atributos de configuração
        self.width = width
        self.height = height
        self.num_people = num_people
        self.num_doors = num_doors
        self.time_limit = time_limit
        
        #Estado inicial da simulação: NORMAL, isto é, antes de iniciar a evacuação, as pessoas apenas vagueiam aleatoriamente
        self.state = SimulationState.NORMAL
        #Garante consistência, trancando para proteger leituras, já que várias threads estão sendo executadas ao mesmo tempo
        self.state_lock = threading.Lock()
        
        #Conjunto de posições que estão ocupadas no momento (portas/pessoas) e checa se as posições estão ocupadas ou livres
        self.occupied_positions: Set[Position] = set()
        #Tranca para proteger alterações nesse conjunto de occupied_positions, já que várias threads podem tentar mover-se simultaneamente.
        self.position_lock = threading.Lock()
        
        #Ficará com referências a todos os objetos Person criados.  
        self.people: List[Person] = []
        #Ficará com referências a todos os objetos Portas.  
        self.doors: List[Door] = []
        #Lista dos objetos que representa cada pessoa na execução
        self.people_threads: List[threading.Thread] = []
        #Indicar se a simulação está rodando ou não. Quando for definida para False, as threads de pessoas vão parar de funcionar.
        self.running = True
        
        #Contador global de quantas pessoas já saíram pelo menos por alguma porta.
        self.total_evacuated = 0
        #Tranca para proteger acesso a total_evacuated, pois várias threads podem incrementar ao mesmo tempo.  
        self.stats_lock = threading.Lock()
        #Lista de strings que registra cada evacuação, para imprimir “histórico” no final.  
        self.evacuation_logs = []
        #Tranca para proteger escrita nessa lista
        self.log_lock = threading.Lock()
        
        #Método interno que posiciona as portas e marca essas posições como ocupadas.  
        self._setup_doors()
        #Método interno que aloca posições livres para cada pessoa, cria cada objeto Person e marca essas posições como ocupadas.
        self._setup_people()
    
    def _setup_doors(self):
        #Cria uma lista vazia onde guardaremos todas as possíveis posições válidas para portas,isto é,
        #todas as células que estão nas bordas do grid, exceto os cantos
        possible_positions = []
        
        #Loop para bordas superior e inferior
        #Assim, estamos enumerando as posições intermediárias das duas bordas horizontais, sem os cantos.
        for x in range(1, self.width - 1):
            possible_positions.extend([Position(x, 0), Position(x, self.height - 1)])
        
        #Loop para bordas esquerda e direita
        #Assim, cobrimos as posições intermediárias nas bordas verticais, sem os cantos
        for y in range(1, self.height - 1):
            possible_positions.extend([Position(0, y), Position(self.width - 1, y)])
        
        #Escolha aleatória da posição das portas
        #Lista com posições ondde as portas serão colocadas
        selected_positions = random.sample(possible_positions, min(self.num_doors, len(possible_positions)))
        
        #Criação dos objetos Door
        for i, pos in enumerate(selected_positions):
            door = Door(pos, i + 1)
            self.doors.append(door)
            #Marca a posição pos como ocupada, para que nenhuma pessoa possa nascer ou se mover para ali.
            self.occupied_positions.add(pos)
    
    #Posiciona um número definido de pessoas em locais aleatórios e livres dentro de um ambiente (como um cubo),
    #criando objetos Person para cada uma, e marcando essas posições como ocupadas.
    def _setup_people(self):
        for i in range(self.num_people):
            position = self._get_random_free_position()
            if position:
                person = Person(i + 1, position, self)
                self.people.append(person)
                self.occupied_positions.add(position)
    
    #Esse método busca, aleatoriamente, uma posição livre dentro do interior do grid (não nas bordas).  
    def _get_random_free_position(self) -> Optional[Position]:
        #Define um limite de tentativas para evitar entrar em loop infinito caso o grid esteja muito lotado.
        max_attempts = 100
        attempts = 0
        
        #Se achar uma posição livre, retorna um objeto Position; caso falhe (após 100 tentativas), retorna None.
        while attempts < max_attempts:
            x = random.randint(1, self.width - 2)
            y = random.randint(1, self.height - 2)
            #Cria um objeto de posição com as coordenadas sorteadas.
            pos = Position(x, y)
            
            #Adiciona a posição ao conjunto self.occupied_positions, marcando que agora uma pessoa ocupa aquela célula.
            #Se estava ocupada, tentamos novamente até atingir o limite de 100.
            if pos not in self.occupied_positions:
                return pos
            
            attempts += 1
        
        return None
    
    #Retorna o estado da simulação
    def get_state(self) -> SimulationState:
        with self.state_lock:
            return self.state
    
    #Define o estado da simulação
    def set_state(self, new_state: SimulationState):
        with self.state_lock:
            self.state = new_state
    
    #Serve para verificar de forma segura (sincronizada) se uma dada posição (x, y) está livre (pode ser ocupada por 
    #uma pessoa que queira se mover para lá).  
    def is_position_free(self, position: Position) -> bool:
        with self.position_lock:
            return position not in self.occupied_positions
    
    #Serve para mover a pessoa.
    #Se a nova posição estiver ocupada, a movimentação falha, se estiver livre ele remove a posição antiga e adiciona a nova.
    def move_person(self, person_id: int, old_pos: Position, new_pos: Position) -> bool:
        #Garante que todo o processo de verificar “livre” e “atualizar conjuntos” seja atômico, sem interferência de outra thread.
        with self.position_lock:
            #Se new_pos estiver em occupied_positions, significa que já há algo (pessoa ou porta) lá.
            if new_pos in self.occupied_positions:
                return False
            
            #Retira old_pos (posição antiga da pessoa) e insere new_pos, se o mesmo não estiver em occupied_positions.
            self.occupied_positions.remove(old_pos)
            self.occupied_positions.add(new_pos)
            return True
    
    #Quando uma pessoa alcança a porta e é evacuada, qremove aquela posição do conjunto de ocupadas, 
    #pois agora essa célula deixará de estar ocupada pela pessoa.  
    def remove_person(self, position: Position):
        with self.position_lock:
            if position in self.occupied_positions:
                self.occupied_positions.remove(position)
    
    #Loczaliza a porta mais próxima da pessoa, buscando sempre o menor caminho
    def find_best_door_and_path(self, position: Position) -> Tuple[Optional[Door], List[Position]]:
        best_door = None
        best_path = []
        shortest_distance = float('inf')
        
        #Itera por todas as portas criadas em _setup_doors. Para cada porta, chama _find_path(start, end) para calcular um caminho viável.
        for door in self.doors:
            path = self._find_path(position, door.position)
            #Verificar se path existe e é mais curto que o já encontrado  
            if path and len(path) < shortest_distance:
                shortest_distance = len(path)
                best_door = door
                best_path = path

        #Se não achou caminho para nenhuma porta, best_door fica None e best_path vazio.  
        #Caso contrário, ambos apontam para a solução ótima (distância mínima).
        return best_door, best_path
    
    def _find_path(self, start: Position, end: Position) -> List[Position]:
        #Se a posição inicial é exatamente a posição da porta desejada (caso raro, pois portas ficam nas bordas e pessoas dentro),
        #retornamos lista vazia de passos, pois não precisamos nos mover.
        if start == end:
            return []
        
        #A fila (queue) contém tuplas (posição_atual, caminho_percorrido_ate_agora).  
        #Começamos com (start, []): ainda não percorremos nenhum passo, caminho vazio.  
        #visited começa com {start}, para não revisitarmos a mesma célula.
        queue = deque([(start, [])])
        visited = {start}
        
        #Direções possíveis
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        #Limite de iterações
        max_iterations = 500
        iterations = 0
        
        #A cada passo, incrementamos iterations. 
        while queue and iterations < max_iterations:
            iterations += 1
            current, path = queue.popleft()
            
            #Calculamos as coordenadas de new_pos, vizinho de current
            for dx, dy in directions:
                new_x = current.x + dx
                new_y = current.y + dy
                new_pos = Position(new_x, new_y)
                
                #Se new_pos for exatamente a porta end  
                #Retornamos imediatamente o caminho atual concatenado com new_pos.
                #Isto fornece a primeira solução mais curta possível (porque BFS garanta que exploramos em “camadas”)
                if new_pos == end:
                    return path + [new_pos]
                
                #Primeiro, testamos se as coordenadas estão dentro do grid (ou seja, não estamos “fora” do ambiente).  
                #E se new_pos ainda não foi visitada (evita laços infinitos).
                if (0 <= new_x < self.width and 0 <= new_y < self.height and
                    new_pos not in visited):
                    
                    #Garante que new_pos está dentro do interior, pois não queremos que uma pessoa caminhe por fora dos limites ou encoste nas paredes.  
                    if (new_pos == end or 
                        (1 <= new_x < self.width - 1 and 1 <= new_y < self.height - 1 and 
                        #Verifica se não há outra pessoa ou porta (exceto a porta de destino) ocupando essa posição.  
                        #Se ambas condições forem atendidas, consideramos new_pos como um vizinho válido a ser colocado na fila.
                         self.is_position_free(new_pos))):
                        
                        
                        visited.add(new_pos)
                        queue.append((new_pos, path + [new_pos]))
        
        #Retornamos lista vazia, indicando “não foi possível achar um caminho viável” (pessoa presa, área muito lotada, etc).
        return []
    
    #add_evacuation_log e increment_evacuated são chamados quando uma pessoa efetivamente chega numa porta e se “evacua”. Eles permitem acompanhar quem evacuou, por qual porta, e quantas pessoas já se foram.
    def add_evacuation_log(self, person_id: int, door_id: int):
        #Garantir que duas threads não escrevam simultaneamente na lista.
        with self.log_lock:
            self.evacuation_logs.append(f"Pessoa {person_id} → Porta {door_id}")
    
    
    #Apenas incrementa em 1 o contador global self.total_evacuated
    def increment_evacuated(self):
        with self.stats_lock:
            self.total_evacuated += 1
    
    def start_simulation(self):
        
        #Exibe no terminal informações como:  
        #Dimensões do ambiente (width x height).  
        #Quantidade de pessoas.  
        #Quantidade de portas.  
        #Tempo limite antes de começar evacuação.  
        #Coordenadas de cada porta (lista de tuplas (x, y)).
        print(f"🏢 Iniciando simulação:")
        print(f"   Ambiente: {self.width}x{self.height}")
        print(f"   Pessoas: {self.num_people}")
        print(f"   Portas: {self.num_doors}")
        print(f"   Tempo limite: {self.time_limit}s")
        print(f"   Posições das portas: {[(d.position.x, d.position.y) for d in self.doors]}")
        print()
        
        #Criação de threads para cada pessoa
        for person in self.people:
            thread = threading.Thread(target=person.run)
            self.people_threads.append(thread)
            thread.start()
        
        #Criação de thread de monitoramento de status
        #Limpa a tela e imprime o “mapa” do ambiente, mostrando posições de pessoas, portas, logs de evacuação parciais etc.
        #Ela roda em paralelo às threads das pessoas para atualizar a visualização a cada segundo.
        status_thread = threading.Thread(target=self._status_monitor)
        status_thread.start()
        
        #Aguardar time_limit segundos antes de iniciar evacuação
        time.sleep(self.time_limit)
        
        #Trocar estado para EVAC
        self.set_state(SimulationState.EVAC)
        print(f"\n🚨 EVACUAÇÃO INICIADA! Tempo limite atingido.")

        #Espera para terminar evacuação ou tempo extra esgotar
        #Definimos um tempo adicional de até 30 segundos (evacuation_timeout) para que todas as pessoas tenham chance de fugir após a ordem de evacuação. 
        evacuation_timeout = 30
        start_time = time.time()
        
        #Continuamos em loop (que dorme 0.5s por iteração para não consumir CPU demais) enquanto:
        #self.total_evacuated < self.num_people (há ainda pessoas dentro).
        #- E ainda não se passaram 30 segundos desde start_time.  
        #Quando uma dessas condições falhar (todas evacuadas ou 30s passarem), saímos do loop.
        while (self.total_evacuated < self.num_people and 
               time.time() - start_time < evacuation_timeout):
            time.sleep(0.5)
        
        #Parar as threads e fixar estado final
        self.running = False
        self.set_state(SimulationState.FINISHED)
        
        
        #thread.join() faz a thread principal (que está executando start_simulation) aguardar até que cada thread de pessoa termine.  
        #O timeout=2 significa que, se a thread não terminar em 2 segundos, prosseguimos mesmo assim.
        for thread in self.people_threads:
            thread.join(timeout=2)
        
        #- Mesma ideia: aguardamos até 2 segundos para a thread de monitor de status parar.  
        #Quando self.running = False e state == FINISHED, o método _status_monitor sai de seu loop e encerra.
        status_thread.join(timeout=2)
        
        #Imprimir estatísticas finais
        #Chama método que formata e exibe informações sobre quantas pessoas foram evacuadas, taxa de sucesso, quantas por cada porta, lista completa de logs etc.
        self._print_final_stats()
    
    def _status_monitor(self):
        #Loop que roda enquanto a simulação estiver em progresso  
        #Quando a simulação termina (todas evacuadas ou timeout), atribuiremos self.running = False no start_simulation e também colocaremos state = FINISHED.
        #Esse loop rodará a cada 1 segundo (time.sleep(1)), fazendo dois passos:
        while self.running and self.get_state() != SimulationState.FINISHED:
            #Limpa o terminal para desenhar tudo de novo.
            self._clear_screen()
            #Desenha o estado atual do grid (mapa), mostrando paredes, portas, pessoas, e algumas estatísticas no terminal.
            #Faz isso de forma textual, utilizando emojis para representar cada célula
            self._print_environment()
            #Aguarda 1 segundo antes de limpar e imprimir de novo.
            #Paralelamente, pessoas continuam se movendo (em threads separadas).
            time.sleep(1)
    
    #Limpa o terminal  
    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _print_environment(self):
        #Mostra o estado atual 
        print(f"Estado: {self.get_state().value.upper()}")
        #Mostra quantas pessoas já evacuaram sobre o total.  
        print(f"Evacuados: {self.total_evacuated}/{self.num_people}")
        #Linha em branco para separar impressão do grid.
        print()
        
        #Construir uma matriz 
        #Cria uma lista de listas (height linhas × width colunas), preenchida com o emoji “⬜” 
        grid = [['⬜' for _ in range(self.width)] for _ in range(self.height)]
        
        #Desenhar as paredes nas bordas com “⬛” 
        #Primeira coluna (x = 0) e última coluna (x = width-1) recebem “⬛” em todas as linhas. 
        for x in range(self.width):
            grid[0][x] = '⬛'
            grid[self.height-1][x] = '⬛'
        
         #Primeira linha (y = 0) e última linha (y = height-1) recebem “⬛” em todas as colunas, indicando parede.
        for y in range(self.height):
            grid[y][0] = '⬛'
            grid[y][self.width-1] = '⬛'
        
        #Para cada porta, substituímos o “⬜” ou “⬛”
        for door in self.doors:
            grid[door.position.y][door.position.x] = f'🚪'
        
        with self.position_lock:
            #Pergunta “para cada posição em occupied_positions, se essa posição não for de uma porta (ou seja, for uma pessoa), desenhe “👤” nessa célula.
            for pos in self.occupied_positions:
                #O teste pos not in [door.position for door in self.doors] verifica se não é uma porta (caso fosse porta, já desenhamos no passo anterior).
                if pos not in [door.position for door in self.doors]:
                    #Teste extra 0 <= pos.y < height e 0 <= pos.x < width apenas para evitar exceções caso algo estranho tenha acontecido (por segurança).
                    if 0 <= pos.y < self.height and 0 <= pos.x < self.width:
                        grid[pos.y][pos.x] = '👤'
        
        #Para cada lista row de emojis, unimos os emojis com um espaço em branco no meio e imprimimos.  
        #Isso gera um “mapa” visual de todo o ambiente.
        for row in grid:
            print(' '.join(row))
        
        #Exibir estatísticas por porta
        #Uma linha em branco e, para cada porta, mostramos quantas pessoas já passaram por ela (o contador interno de cada Door).
        print()
        for door in self.doors:
            print(f"Porta {door.id}: {door.evacuated_people} pessoas evacuadas")
        
        #Exibir os últimos 5 logs de evacuação  
        with self.log_lock:
            if self.evacuation_logs:
                #Se algum log existir, imprime título “Últimas evacuações:” e lista as últimas 5 entradas de evacuation_logs, cada uma com uma indentação extra para facilitar leitura.
                print("\n📝 Últimas evacuações:")
                for log in self.evacuation_logs[-5:]:
                    print(f"   {log}")
    
    def _print_final_stats(self):
        #Imprime uma linha de 50 sinais “=”, depois “SIMULAÇÃO FINALIZADA”, depois mais 50 “=” para destacar a seção.
        print(f"\n{'='*50}")
        print(f"SIMULAÇÃO FINALIZADA")
        print(f"{'='*50}")
        #Mostra quantas pessoas existiam no início, quantas foram evacuadas (pode ser menor que total se alguma não conseguiu sair no tempo extra), e calcula a porcentagem de evacuação com uma casa decimal.
        print(f"Total de pessoas: {self.num_people}")
        print(f"Pessoas evacuadas: {self.total_evacuated}")
        print(f"Taxa de evacuação: {(self.total_evacuated/self.num_people)*100:.1f}%")
        print()
        
        #Para cada porta, indica quantas pessoas passaram por ela. 
        #Se aquela porta tem uma lista de IDs (evacuated_list) não vazia, converte essa lista em string separada por vírgulas e imprime quais IDs de pessoas usaram essa porta.
        print("📊 Evacuação por porta:")
        for door in self.doors:
            print(f"  Porta {door.id}: {door.evacuated_people} pessoas")
            if door.evacuated_list:
                people_str = ", ".join(map(str, door.evacuated_list))
                print(f"    └─ Pessoas: {people_str}")
        
        #Exibe todas as entradas de self.evacuation_logs (cada pessoa que saiu e a porta usada), em ordem cronológica
        print("\n📝 Histórico completo de evacuações:")

        with self.log_lock:
            for log in self.evacuation_logs:
                print(f"   {log}")

#Cada instância de Person representa uma pessoa que exista no ambiente e que seja executada em sua própria thread.
#Ela carrega a lógica de movimentação aleatória (fase NORMAL) e de evacuação (fase EVAC), buscando o melhor caminho até uma porta.
class Person:
    def __init__(self, id: int, position: Position, environment: Environment):
        #Armazena o identificador desta pessoa (1, 2, 3, ...)
        self.id = id
        #Posicionamento inicial (um objeto Position) onde a pessoa “nasceu”.
        self.position = position
        #Guarda referência ao objeto Environment, para poder consultar estado, mover-se, achar portas, atualizar logs, etc.
        self.environment = environment
        #Tempo de espera (em segundos) entre cada passo de movimentação dessa pessoa. É escolhido aleatoriamente entre 0.5 e 1.5 segundos.  
        #Isso faz com que cada pessoa se mova em velocidades ligeiramente diferentes, deixando a simulação mais realista.
        self.move_delay = random.uniform(0.5, 1.5)
        #Quando começa a evacuação, a pessoa calculará um “caminho” até a porta, armazenando-o em current_path. Se estiver vazia, significa que ainda não calculou ou que precisa recalcular.
        self.current_path = []
        #armazena a referência ao objeto Door que está mirando para evacuar. Inicialmente None.
        self.target_door = None
    
    def run(self):
        #Enquanto o ambiente (Environment) estiver rodando (running == True), a pessoa continua ativa.  
        #Quando Environment definir running = False, o laço termina e o método run finaliza, encerrando a thread.
        while self.environment.running:
            #Consulta de forma segura (com lock interno) o valor de Environment.state. Pode ser NORMAL, EVAC ou FINISHED.
            state = self.environment.get_state()
            #Se estado for NORMAL :
            #Chama o método _random_movement(), que tenta mover a pessoa para um vizinho aleatório caso esteja livre.
            if state == SimulationState.NORMAL:
                self._random_movement()
            #Se estado for EVAC 
            #Chama método _evacuate(). Esse método tentará colocar a pessoa em movimento ao longo de um caminho calculado até a porta.  
            #Se _evacuate() retorna True, significa que a pessoa conseguiu chegar na porta e foi evacuada. Nesse caso, quebramos (break) o laço e terminamos a thread.
            elif state == SimulationState.EVAC:
                if self._evacuate():
                    break
            #Se estado for FINISHED
            #Caso a simulação tenha sido marcada como finalizada (por timeout geral), encerramos a thread sem tentar mover ou evacuar.
            elif state == SimulationState.FINISHED:
                break
            
            #Faz com que cada iteração (movimento aleatório ou tentativa de evacuar) ocorra após um pequeno atraso específico de cada pessoa, armazenado em self.move_delay.  
            #Isso evita que todas as pessoas se movimentem “ao mesmo tempo exato”.
            time.sleep(self.move_delay)
    
    def _random_movement(self):
        #Gerar lista de possíveis vizinhos livres
        #Retorna uma lista de objetos Position vizinhos (cima, baixo, esquerda, direita) que estejam livres (não ocupadas por outra pessoa ou porta)
        possible_moves = self._get_possible_moves()
        #Se houver ao menos um vizinho disponível
        #Selecionamos aleatoriamente (random.choice) uma das posições livres
        if possible_moves:
            new_position = random.choice(possible_moves)
            #Tentar mover a pessoa para new_position  
            if self.environment.move_person(self.id, self.position, new_position):
                self.position = new_position
    
    #Esse método gerencia a lógica de evacuação, passo a passo
    def _evacuate(self) -> bool:
        #Se ainda não calculamos caminho ou porta de destino 
        #Quando entramos na primeira vez em evacuação, current_path está vazio e target_door é None. 
        if not self.current_path or not self.target_door:
            #Chamamos find_best_door_and_path(self.position) para obter:  
            #self.target_door: a melhor porta (objeto Door) para evacuar.  
            #self.current_path: uma lista de objetos Position correspondentes ao caminho (em numero mínimo de passos).  
            self.target_door, self.current_path = self.environment.find_best_door_and_path(self.position)
            
            #Se não existirem portas acessíveis (por congestionamento), target_door será None ou current_path vazio. Nesse caso, não conseguimos evacuar, retornamos False e tentaremos de novo na próxima iteração do laço.
            if not self.target_door or not self.current_path:
                return False
        
        #Checar se o próximo passo está a uma distância de 1
        #Distance_to(...) == 1 garante que essa posição é adjacente (vizinha) à posição atual.
        if self.current_path and self.position.distance_to(self.current_path[0]) == 1:
            #Obter e remover o primeiro passo (pop)  
            next_position = self.current_path.pop(0)
            
            #Se next_position for exatamente a posição da porta significa que a pessoa está chegando à porta.
            #Chamamos self.target_door.evacuate_person(self.id), que atualiza número de pessoas daquela porta e lista de IDs, e imprime uma mensagem “Pessoa X evacuada pela porta Y”.  
            if next_position == self.target_door.position:
                self.environment.remove_person(self.position)
                self.target_door.evacuate_person(self.id)
                #Registramos no log geral (add_evacuation_log) qual pessoa e qual porta.
                #Incrementamos o contador global  
                self.environment.add_evacuation_log(self.id, self.target_door.id)
                self.environment.increment_evacuated()
                return True
            
            #Caso False, tentar efetuar o movimento para next_position  
            #Se retornar True (movimento bem-sucedido), atualizamos self.position.  
            #Se retornar False (alguém ocupou aquele espaço no instante exato), “estragamos” o caminho: atribuímos current_path = [] e target_door = None, de modo que seremos forçados a recalcular tudo na próxima chamada de _evacuate(), pois a rota está bloqueada.
            if self.environment.move_person(self.id, self.position, next_position):
                self.position = next_position
                #Significa que, por algum motivo, current_path não está sincronizado com a posição atual (talvez a pessoa tenha sido empurrada/teletransportada, ou rota ficou obsoleta).  
                #Reinicializa rota e porta, para que na próxima iteração seja requerido novo cálculo.
            else:
                self.current_path = []
                self.target_door = None
        else:
            self.current_path = []
            self.target_door = None
        
        #Se não chegamos à porta neste passo, retornamos False, o que faz com que, no laço de run(), continuemos tentando evacuar, mas a thread não encerra ainda.
        return False
    
    def _get_possible_moves(self) -> List[Position]:
        #Acumulará posições adjacentes disponíveis para mover
        moves = []
        #Direções a se mover
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        
        #Calcula coordenadas new_x, new_y de new_pos
        for dx, dy in directions:
            new_x = self.position.x + dx
            new_y = self.position.y + dy
            
            #Limitar movimento apenas ao interior (não nas bordas)
            #Se a célula vizinha está dentro da faixa [1, width-2] e [1, height-2], ou seja, não ultrapassa as paredes.  
            #Se estivéssemos no limite (x=0 ou x=width-1), seria parede. Logo, pessoas não andam em cima das paredes.
            if (1 <= new_x < self.environment.width - 1 and 
                1 <= new_y < self.environment.height - 1):
                
                #Cria objeto Position.  
                #Pergunta ao ambiente: “está livre?”  
                #Se sim, adiciona à lista de possíveis movimentos.
                new_pos = Position(new_x, new_y)
                if self.environment.is_position_free(new_pos):
                    moves.append(new_pos)
        
        return moves


#interage com o usuário por meio do terminal, lê parâmetros, cria o Environment e chama start_simulation().
def main():
    #Mostra título do programa no terminal
    print("=== SIMULAÇÃO DE EVACUAÇÃO COM THREADS ===\n")
    
    
    try:
        #Parâmetros setados pelo usuário    
        width = int(input("Largura do ambiente (mínimo 10): ") or "15")
        height = int(input("Altura do ambiente (mínimo 10): ") or "10")
        num_people = int(input("Número de pessoas (máximo 20): ") or "8")
        num_doors = int(input("Número de portas (mínimo 2): ") or "3")
        time_limit = int(input("Tempo limite em segundos (antes da evacuação): ") or "10")
        
        #Ajustes / validações
        width = max(10, width)
        height = max(10, height)
        num_people = min(20, max(1, num_people))
        num_doors = max(2, min(num_doors, (width + height - 4) * 2))
        time_limit = max(5, time_limit)
        
        #Mostra o que de fato será usado, após ajustes.
        print(f"\nParâmetros confirmados:")
        print(f"Ambiente: {width}x{height}")
        print(f"Pessoas: {num_people}")
        print(f"Portas: {num_doors}")
        print(f"Tempo limite: {time_limit}s")
        
        #Pausa até o usuário apertar Enter, para que ele veja os parâmetros e esteja pronto.
        input("\nPressione Enter para iniciar...")
        
        #Instancia o ambiente com todos os dados fornecidos.  
        #Chama o método que realmente gerencia todo o ciclo de simulação (start_simulation(self))
        environment = Environment(width, height, num_people, num_doors, time_limit)
        environment.start_simulation()

    #Se o usuário apertar Ctrl+C no meio do input ou durante a simulação, o programa exibirá “Simulação interrompida pelo usuário.”  
    except KeyboardInterrupt:
        print("\n\nSimulação interrompida pelo usuário.")
    #Se acontecer qualquer outro erro, será exibida mensagem “Erro durante a simulação: <descrição do erro>”.    
    except Exception as e:
        print(f"\nErro durante a simulação: {e}")

#Essa linha faz com que a função main() seja executada somente quando este arquivo for executado como programa principal (não quando for importado como módulo por outro arquivo).  
#Então, se você executar python nome_do_arquivo.py, ele vai entrar nesse if e chamar main(). Se você importar esse script em outro arquivo, o main() não será chamado automaticamente.
if __name__ == "__main__":
    main()