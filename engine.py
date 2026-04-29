class DaraEngine:
    """
    Motor de lógica do jogo Dara. 
    Gerencia o tabuleiro, valida jogadas e controla as fases do jogo.
    """
    def __init__(self):
        # Tabuleiro 5x6 (padrão do Dara). 0 = vazio, 1 = Jogador 1, 2 = Jogador 2.
        self.board = [[0 for _ in range(6)] for _ in range(5)]
        self.turn = 1               # Começa com o Jogador 1
        self.phase = "PLACEMENT"    # Fases: PLACEMENT -> MOVEMENT -> CAPTURE
        self.pieces_placed = {1: 0, 2: 0} # Contador de peças colocadas (máx 12 cada)
        self.pieces_left = {1: 12, 2: 12}  # Peças que restam no tabuleiro

    def get_state(self):
        """ Retorna um resumo do estado atual para ser enviado via RPC aos clientes """
        winner = None
        # Condição de Vitória: Na fase de movimento, se o oponente tiver menos de 3 peças, ele perde.
        if self.phase != "PLACEMENT":
            if self.pieces_left[1] < 3: winner = 2
            elif self.pieces_left[2] < 3: winner = 1
            
        return {
            "board": self.board, 
            "turn": self.turn, 
            "phase": self.phase, 
            "pieces_left": self.pieces_left,
            "winner": winner
        }

    def get_sequence_at(self, r, c, p_id):
        """ 
        Verifica o tamanho da sequência (linha ou coluna) que uma peça forma ao ser colocada.
        No Dara, sequências de exatamente 3 peças permitem capturar uma peça inimiga.
        """
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        
        def count_line(line, idx):
            """ Conta quantas peças iguais estão conectadas em uma lista (horizontal ou vertical) """
            if line[idx] != p_id: return 0
            cnt = 1
            # Conta para a esquerda/cima
            for i in range(idx - 1, -1, -1):
                if line[i] == p_id: cnt += 1
                else: break
            # Conta para a direita/baixo
            for i in range(idx + 1, len(line)):
                if line[i] == p_id: cnt += 1
                else: break
            return cnt
            
        return max(count_line(row, c), count_line(col, r))

    def process_action(self, player_id, msg):
        """ 
        Processa as intenções dos jogadores. 
        Retorna True se a jogada foi válida e False caso contrário.
        """
        # Validação básica: Só processa se for a vez do jogador
        if self.turn != player_id: return False
        
        r, c = msg.get('pos', (0,0))
        
        # --- FASE 1: POSICIONAMENTO ---
        if self.phase == "PLACEMENT":
            if self.board[r][c] == 0: # Só coloca em espaço vazio
                self.board[r][c] = player_id
                
                # Regra do Dara: Não pode formar sequências de 3 ou mais na fase de colocar peças!
                if self.get_sequence_at(r, c, player_id) >= 3:
                    self.board[r][c] = 0 # Desfaz a jogada
                    return False
                
                self.pieces_placed[player_id] += 1
                
                # Se ambos colocaram as 12 peças, muda para a fase de movimento
                if self.pieces_placed[1] == 12 and self.pieces_placed[2] == 12:
                    self.phase = "MOVEMENT"
                
                self.turn = 3 - self.turn # Passa a vez (Se era 1 vira 2, se era 2 vira 1)
                return True
        
        # --- FASE 2: MOVIMENTAÇÃO ---
        elif self.phase == "MOVEMENT":
            old_r, old_c = msg['old_pos']
            # Valida movimento adjacente (cima, baixo, esquerda, direita) e se o destino está vazio
            if abs(r-old_r) + abs(c-old_c) == 1 and self.board[r][c] == 0:
                self.board[old_r][old_c] = 0
                self.board[r][c] = player_id
                
                seq = self.get_sequence_at(r, c, player_id)
                
                # Regra: Não pode formar sequências maiores que 3 (4 ou mais é proibido)
                if seq >= 4:
                    self.board[r][c] = 0 # Desfaz o movimento
                    self.board[old_r][old_c] = player_id
                    return False
                
                # Se formou exatamente 3, o jogador entra na fase de CAPTURA (joga de novo para remover peça)
                if seq == 3: 
                    self.phase = "CAPTURE"
                else: 
                    self.turn = 3 - self.turn # Se não fez 3, passa a vez
                return True
        
        # --- FASE 3: CAPTURA ---
        elif self.phase == "CAPTURE":
            # O jogador deve clicar em uma peça do ADVERSÁRIO (3 - player_id)
            if self.board[r][c] == (3 - player_id):
                self.board[r][c] = 0
                self.pieces_left[3 - player_id] -= 1
                self.phase = "MOVEMENT" # Volta para movimentação
                self.turn = 3 - self.turn # Passa a vez
                return True
                
        return False # Se não caiu em nenhum critério, a jogada é inválida