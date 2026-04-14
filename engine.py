class DaraEngine:
    def __init__(self):
        self.board = [[0 for _ in range(6)] for _ in range(5)]
        self.turn = 1
        self.phase = "PLACEMENT"
        self.pieces_placed = {1: 0, 2: 0}
        self.pieces_left = {1: 12, 2: 12}

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "phase": self.phase,
            "pieces_left": self.pieces_left
        }

    def get_sequence_at(self, r, c, p_id):
        row = self.board[r]
        col = [self.board[i][c] for i in range(5)]
        def count_line(line, idx):
            if line[idx] != p_id: return 0
            cnt = 1
            for i in range(idx - 1, -1, -1):
                if line[i] == p_id: cnt += 1
                else: break
            for i in range(idx + 1, len(line)):
                if line[i] == p_id: cnt += 1
                else: break
            return cnt
        return max(count_line(row, c), count_line(col, r))

    def process_action(self, player_id, msg):
        if self.turn != player_id: return False
        r, c = msg.get('pos', (0,0))
        
        if self.phase == "PLACEMENT":
            if self.board[r][c] == 0:
                self.board[r][c] = player_id
                if self.get_sequence_at(r, c, player_id) >= 3:
                    self.board[r][c] = 0
                    return False
                self.pieces_placed[player_id] += 1
                if self.pieces_placed[1] == 12 and self.pieces_placed[2] == 12:
                    self.phase = "MOVEMENT"
                self.turn = 3 - self.turn
                return True
        
        elif self.phase == "MOVEMENT":
            old_r, old_c = msg['old_pos']
            if abs(r-old_r) + abs(c-old_c) == 1 and self.board[r][c] == 0:
                self.board[old_r][old_c] = 0
                self.board[r][c] = player_id
                seq = self.get_sequence_at(r, c, player_id)
                if seq >= 4:
                    self.board[r][c] = 0
                    self.board[old_r][old_c] = player_id
                    return False
                if seq == 3: self.phase = "CAPTURE"
                else: self.turn = 3 - self.turn
                return True
        
        elif self.phase == "CAPTURE":
            if self.board[r][c] == (3 - player_id):
                self.board[r][c] = 0
                self.pieces_left[3 - player_id] -= 1
                self.phase = "MOVEMENT"
                self.turn = 3 - self.turn
                return True
        return False