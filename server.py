import socket
import threading
import json
import time
import random

class DaraServer:
    def __init__(self, host='127.0.0.1', port=5000):
        # Inicializa o socket TCP/IP. AF_INET é para IPv4 e SOCK_STREAM para TCP.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen(2) # Dara é um duelo, então limitamos a fila de espera a 2
        
        # --- ESTADO GLOBAL DO JOGO ---
        self.clients = [] # Guarda os objetos de conexão (conns) para enviar dados
        self.board = [[0 for _ in range(6)] for _ in range(5)] # Matriz 5x6: 0=vazio, 1=P1, 2=P2
        self.turn = 1  # Indica qual ID de jogador pode agir no momento
        self.phase = "PLACEMENT" # Fases: PLACEMENT (Colocar), MOVEMENT (Mover), CAPTURE (Capturar)
        self.pieces_placed = {1: 0, 2: 0} # Contador para a fase inicial (limite de 12 cada)
        self.pieces_left = {1: 12, 2: 12} # Quantidade viva no tabuleiro para checar vitória
        print(f"Servidor Dara rodando em {host}:{port}")

    def broadcast(self, data):
        """Converte o dicionário Python em JSON e envia para TODOS os jogadores conectados."""
        message = json.dumps(data).encode('utf-8')
        for client in self.clients:
            try: 
                client.send(message)
            except: 
                # Se um cliente caiu, removemos da lista para evitar erros de envio
                self.clients.remove(client)

    def count_max_sequence(self, line, p_id):
        """Varre uma lista (linha ou coluna) para encontrar a maior sequência de peças idênticas."""
        max_count = 0
        current_count = 0
        for val in line:
            if val == p_id:
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0
        return max_count

    def get_sequence_at(self, line, index, p_id):
        """
        Lógica Fundamental: Conta peças seguidas partindo obrigatoriamente do 'index' atual.
        Isso garante que só detectamos o trio ou erro de 4+ se a peça que acabou de ser 
        mexida fizer parte desse alinhamento.
        """
        if line[index] != p_id: return 0
        
        count = 1
        # Conta para trás (esquerda ou cima)
        for i in range(index - 1, -1, -1):
            if line[i] == p_id: count += 1
            else: break
            
        # Conta para frente (direita ou baixo)
        for i in range(index + 1, len(line)):
            if line[i] == p_id: count += 1
            else: break
            
        return count

    def check_invalid_4(self, r, c, p_id):
        """Regra do Dara: É proibido formar linhas ou colunas com 4 ou mais peças do mesmo jogador."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        
        return self.get_sequence_at(row, c, p_id) >= 4 or \
               self.get_sequence_at(col, r, p_id) >= 4

    def check_capture_exactly_3(self, r, c, p_id):
        """Regra de Captura: O jogador entra em modo de captura apenas se formar EXATAMENTE 3 peças em linha."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        
        return self.get_sequence_at(row, c, p_id) == 3 or \
               self.get_sequence_at(col, r, p_id) == 3

    def has_any_3_in_line(self, r, c, p_id):
        """Impede que trios sejam formados na fase de colocação (PLACEMENT)."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        return self.get_sequence_at(row, c, p_id) >= 3 or \
               self.get_sequence_at(col, r, p_id) >= 3

    def handle_client(self, conn, player_id):
        """Escuta o que um jogador específico envia e aplica a regra correspondente."""
        # Envia ao cliente o seu ID único (1 ou 2) assim que ele conecta
        conn.send(json.dumps({"type": "init", "player_id": player_id}).encode('utf-8'))
        
        while True:
            try:
                # Espera por mensagens do cliente (bloqueante até receber algo)
                data = conn.recv(4096).decode('utf-8')
                if not data: break
                msg = json.loads(data)

                # --- CHAT E DESISTÊNCIA ---
                if msg['type'] == 'chat':
                    self.broadcast(msg)
                    continue
                
                if msg['type'] == 'give_up':
                    winner = 3 - player_id # Inverte o ID: Se o 1 desiste, o 2 vence.
                    self.broadcast({
                        "type": "chat", "user": "SISTEMA", 
                        "text": f"O Jogador {player_id} desistiu da partida!"
                    })
                    self.broadcast({"type": "win", "winner": winner})
                    continue

                # --- SEGURANÇA: SÓ PROCESSA SE FOR O TURNO DO JOGADOR ---
                if self.turn != player_id:
                    continue

                r, c = msg.get('pos', (0,0)) # Coordenadas do clique do jogador

                # --- LÓGICA POR FASE ---
                
                if self.phase == "PLACEMENT":
                    if self.board[r][c] == 0: # Só coloca em casa vazia
                        self.board[r][c] = player_id
                        
                        # Se tentar formar trio antes da hora, o servidor desfaz a jogada
                        if self.has_any_3_in_line(r, c, player_id):
                            self.board[r][c] = 0
                            continue
                        
                        self.pieces_placed[player_id] += 1
                        # Quando os dois atingem 12 peças, o jogo 'destrava' para movimentação
                        if self.pieces_placed[1] == 12 and self.pieces_placed[2] == 12:
                            self.phase = "MOVEMENT"
                        self.turn = 3 - self.turn # Passa a vez

                elif self.phase == "MOVEMENT":
                    old_r, old_c = msg['old_pos']
                    # Valida se a peça destino está vazia e se a distância é de 1 casa (cima, baixo, esq, dir)
                    if abs(r-old_r) + abs(c-old_c) == 1 and self.board[r][c] == 0:
                        self.board[old_r][old_c] = 0
                        self.board[r][c] = player_id
                        
                        # Se o movimento criar uma linha proibida de 4+, ele é revertido
                        if self.check_invalid_4(r, c, player_id):
                            self.board[r][c] = 0
                            self.board[old_r][old_c] = player_id
                            continue

                        # Se formou trio exato, entra em modo de captura
                        if self.check_capture_exactly_3(r, c, player_id):
                            self.phase = "CAPTURE"
                            # Note: Aqui não trocamos o turno, pois o jogador atual deve capturar agora.
                        else:
                            self.turn = 3 - self.turn

                elif self.phase == "CAPTURE":
                    # Valida se o clique foi em uma peça do ADVERSÁRIO (3 - player_id)
                    if self.board[r][c] == (3 - player_id):
                        self.board[r][c] = 0
                        self.pieces_left[3 - player_id] -= 1
                        self.phase = "MOVEMENT" # Volta para o fluxo normal
                        self.turn = 3 - self.turn
                        
                        # Condição de Vitória: Perde quem ficar com apenas 2 peças (não consegue mais fazer trios)
                        if self.pieces_left[3 - player_id] <= 2:
                            self.broadcast({"type": "win", "winner": player_id})

                # Após qualquer jogada válida, o servidor 'grita' (broadcast) o novo estado para todos
                self.broadcast({
                    "type": "update", 
                    "board": self.board, 
                    "turn": self.turn, 
                    "phase": self.phase
                })
            except: 
                break

    def run(self):
        """Inicia o loop principal de conexões e sorteia o início."""
        while len(self.clients) < 2:
            conn, addr = self.server.accept()
            self.clients.append(conn)
            # Cada jogador ganha sua própria 'conversa' (Thread) paralela
            threading.Thread(target=self.handle_client, args=(conn, len(self.clients))).start()
        
        # Sorteia quem começa (1 ou 2)
        self.turn = random.randint(1, 2)
        
        # Avisa os clientes que a interface de jogo pode ser montada
        self.broadcast({"type": "start"})
        time.sleep(0.2) # Pequena pausa para garantir que os clientes processaram o 'start'
        
        self.broadcast({
            "type": "chat", "user": "SISTEMA", 
            "text": f"O Jogador {self.turn} inicia a partida!"
        })
        
        # Sincroniza o tabuleiro inicial (vazio) com os IDs sorteados
        self.broadcast({
            "type": "update", 
            "board": self.board, 
            "turn": self.turn, 
            "phase": self.phase
        })

if __name__ == "__main__":
    DaraServer().run()