import tkinter as tk
from tkinter import messagebox, scrolledtext
import Pyro5.api
import Pyro5.socketutil
import threading

# =============================================================================
# CLASSE DE CALLBACK (RECEBIMENTO DE DADOS)
# =============================================================================
@Pyro5.api.expose
class ClientCallback:
    """ 
    Classe que permite o servidor principal 
    chamar estes métodos remotamente para atualizar o jogador.
    """
    def __init__(self, ui):
        self.ui = ui # Referência para a classe principal da interface

    def update_ui(self, data):
        """ Recebe o novo estado do tabuleiro e turno do servidor """
        #thread principal, evitando que o programa trave ou feche.
        self.ui.root.after(0, self.ui.draw_board, data)

    def trigger_start(self):
        """ Chamado pelo servidor para avisar que 2 jogadores conectaram e o jogo pode começar """
        self.ui.root.after(0, self.ui.setup_game_ui)

    def receive_chat(self, user, text):
        """ Recebe mensagens de chat enviadas por outros jogadores através do servidor """
        self.ui.root.after(0, self.ui.add_chat, {"user": user, "text": text})

# =============================================================================
# CLASSE DE CONEXÃO RMI (HANDLER DE REDE)
# =============================================================================
class RMIHandler:
    """ 
    Gerencia toda a lógica de saída (Cliente -> Servidor).
    """
    def __init__(self, ui):
        self.ui = ui
        self.server_uri = None 

    def connect(self, ip_servidor):
        """ Estabelece a conexão inicial e configura o canal de retorno (callback) """
        try:
            # 1. Define o endereço RMI do servidor baseado no IP digitado
            self.server_uri = f"PYRO:dara.game@{ip_servidor}:5000"
            
            # 2. Descoberta de IP Automática: 
            # O Pyro identifica qual placa de rede usar para falar com o servidor.
            meu_ip = Pyro5.socketutil.get_ip_address(ip_servidor)
            
            # 3. Cria o Daemon: O "serviço" que permite ao servidor chamar o cliente de volta.
            daemon = Pyro5.api.Daemon(host=meu_ip)
            cb_instancia = ClientCallback(self.ui)
            cb_uri = daemon.register(cb_instancia) # Gera um endereço único para este cliente
            
            # 4. Thread de Escuta: Fica rodando no fundo esperando chamadas do servidor
            threading.Thread(target=daemon.requestLoop, daemon=True).start()
            
            # 5. Registro no Servidor: O cliente envia seu 'endereço de volta' (cb_uri)
            # e recebe seu número de jogador (1 ou 2).
            with Pyro5.api.Proxy(self.server_uri) as proxy:
                self.ui.player_id = proxy.register_client(cb_uri)
            
            print(f"[REDE] Conectado RMI. IP Local: {meu_ip} | ID: {self.ui.player_id}")
            
        except Exception as e:
            messagebox.showerror("Erro de Rede", f"Não foi possível conectar: {e}")

    def send(self, data):
        """ Envia dados para o servidor sem travar a interface do usuário """
        def async_send():
            try:
                with Pyro5.api.Proxy(self.server_uri) as proxy:
                    if data['type'] == 'chat':
                        proxy.send_chat(data['user'], data['text'])
                    else:
                        proxy.execute_action(self.ui.player_id, data)
            except Exception as e:
                print(f"[ERRO RPC] Falha no envio: {e}")
        
        # Dispara o envio em uma thread separada (Assíncrono)
        threading.Thread(target=async_send, daemon=True).start()

