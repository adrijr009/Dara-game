import tkinter as tk
from tkinter import messagebox, scrolledtext
import socket, threading, json

class SocketHandler:
    def __init__(self, callback):
        self.socket = None
        self.callback = callback

    def connect(self, ip):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((ip, 5000))
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        while True:
            try:
                data = json.loads(self.socket.recv(4096).decode('utf-8'))
                self.callback(data)
            except: break

    def send(self, data):
        if self.socket: self.socket.send(json.dumps(data).encode('utf-8'))

class DaraClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Dara Game")
        self.network = SocketHandler(self.process_data)
        self.player_id = None
        self.my_turn = False
        self.phase = "PLACEMENT"
        self.selected_piece = None
        self.btns = [[None for _ in range(6)] for _ in range(5)]
        self.setup_lobby()

    def setup_lobby(self):
        self.lobby_frame = tk.Frame(self.root, padx=20, pady=20)
        self.lobby_frame.pack()
        tk.Label(self.lobby_frame, text="Dara - Redes", font=('Arial', 14, 'bold')).pack(pady=10)
        tk.Label(self.lobby_frame, text="IP do Servidor:").pack()
        self.ent_ip = tk.Entry(self.lobby_frame)
        self.ent_ip.insert(0, "127.0.0.1")
        self.ent_ip.pack(pady=5)
        self.btn_conn = tk.Button(self.lobby_frame, text="Conectar", command=self.connect)
        self.btn_conn.pack()

    def connect(self):
        try:
            self.network.connect(self.ent_ip.get())
            self.btn_conn.config(text="Aguardando Oponente...", state="disabled")
        except: messagebox.showerror("Erro", "Servidor offline!")

    def setup_game_ui(self):
        self.lobby_frame.destroy()
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=10, pady=10)
        
        # Cabeçalho: ID do jogador e botão desistir
        header = tk.Frame(self.main_frame)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        tk.Label(header, text=f"Você é o JOGADOR {self.player_id}", fg="blue" if self.player_id==1 else "red", font=('Arial', 10, 'bold')).pack(side="left")
        
        tk.Button(header, text="Desistir", bg="#ff7675", command=self.confirm_give_up).pack(side="right")
        
        self.lbl_status = tk.Label(self.main_frame, text="Iniciando...", font=('Arial', 11))
        self.lbl_status.grid(row=1, column=0, columnspan=2, pady=10)
        
        board_container = tk.Frame(self.main_frame, bg="#2f3640", padx=2, pady=2)
        board_container.grid(row=2, column=0)
        
        for r in range(5):
            for c in range(6):
                canv = tk.Canvas(board_container, width=60, height=60, bg="#dcdde1", highlightthickness=1)
                canv.grid(row=r, column=c, padx=1, pady=1)
                canv.bind("<Button-1>", lambda e, r=r, c=c: self.on_click(r, c))
                self.btns[r][c] = canv

        # Chat
        chat_frame = tk.Frame(self.main_frame)
        chat_frame.grid(row=2, column=1, padx=10)
        self.chat_area = scrolledtext.ScrolledText(chat_frame, width=30, height=18, state='disabled', font=('Arial', 9))
        self.chat_area.pack()
        self.chat_ent = tk.Entry(chat_frame)
        self.chat_ent.pack(fill='x', pady=5)
        self.chat_ent.bind("<Return>", self.send_chat)

    def process_data(self, data):
        t = data['type']
        if t == 'init': self.player_id = data['player_id']
        elif t == 'start': self.root.after(0, self.setup_game_ui)
        elif t == 'update': self.root.after(0, self.draw_board, data)
        elif t == 'chat': self.root.after(0, self.add_chat, data)
        elif t == 'win': 
            messagebox.showinfo("Fim de Jogo", f"O Jogador {data['winner']} venceu!")
            self.root.quit()

    def on_click(self, r, c):
        if not self.my_turn: return
        
        if self.phase == "PLACEMENT":
            self.network.send({"type": "place", "pos": (r, c)})
        
        elif self.phase == "MOVEMENT":
            # Lógica de seleção e DESELEÇÃO
            if self.selected_piece == (r, c):
                self.selected_piece = None # Clicou na mesma, desmarca
                self.refresh_visuals()
            elif self.selected_piece:
                self.network.send({"type": "move", "old_pos": self.selected_piece, "pos": (r, c)})
                self.selected_piece = None
            else:
                self.selected_piece = (r, c)
                self.refresh_visuals()
        
        elif self.phase == "CAPTURE":
            self.network.send({"type": "capture", "pos": (r, c)})

    def draw_board(self, data):
        self.phase = data['phase']
        self.my_turn = (data['turn'] == self.player_id)
        
        # Indicativo de fases com cores
        fase_pt = {"PLACEMENT": "Colocação", "MOVEMENT": "Movimentação", "CAPTURE": "CAPTURA!"}
        cor_fase = "red" if self.phase == "CAPTURE" else "black"
        peso_fase = "bold" if self.phase == "CAPTURE" else "normal"
        
        status_text = "SUA VEZ" if self.my_turn else f"Vez do Jogador {data['turn']}"
        self.lbl_status.config(text=f"{status_text} | Fase: {fase_pt[self.phase]}", fg=cor_fase, font=('Arial', 11, peso_fase))
        
        self.current_board_data = data['board'] # Salva para refrescar destaques
        self.refresh_visuals()

    def refresh_visuals(self):
        """Atualiza o Canvas com base no estado e na seleção atual"""
        if not hasattr(self, 'current_board_data'): return
        colors = {1: "#3498db", 2: "#e74c3c"}
        
        for r in range(5):
            for c in range(6):
                val = self.current_board_data[r][c]
                canv = self.btns[r][c]
                canv.delete("piece")
                
                # Borda de seleção
                if self.selected_piece == (r, c):
                    canv.config(highlightbackground="yellow", highlightthickness=3)
                else:
                    canv.config(highlightbackground="black", highlightthickness=1)
                
                if val != 0:
                    canv.create_oval(10, 10, 50, 50, fill=colors[val], outline="white", width=2, tags="piece")

    def confirm_give_up(self):
        if messagebox.askyesno("Desistir", "Deseja mesmo abandonar a partida?"):
            self.network.send({"type": "give_up"})

    def send_chat(self, e):
        msg = self.chat_ent.get()
        if msg:
            self.network.send({"type": "chat", "user": f"Jogador {self.player_id}", "text": msg})
            self.chat_ent.delete(0, tk.END)

    def add_chat(self, data):
        self.chat_area.config(state='normal')
        cor = "purple" if data['user'] == "SISTEMA" else "black"
        self.chat_area.insert(tk.END, f"{data['user']}: {data['text']}\n", data['user'])
        self.chat_area.tag_config(data['user'], foreground=cor)
        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    DaraClient(root)
    root.mainloop()