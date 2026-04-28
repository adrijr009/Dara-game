import tkinter as tk
from tkinter import messagebox, scrolledtext
import Pyro5.api
import threading, socket

# --- CLASSE DE CALLBACK (O que o servidor manda para o cliente) ---
@Pyro5.api.expose
class ClientCallback:
    """ Esta classe permite que o servidor execute funções dentro do computador do jogador """
    def __init__(self, ui):
        self.ui = ui # Guarda uma referência da interface visual (DaraClient)

    def update_ui(self, data):
        """ Chamado pelo servidor sempre que o tabuleiro muda """
        print("[CLIENTE] Recebeu atualização de tabuleiro")
        # .after(0, ...) garante que o Tkinter atualize a tela na thread principal (evita crash)
        self.ui.root.after(0, self.ui.draw_board, data)

    def trigger_start(self):
        """ Chamado pelo servidor quando o segundo jogador entra, para fechar o lobby e abrir o jogo """
        print("[CLIENTE] Recebeu comando de START!")
        self.ui.root.after(0, self.ui.setup_game_ui)

    def receive_chat(self, user, text):
        """ Chamado pelo servidor para entregar uma mensagem de chat """
        self.ui.root.after(0, self.ui.add_chat, {"user": user, "text": text})

# --- CLASSE DE CONEXÃO (RMI) ---
class RMIHandler:
    """ Gerencia a saída de dados do cliente para o servidor """
    def __init__(self, ui):
        self.ui = ui
        self.server_uri = None # Guardamos apenas o endereço (URI) para criar proxies novos depois

    def connect(self, ip_servidor):
        """ Realiza o aperto de mão inicial com o servidor """
        try:
            # Descobrir o próprio IP local do jogador para que o servidor saiba para onde responder
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((ip_servidor, 5000))
            meu_ip = s.getsockname()[0]
            s.close()
            
            # Monta o endereço Pyro baseado no IP digitado
            self.server_uri = f"PYRO:dara.game@{ip_servidor}:5000"
            
            # Cria o "daemon" (serviço) que fica ouvindo o servidor no PC do jogador
            daemon = Pyro5.api.Daemon(host=meu_ip)
            cb_instancia = ClientCallback(self.ui)
            cb_uri = daemon.register(cb_instancia) # Registra o callback para ser acessível remotamente
            
            # Roda o loop de escuta em uma thread separada para não travar a janela do jogo
            threading.Thread(target=daemon.requestLoop, daemon=True).start()
            
            # Conecta no servidor e registra este jogador, recebendo de volta o ID (1 ou 2)
            with Pyro5.api.Proxy(self.server_uri) as proxy:
                self.ui.player_id = proxy.register_client(cb_uri)
            
            print(f"[CLIENTE] Conectado como Jogador {self.ui.player_id}")
            
        except Exception as e:
            messagebox.showerror("Erro", f"Falha na conexão: {e}")

    def send(self, data):
        """ Envia as ações do clique ou chat para o servidor em background """
        def async_send():
            try:
                # Criamos um Proxy novo DENTRO da thread para evitar erro de 'ownership'
                with Pyro5.api.Proxy(self.server_uri) as proxy:
                    if data['type'] == 'chat':
                        proxy.send_chat(data['user'], data['text'])
                    else:
                        proxy.execute_action(self.ui.player_id, data)
            except Exception as e:
                print(f"[CLIENTE] Erro ao enviar: {e}")
        
        # Inicia a thread de envio
        threading.Thread(target=async_send, daemon=True).start()

