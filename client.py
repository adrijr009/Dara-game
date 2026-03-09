import tkinter as tk
from tkinter import messagebox, scrolledtext
import socket, threading, json

class DaraClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Dara Game")
        
        # Variáveis de controle de rede e estado
        self.socket = None
        self.player_id = None    # Definido pelo servidor (1 ou 2)
        self.my_turn = False     # Bloqueia cliques se não for sua vez
        self.phase = "PLACEMENT" # PLACEMENT, MOVEMENT ou CAPTURE
        self.selected_piece = None # Armazena a peça que você quer mover
        
        self.setup_lobby()

    def setup_lobby(self):
        """Cria a tela inicial de conexão."""
        self.lobby_frame = tk.Frame(self.root, padx=20, pady=20)
        self.lobby_frame.pack()
        tk.Label(self.lobby_frame, text="Dara Multi-Máquinas", font=('Arial', 14, 'bold')).pack(pady=10)
        self.btn_connect = tk.Button(self.lobby_frame, text="Conectar ao Servidor", command=self.connect)
        self.btn_connect.pack()

    def connect(self):
        """Tenta conectar ao IP do servidor e inicia a escuta de mensagens."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(('127.0.0.1', 5000)) 
            # Thread: permite que o jogo receba dados do servidor sem travar a janela
            threading.Thread(target=self.listen, daemon=True).start()
            self.btn_connect.config(text="Aguardando oponente...", state="disabled")
        except:
            messagebox.showerror("Erro", "Servidor offline!")

    def setup_game_ui(self):
        """Monta a interface do tabuleiro e do chat após a conexão."""
        self.lobby_frame.destroy()
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(padx=10, pady=10)

        # Labels de informação
        tk.Label(self.main_frame, text=f"Você é o Jogador {self.player_id}", font=('Arial', 10, 'italic')).grid(row=0, column=0, sticky="w")
        self.lbl_status = tk.Label(self.main_frame, text="Sorteando quem inicia...", font=('Arial', 11, 'bold'))
        self.lbl_status.grid(row=1, column=0, columnspan=2, pady=5)

        # Criação do Tabuleiro 5x6 usando Canvas (para desenhar peças redondas)
        self.board_frame = tk.Frame(self.main_frame, bg="grey")
        self.board_frame.grid(row=2, column=0)
        
        self.btns = [[None for _ in range(6)] for _ in range(5)]
        for r in range(5):
            for c in range(6):
                canv = tk.Canvas(self.board_frame, width=60, height=60, bg="#dcdde1", highlightthickness=1, relief="raised")
                canv.grid(row=r, column=c, padx=1, pady=1)
                # O clique envia a coordenada (r, c) para a função on_click
                canv.bind("<Button-1>", lambda event, r=r, c=c: self.on_click(r, c))
                self.btns[r][c] = canv

        self.btn_give_up = tk.Button(self.main_frame, text="Desistir", fg="white", bg="#c0392b", command=self.confirm_give_up)
        self.btn_give_up.grid(row=0, column=1, sticky="e", padx=5)

        self.setup_chat()

    def on_click(self, r, c):
        """Envia para o servidor a intenção de jogada dependendo da fase atual."""
        if self.my_turn:
            # Fase 1: Apenas posicionar
            if self.phase == "PLACEMENT":
                self.send({"type": "place", "pos": (r, c)})
            
            # Fase 2: Selecionar peça (clique 1) e mover (clique 2)
            elif self.phase == "MOVEMENT":
                if self.selected_piece:
                    self.send({"type": "move", "old_pos": self.selected_piece, "pos": (r, c)})
                    self.selected_piece = None
                    # Limpa destaques amarelos
                    for row in self.btns:
                        for canv in row: canv.config(highlightbackground="black", highlightthickness=1)
                else:
                    self.selected_piece = (r, c)
                    # Destaca a peça escolhida
                    self.btns[r][c].config(highlightbackground="yellow", highlightthickness=3)
            
            # Fase 3: Escolher peça do inimigo para remover
            elif self.phase == "CAPTURE":
                self.send({"type": "capture", "pos": (r, c)})

    def update_board(self, data):
        """Recebe o estado do tabuleiro do servidor e redesenha tudo."""
        self.phase = data['phase']
        turn = data['turn']
        self.my_turn = (turn == self.player_id)
        
        fases_pt = {"PLACEMENT": "Colocação", "MOVEMENT": "Movimentação", "CAPTURE": "CAPTURA!"}
        
        # Lógica visual de cores para o status
        if self.my_turn:
            status_text = "SUA VEZ"
            cor = "green" if self.phase != "CAPTURE" else "red"
        else:
            status_text = f"Vez do Jogador {turn}"
            cor = "black"
            
        self.lbl_status.config(text=f"{status_text} | Fase: {fases_pt[self.phase]}", fg=cor)

        piece_colors = {1: "#3498db", 2: "#e74c3c"} # 1=Azul, 2=Vermelho
        
        # Varre a matriz recebida e desenha os círculos no Canvas
        for r in range(5):
            for c in range(6):
                val = data['board'][r][c]
                canv = self.btns[r][c]
                canv.delete("piece") # Remove desenho antigo
                
                if val != 0:
                    padding = 10
                    canv.create_oval(padding, padding, 60-padding, 60-padding, 
                                     fill=piece_colors[val], outline="white", width=2, tags="piece")

    def update_chat(self, msg):
        """Adiciona mensagens ao campo de chat."""
        self.chat_area.config(state='normal')
        self.chat_area.insert(tk.END, msg + "\n")
        if "SISTEMA:" in msg: # Mensagens automáticas ficam em roxo
            self.chat_area.tag_add("sys", "end-2l", "end-1l")
            self.chat_area.tag_config("sys", foreground="purple", font=('Arial', 9, 'bold'))
        self.chat_area.config(state='disabled')
        self.chat_area.see(tk.END)

    def setup_chat(self):
        """Interface lateral do chat."""
        chat_frame = tk.Frame(self.main_frame)
        chat_frame.grid(row=2, column=1, padx=10)
        self.chat_area = scrolledtext.ScrolledText(chat_frame, width=30, height=18, state='disabled', font=('Arial', 9))
        self.chat_area.pack()
        self.chat_entry = tk.Entry(chat_frame)
        self.chat_entry.pack(fill='x', pady=5)
        self.chat_entry.bind("<Return>", self.send_chat)

    def send(self, data):
        """Converte dicionário em JSON e envia via Socket."""
        self.socket.send(json.dumps(data).encode('utf-8'))

    def send_chat(self, event):
        """Envia a mensagem digitada para o servidor."""
        msg = self.chat_entry.get()
        if msg:
            self.send({"type": "chat", "user": f"Jogador {self.player_id}", "text": msg})
            self.chat_entry.delete(0, tk.END)

    def listen(self):
        """Fica ouvindo o servidor continuamente (roda em background)."""
        while True:
            try:
                raw_data = self.socket.recv(4096).decode('utf-8')
                if not raw_data: break
                data = json.loads(raw_data)
                
                # O servidor manda o comando e o cliente obedece
                if data['type'] == 'init': 
                    self.player_id = data['player_id']
                elif data['type'] == 'start': 
                    self.root.after(0, self.setup_game_ui)
                elif data['type'] == 'update': 
                    self.root.after(0, self.update_board, data)
                elif data['type'] == 'chat': 
                    self.root.after(0, self.update_chat, f"{data['user']}: {data['text']}")
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