# =============================================================================
# CLASSE DA INTERFACE GRÁFICA (GUI)
# =============================================================================
class DaraClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Dara - Jogo de Tabuleiro RMI")
        self.network = RMIHandler(self)
        
        # Variáveis de controle do Jogo
        self.player_id = None
        self.my_turn = False
        self.phase = "PLACEMENT" # PLACEMENT, MOVEMENT ou CAPTURE
        self.selected_piece = None # Guarda (r, c) da peça que o jogador quer mover
        self.btns = [[None for _ in range(6)] for _ in range(5)]
        
        self.setup_lobby()

    def setup_lobby(self):
        """ Tela inicial para digitar o IP e conectar """
        self.lobby = tk.Frame(self.root, padx=20, pady=20)
        self.lobby.pack()
        tk.Label(self.lobby, text="Digite o IP do Servidor:", font=("Arial", 10)).pack()
        self.ent_ip = tk.Entry(self.lobby, justify="center")
        self.ent_ip.insert(0, "127.0.0.1")
        self.ent_ip.pack(pady=5)
        
        self.btn_conn = tk.Button(self.lobby, text="Entrar no Jogo", bg="#2ecc71", fg="white",
                                  command=lambda: self.network.connect(self.ent_ip.get()))
        self.btn_conn.pack(pady=10)

    def setup_game_ui(self):
        """ Constrói a tela do jogo (Tabuleiro + Chat) após a conexão bem-sucedida """
        self.lobby.destroy()
        self.main_container = tk.Frame(self.root, padx=10, pady=10)
        self.main_container.pack()

        # Identificação visual do Jogador
        cor_nome = "Azul" if self.player_id == 1 else "Vermelho"
        cor_hex = "#3498db" if self.player_id == 1 else "#e74c3c"
        
        tk.Label(self.main_container, text=f"VOCÊ É O JOGADOR {self.player_id} ({cor_nome})", 
                 fg=cor_hex, font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=2, pady=5)

        # Painel do Tabuleiro
        left_frame = tk.Frame(self.main_container)
        left_frame.grid(row=1, column=0, sticky="n")

        self.lbl_status = tk.Label(left_frame, text="Aguardando sorteio...", font=('Arial', 10, 'italic'))
        self.lbl_status.pack(pady=5)
        
        board_grid = tk.Frame(left_frame, bg="#2c3e50", padx=3, pady=3)
        board_grid.pack()

        for r in range(5):
            for c in range(6):
                canv = tk.Canvas(board_grid, width=50, height=50, bg="white", highlightthickness=1)
                canv.grid(row=r, column=c, padx=1, pady=1)
                # O clique envia a posição (linha, coluna) para processamento
                canv.bind("<Button-1>", lambda e, r=r, c=c: self.on_click(r, c))
                self.btns[r][c] = canv

        # Painel Lateral (Chat)
        right_frame = tk.Frame(self.main_container, padx=10)
        right_frame.grid(row=1, column=1, sticky="n")

        tk.Label(right_frame, text="CHAT DA PARTIDA", font=('Arial', 9, 'bold')).pack()
        self.chat_area = scrolledtext.ScrolledText(right_frame, width=35, height=15, state='disabled', wrap='word')
        self.chat_area.pack(pady=5)
        
        self.ent_chat = tk.Entry(right_frame)
        self.ent_chat.pack(fill="x")
        self.ent_chat.bind("<Return>", self.send_chat) # Envia ao apertar Enter

        self.btn_desistir = tk.Button(right_frame, text="Desistir", bg="#e74c3c", fg="white", 
                                      command=self.confirmar_desistencia)
        self.btn_desistir.pack(fill="x", pady=10)

    def on_click(self, r, c):
        """ Trata a lógica de clique do mouse de acordo com a fase do jogo """
        if not self.my_turn: return # Ignora cliques se não for o turno do jogador
        
        if self.phase == "PLACEMENT":
            self.network.send({"type": "place", "pos": (r, c)})
            
        elif self.phase == "MOVEMENT":
            if self.selected_piece == (r, c): 
                self.selected_piece = None # Desmarca a peça
            elif self.selected_piece:
                # Se já tem uma selecionada, tenta mover para o novo local
                self.network.send({"type": "move", "old_pos": self.selected_piece, "pos": (r, c)})
                self.selected_piece = None
            else:
                self.selected_piece = (r, c) # Seleciona a peça para mover
                
        elif self.phase == "CAPTURE":
            self.network.send({"type": "capture", "pos": (r, c)})
        
        self.refresh_visuals() # Atualiza o feedback visual imediato

    def draw_board(self, data):
        """ Reconstrói o tabuleiro com base nos dados oficiais vindos do servidor """
        self.phase = data['phase']
        self.my_turn = (data['turn'] == self.player_id)
        self.current_board = data['board']
        
        # Atualiza a mensagem de status (Vez de quem / Fim de jogo)
        if data.get("winner"):
            self.my_turn = False
            msg = "VITÓRIA! 🎉" if data["winner"] == self.player_id else "DERROTA..."
            self.lbl_status.config(text=msg, fg="green" if data["winner"] == self.player_id else "red")
            messagebox.showinfo("Partida Encerrada", f"O Jogador {data['winner']} venceu!")
        else:
            status = "SUA VEZ!" if self.my_turn else "Aguarde o oponente..."
            self.lbl_status.config(text=f"{status} | Fase: {self.phase}", fg="#15d822" if self.my_turn else "black")
        
        self.refresh_visuals()

    def refresh_visuals(self):
        """ Pinta as peças no tabuleiro e destaca a peça selecionada """
        if not hasattr(self, 'current_board'): return
        cores = {1: "#3498db", 2: "#e74c3c"} # Azul e Vermelho
        
        for r in range(5):
            for c in range(6):
                canv = self.btns[r][c]
                canv.delete("all") # Limpa desenhos anteriores
                
                peca = self.current_board[r][c]
                if peca:
                    canv.create_oval(7, 7, 43, 43, fill=cores[peca], outline="black")
                
                # Highlight amarelo se a peça estiver selecionada para movimento
                bg_cor = "#f1c40f" if self.selected_piece == (r, c) else "white"
                canv.config(bg=bg_cor)

    def send_chat(self, event):
        """ Envia a mensagem do chat para o servidor """
        msg = self.ent_chat.get()
        if msg.strip():
            self.network.send({"type": "chat", "user": f"P{self.player_id}", "text": msg})
            self.ent_chat.delete(0, tk.END)

    def add_chat(self, data):
        """ Adiciona texto na janela de chat e rola para o fim """
        self.chat_area.config(state='normal')
        self.chat_area.insert("end", f"{data['user']}: {data['text']}\n")
        self.chat_area.config(state='disabled')
        self.chat_area.see("end")

    def confirmar_desistencia(self):
        if messagebox.askyesno("Desistir", "Sair agora contará como derrota. Confirmar?"):
            self.network.send({"type": "give_up"})

# =============================================================================
# EXECUÇÃO DO CLIENTE
# =============================================================================
if __name__ == "__main__":
    app = tk.Tk()
    DaraClient(app)
    app.mainloop()