# --- CLASSE PRINCIPAL DA INTERFACE (GUI) ---
class DaraClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Dara RMI")
        self.network = RMIHandler(self) # Inicializa o controlador de rede
        self.player_id = None
        self.my_turn = False
        self.phase = "PLACEMENT"
        self.selected_piece = None # Usado para marcar qual peça você quer mover
        self.btns = [[None for _ in range(6)] for _ in range(5)] # Matriz dos espaços do tabuleiro
        self.setup_lobby() # Inicia pela tela de IP

    def setup_lobby(self):
        """ Cria a tela inicial de conexão """
        self.lobby = tk.Frame(self.root, padx=20, pady=20)
        self.lobby.pack()
        tk.Label(self.lobby, text="IP do Servidor:").pack()
        self.ent_ip = tk.Entry(self.lobby)
        self.ent_ip.insert(0, "127.0.0.1") # IP padrão (mesma máquina)
        self.ent_ip.pack()
        self.btn_conn = tk.Button(self.lobby, text="Conectar RMI", 
                                  command=lambda: self.network.connect(self.ent_ip.get()))
        self.btn_conn.pack(pady=10)

    def setup_game_ui(self):
        """ Monta a interface do jogo propriamente dita (Tabuleiro + Chat) """
        self.lobby.destroy() # Remove a tela de IP
        
        # Frame que segura tudo
        self.main_container = tk.Frame(self.root, padx=10, pady=10)
        self.main_container.pack()

        # Cabeçalho: Mostra seu ID e sua cor
        minha_cor = "Azul" if self.player_id == 1 else "Vermelho"
        cor_hex = "#3498db" if self.player_id == 1 else "#e74c3c"
        
        header_frame = tk.Frame(self.main_container)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        tk.Label(header_frame, text=f"JOGADOR {self.player_id} ({minha_cor})", 
                 fg=cor_hex, font=('Arial', 10, 'bold')).pack(side="left")

        # Tabuleiro (Lado Esquerdo)
        left_frame = tk.Frame(self.main_container)
        left_frame.grid(row=1, column=0, sticky="n")

        self.lbl_status = tk.Label(left_frame, text="Sorteando...", font=('Arial', 10))
        self.lbl_status.pack(pady=5)
        
        board_grid = tk.Frame(left_frame, bg="black", padx=2, pady=2)
        board_grid.pack()
        # Cria os 30 círculos (Canvas) do tabuleiro
        for r in range(5):
            for c in range(6):
                canv = tk.Canvas(board_grid, width=50, height=50, bg="white", highlightthickness=1)
                canv.grid(row=r, column=c, padx=1, pady=1)
                # O clique envia as coordenadas R e C para a função on_click
                canv.bind("<Button-1>", lambda e, r=r, c=c: self.on_click(r, c))
                self.btns[r][c] = canv

        # Chat e Controles (Lado Direito)
        right_frame = tk.Frame(self.main_container, padx=10)
        right_frame.grid(row=1, column=1, sticky="n")

        tk.Label(right_frame, text="Chat", font=('Arial', 10, 'bold')).pack(pady=(10, 5))
        self.chat_area = scrolledtext.ScrolledText(right_frame, width=30, height=18, 
                                                   state='disabled', wrap='word')
        self.chat_area.pack(pady=5)
        
        self.ent_chat = tk.Entry(right_frame)
        self.ent_chat.pack(fill="x")
        self.ent_chat.bind("<Return>", self.send_chat)

        self.btn_desistir = tk.Button(right_frame, text="Desistir", bg="#ff0000", fg="white", 
                                      width=8, command=self.confirmar_desistencia)
        self.btn_desistir.pack(fill="x", pady=10)

    def confirmar_desistencia(self):
        """ Pergunta antes de avisar o servidor que o jogador desistiu """
        if messagebox.askyesno("Desistir", "Tem certeza que deseja abandonar a partida?"):
            self.network.send({"type": "give_up"})

    def on_click(self, r, c):
        """ Gerencia o clique no tabuleiro baseado na fase do jogo """
        if not self.my_turn: return # Bloqueia se não for o turno do jogador
        
        if self.phase == "PLACEMENT": # Fase de colocar peças
            self.network.send({"type": "place", "pos": (r, c)})
        elif self.phase == "MOVEMENT": # Fase de mover as peças
            if self.selected_piece == (r, c): 
                self.selected_piece = None # Desmarca se clicar na mesma
            elif self.selected_piece:
                # Se já tinha uma selecionada e clicou em outro lugar, tenta mover
                self.network.send({"type": "move", "old_pos": self.selected_piece, "pos": (r, c)})
                self.selected_piece = None
            else:
                # Primeiro clique: seleciona a peça
                self.selected_piece = (r, c)
        elif self.phase == "CAPTURE": # Fase de capturar peça do inimigo
            self.network.send({"type": "capture", "pos": (r, c)})
        
        self.refresh_visuals() # Atualiza as cores localmente (ex: marcar amarelo)

    def draw_board(self, data):
        """ Atualiza todo o visual conforme os dados que vieram do servidor """
        self.phase = data['phase']
        self.my_turn = (data['turn'] == self.player_id)
        self.current_board = data['board']
        
        # Verifica se alguém ganhou
        if data.get("winner"):
            self.my_turn = False
            vencedor_texto = "VOCÊ VENCEU! 🎉" if data["winner"] == self.player_id else f"Jogador {data['winner']} Venceu!"
            self.lbl_status.config(text=vencedor_texto, fg="green" if data["winner"] == self.player_id else "red")
            messagebox.showinfo("Fim de Jogo", vencedor_texto)
        else:
            # Mostra de quem é a vez
            status = "SUA VEZ" if self.my_turn else f"Vez do Jogador {data['turn']}"
            self.lbl_status.config(text=f"{status} | Fase: {self.phase}", fg="black")
            
        self.refresh_visuals()

    def refresh_visuals(self):
        """ Percorre os Canvas e desenha as peças (Ovais) coloridas """
        if not hasattr(self, 'current_board'): return
        colors = {1: "blue", 2: "red"}
        for r in range(5):
            for c in range(6):
                canv = self.btns[r][c]
                canv.delete("all") # Limpa o desenho anterior
                val = self.current_board[r][c]
                if val:
                    # Desenha a peça
                    canv.create_oval(5, 5, 45, 45, fill=colors[val])
                
                # Pinta de amarelo se for a peça selecionada para mover
                bg = "yellow" if self.selected_piece == (r, c) else "white"
                canv.config(bg=bg)

    def send_chat(self, e):
        """ Pega o texto da Entry e envia para o servidor distribuir """
        txt = self.ent_chat.get()
        if txt:
            self.network.send({"type": "chat", "user": f"Jogador {self.player_id}", "text": txt})
            self.ent_chat.delete(0, tk.END)

    def add_chat(self, data):
        """ Adiciona a mensagem recebida na área de texto e rola para baixo """
        self.chat_area.config(state='normal')
        self.chat_area.insert("end", f"{data['user']}: {data['text']}\n")
        self.chat_area.config(state='disabled')
        self.chat_area.see("end") # Scroll automático

# --- INICIALIZAÇÃO DO PROGRAMA ---
if __name__ == "__main__":
    root = tk.Tk()
    DaraClient(root)
    root.mainloop() # Loop infinito da janela