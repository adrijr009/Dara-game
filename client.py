import tkinter as tk
from tkinter import messagebox, scrolledtext
import socket, threading, json

class DaraClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Dara Game")
        self.socket = None
        self.player_id = None
        self.my_turn = False
        self.phase = "PLACEMENT"
        self.selected_piece = None
        
        self.setup_lobby()

    def setup_lobby(self):
        self.lobby_frame = tk.Frame(self.root, padx=20, pady=20)
        self.lobby_frame.pack()
        tk.Label(self.lobby_frame, text="Dara Multi-Máquinas", font=('Arial', 14, 'bold')).pack(pady=10)
        self.btn_connect = tk.Button(self.lobby_frame, text="Conectar ao Servidor", command=self.connect)
        self.btn_connect.pack()

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(('127.0.0.1', 5000)) 
            threading.Thread(target=self.listen, daemon=True).start()
            self.btn_connect.config(text="Aguardando oponente...", state="disabled")
        except:
            messagebox.showerror("Erro", "Servidor offline!")

    def setup_game_ui(self):
        self.lobby_frame.destroy()
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=10, pady=10)

        tk.Label(self.main_frame, text=f"Você é o Jogador {self.player_id}", font=('Arial', 10, 'italic')).grid(row=0, column=0, sticky="w")
        self.lbl_status = tk.Label(self.main_frame, text="Sorteando quem inicia...", font=('Arial', 11, 'bold'))
        self.lbl_status.grid(row=1, column=0, columnspan=2, pady=5)

        # TABULEIRO: Agora usamos Canvas em vez de Buttons
        self.board_frame = tk.Frame(self.main_frame, bg="grey")
        self.board_frame.grid(row=2, column=0)
        
        self.btns = [[None for _ in range(6)] for _ in range(5)]
        for r in range(5):
            for c in range(6):
                # Criamos um Canvas para cada célula (retangular por fora, redondo por dentro)
                canv = tk.Canvas(self.board_frame, width=60, height=60, bg="#dcdde1", highlightthickness=1, relief="raised")
                canv.grid(row=r, column=c, padx=1, pady=1)
                
                # Vinculamos o clique diretamente ao Canvas
                canv.bind("<Button-1>", lambda event, r=r, c=c: self.on_click(r, c))
                self.btns[r][c] = canv

        self.btn_give_up = tk.Button(self.main_frame, text="Desistir", fg="white", bg="#c0392b", command=self.confirm_give_up)
        self.btn_give_up.grid(row=0, column=1, sticky="e", padx=5)

        self.setup_chat()

    def on_click(self, r, c):
        if self.my_turn:
            if self.phase == "PLACEMENT":
                self.send({"type": "place", "pos": (r, c)})
            elif self.phase == "MOVEMENT":
                if self.selected_piece:
                    self.send({"type": "move", "old_pos": self.selected_piece, "pos": (r, c)})
                    self.selected_piece = None
                    # Reseta o visual de seleção de todos os Canvas
                    for row in self.btns:
                        for canv in row: canv.config(highlightbackground="black", highlightthickness=1)
                else:
                    self.selected_piece = (r, c)
                    # Destaca o Canvas selecionado com uma borda amarela
                    self.btns[r][c].config(highlightbackground="yellow", highlightthickness=3)
            elif self.phase == "CAPTURE":
                self.send({"type": "capture", "pos": (r, c)})

    def update_board(self, data):
        self.phase = data['phase']
        turn = data['turn']
        self.my_turn = (turn == self.player_id)
        
        fases_pt = {
            "PLACEMENT": "Colocação", 
            "MOVEMENT": "Movimentação", 
            "CAPTURE": "CAPTURA!"
        }
        
        # --- SUBSTITUA AS LINHAS DE STATUS POR ESTE BLOCO ---
        if self.my_turn:
            status_text = "SUA VEZ"
            # Fica verde se for movimento/colocação, vermelho se for captura
            cor = "green" if self.phase != "CAPTURE" else "red"
        else:
            status_text = f"Vez do Jogador {turn}"
            # Se não for minha vez, o texto é sempre preto (evita confusão)
            cor = "black"
        # Aplica o texto e a cor no label
        self.lbl_status.config(text=f"{status_text} | Fase: {fases_pt[self.phase]}", fg=cor)

        # Cores das peças redondas
        piece_colors = {1: "#3498db", 2: "#e74c3c"} # Azul e Vermelho
        
        for r in range(5):
            for c in range(6):
                val = data['board'][r][c]
                canv = self.btns[r][c]
                canv.delete("piece") # Limpa apenas o desenho da peça anterior
                
                if val != 0:
                    # Desenha o círculo (peça redonda)
                    padding = 10
                    canv.create_oval(padding, padding, 60-padding, 60-padding, 
                                     fill=piece_colors[val], outline="white", width=2, tags="piece")

    def update_chat(self, msg):
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, msg + "\n")
        if "SISTEMA:" in msg:
            self.chat_area.tag_add("sys", "end-2l", "end-1l")
            self.chat_area.tag_config("sys", foreground="purple", font=('Arial', 9, 'bold'))
        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END)

    def setup_chat(self):
        chat_frame = tk.Frame(self.main_frame)
        chat_frame.grid(row=2, column=1, padx=10)
        self.chat_area = scrolledtext.ScrolledText(chat_frame, width=30, height=18, state='disabled', font=('Arial', 9))
        self.chat_area.pack()
        self.chat_entry = tk.Entry(chat_frame)
        self.chat_entry.pack(fill='x', pady=5)
        self.chat_entry.bind("<Return>", self.send_chat)

    def send(self, data):
        self.socket.send(json.dumps(data).encode('utf-8'))

    def send_chat(self, event):
        msg = self.chat_entry.get()
        if msg:
            self.send({"type": "chat", "user": f"Jogador {self.player_id}", "text": msg})
            self.chat_entry.delete(0, tk.END)

    def listen(self):
        while True:
            try:
                raw_data = self.socket.recv(4096).decode('utf-8')
                if not raw_data: break
                data = json.loads(raw_data)
                if data['type'] == 'init': self.player_id = data['player_id']
                elif data['type'] == 'start': self.root.after(0, self.setup_game_ui)
                elif data['type'] == 'update': self.root.after(0, self.update_board, data)
                elif data['type'] == 'chat': self.root.after(0, self.update_chat, f"{data['user']}: {data['text']}")
                elif data['type'] == 'win':
                    messagebox.showinfo("Fim de Jogo", f"Jogador {data['winner']} venceu!")
                    self.root.quit()
            except: break

    def confirm_give_up(self):
        res = messagebox.askyesno("Desistir", "Tem certeza que deseja desistir da partida?")
        if res: self.send({"type": "give_up"})

if __name__ == "__main__":
    root = tk.Tk()
    client = DaraClient(root)
    root.mainloop()