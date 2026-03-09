import socket
import threading
import json
import time
import random

class DaraServer:
    def __init__(self, host='127.0.0.1', port=5000):
        # Inicializa o socket TCP/IP para aguardar conexões
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen(2) # Define o limite de 2 jogadores (Dara é um jogo de duelo)
        
        self.clients = [] # Lista para gerenciar as conexões ativas
        self.board = [[0 for _ in range(6)] for _ in range(5)] # Matriz 5x6 representando o tabuleiro
        self.turn = 1  # Armazena o ID do jogador da vez
        self.phase = "PLACEMENT" # Controla o estado do jogo: PLACEMENT, MOVEMENT ou CAPTURE
        self.pieces_placed = {1: 0, 2: 0} # Contador para garantir que cada um coloque 12 peças
        self.pieces_left = {1: 12, 2: 12} # Contador de peças restantes para verificar condição de vitória
        print(f"Servidor Dara rodando em {host}:{port}")

    def broadcast(self, data):
        """Envia um objeto (convertido em JSON) para todos os jogadores conectados."""
        message = json.dumps(data).encode('utf-8')
        for client in self.clients:
            try: 
                client.send(message)
            except: 
                self.clients.remove(client)

    def count_max_sequence(self, line, p_id):
        """Função utilitária para encontrar a maior sequência de peças em uma lista."""
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
        Lógica local: Conta peças seguidas que passam obrigatoriamente pela posição 'index'.
        Isso evita que alinhamentos antigos em outras partes da linha disparem capturas.
        """
        if line[index] != p_id: return 0
        
        count = 1
        # Varre para a esquerda/cima
        for i in range(index - 1, -1, -1):
            if line[i] == p_id: count += 1
            else: break
            
        # Varre para a direita/baixo
        for i in range(index + 1, len(line)):
            if line[i] == p_id: count += 1
            else: break
            
        return count

    def check_invalid_4(self, r, c, p_id):
        """Regra Restritiva: No Dara, é proibido formar colunas ou linhas com mais de 3 peças."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        
        return self.get_sequence_at(row, c, p_id) >= 4 or \
               self.get_sequence_at(col, r, p_id) >= 4

    def check_capture_exactly_3(self, r, c, p_id):
        """Regra de Captura: O jogador só ganha o direito de capturar se formar exatamente 3 peças."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        
        return self.get_sequence_at(row, c, p_id) == 3 or \
               self.get_sequence_at(col, r, p_id) == 3

    def has_any_3_in_line(self, r, c, p_id):
        """Impedimento de fase: Durante a colocação, não se pode formar trios (apenas na movimentação)."""
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        return self.get_sequence_at(row, c, p_id) >= 3 or \
               self.get_sequence_at(col, r, p_id) >= 3

    def handle_client(self, conn, player_id):
        """Thread individual para cada cliente. Escuta mensagens e processa a lógica de jogo."""
        # Envia mensagem inicial informando ao cliente se ele é o Jogador 1 ou 2
        conn.send(json.dumps({"type": "init", "player_id": player_id}).encode('utf-8'))
        
        while True:
            try:
                data = conn.recv(4096).decode('utf-8')
                if not data: break
                msg = json.loads(data)

                # Tratamento de mensagens de chat (apenas repassa para os outros)
                if msg['type'] == 'chat':
                    self.broadcast(msg)
                    continue
                
                if msg['type'] == 'give_up':
                    winner = 3 - player_id # Se o jogador 1 desiste, o 2 vence e vice-versa
                    self.broadcast({
                        "type": "chat", 
                        "user": "SISTEMA", 
                        "text": f"O Jogador {player_id} desistiu da partida!"
                        })
                    self.broadcast({"type": "win", "winner": winner})
                    continue

                # Trava de Segurança: Ignora cliques se não for a vez do jogador
                # (A menos que esteja na fase de captura, onde o jogador da vez remove a peça)
                if self.turn != player_id:
                    continue
                r, c = msg.get('pos', (0,0))

                # --- Lógica: Fase de Colocação ---
                if self.phase == "PLACEMENT":
                    if self.board[r][c] == 0:
                        self.board[r][c] = player_id
                        # Validação: Não permite criar sequências de 3 nesta fase
                        if self.has_any_3_in_line(r, c, player_id):
                            self.board[r][c] = 0
                            continue
                        
                        self.pieces_placed[player_id] += 1
                        # Transição de fase: Ambos colocaram todas as 12 peças
                        if self.pieces_placed[1] == 12 and self.pieces_placed[2] == 12:
                            self.phase = "MOVEMENT"
                        self.turn = 3 - self.turn # Alterna o turno (se 1 vira 2, se 2 vira 1)
                
                # --- Lógica: Fase de Movimentação ---
                elif self.phase == "MOVEMENT":
                    old_r, old_c = msg['old_pos']
                    # Validação: Movimento deve ser adjacente (distância Manhattan = 1) e para casa vazia
                    if abs(r-old_r) + abs(c-old_c) == 1 and self.board[r][c] == 0:
                        self.board[old_r][old_c] = 0
                        self.board[r][c] = player_id
                        
                        # Se o movimento criar uma linha proibida de 4+, ele é desfeito
                        if self.check_invalid_4(r, c, player_id):
                            self.board[r][c] = 0
                            self.board[old_r][old_c] = player_id
                            continue

                        # Verifica se o movimento resultou em um trio para iniciar captura
                        if self.check_capture_exactly_3(r, c, player_id):
                            self.phase = "CAPTURE"
                        else:
                            self.turn = 3 - self.turn

                # --- Lógica: Fase de Captura ---
                elif self.phase == "CAPTURE":
                    # O jogador clica em uma peça que deve ser do oponente (3 - player_id)
                    if self.board[r][c] == (3 - player_id):
                        self.board[r][c] = 0
                        self.pieces_left[3 - player_id] -= 1
                        self.phase = "MOVEMENT"
                        self.turn = 3 - self.turn
                        # Condição de Fim de Jogo: Oponente ficou com menos de 3 peças
                        if self.pieces_left[3 - player_id] <= 2:
                            self.broadcast({"type": "win", "winner": player_id})

                # Envia o estado do tabuleiro atualizado para ambos os jogadores após qualquer ação
                self.broadcast({"type": "update", "board": self.board, "turn": self.turn, "phase": self.phase})
            except: break

    def run(self):
        """Inicia o servidor e aguarda os dois jogadores conectarem para começar."""
        while len(self.clients) < 2:
            conn, addr = self.server.accept()
            self.clients.append(conn)
            # Inicia uma thread separada para que um jogador não trave o outro
            threading.Thread(target=self.handle_client, args=(conn, len(self.clients))).start()
        
        # SORTEIO: Define aleatoriamente quem começa
        self.turn = random.randint(1, 2)
        
        self.broadcast({"type": "start"})
        time.sleep(0.2)
        
        # Avisa no chat do sistema o resultado do sorteio
        self.broadcast({"type": "chat", "user": "SISTEMA", "text": f"O Jogador {self.turn} inicia a partida!"})
        
        # Sincroniza o estado inicial em todos os clientes
        self.broadcast({"type": "update", "board": self.board, "turn": self.turn, "phase": self.phase})

if __name__ == "__main__":
    DaraServer().run()