import socket, threading, json, time, random
from engine import DaraEngine

class DaraServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(2)
        self.clients = []
        self.game = DaraEngine()

    def broadcast(self, data):
        msg = json.dumps(data).encode('utf-8')
        for c in self.clients:
            try: c.send(msg)
            except: self.clients.remove(c)

    def handle_client(self, conn, player_id):
        conn.send(json.dumps({"type": "init", "player_id": player_id}).encode('utf-8'))
        while True:
            try:
                raw = conn.recv(4096).decode('utf-8')
                if not raw: break
                msg = json.loads(raw)
                
                if msg['type'] == 'chat': 
                    self.broadcast(msg)
                elif msg['type'] == 'give_up':
                    winner = 3 - player_id
                    self.broadcast({"type": "chat", "user": "SISTEMA", "text": f"Jogador {player_id} desistiu!"})
                    self.broadcast({"type": "win", "winner": winner})
                else:
                    if self.game.process_action(player_id, msg):
                        state = self.game.get_state()
                        state["type"] = "update"
                        self.broadcast(state)
                        if self.game.pieces_left[3-player_id] <= 2:
                            self.broadcast({"type": "win", "winner": player_id})
            except: break

    def run(self):
        print("Servidor Dara rodando...")
        while len(self.clients) < 2:
            conn, _ = self.server.accept()
            self.clients.append(conn)
            threading.Thread(target=self.handle_client, args=(conn, len(self.clients)), daemon=True).start()
        
        self.game.turn = random.randint(1, 2)
        self.broadcast({"type": "start"})
        time.sleep(0.5)
        
        # Mensagem de sistema sobre quem começa
        self.broadcast({"type": "chat", "user": "SISTEMA", "text": f"O Jogador {self.game.turn} inicia!"})
        
        state = self.game.get_state()
        state["type"] = "update"
        self.broadcast(state)
        while True: time.sleep(1)

if __name__ == "__main__":
    DaraServer().run()