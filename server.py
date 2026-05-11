import Pyro5.api
from engine import DaraEngine
import threading, time
import random

# CONFIGURAÇÃO DE PERFORMANCE: 
# O 'marshal' é um serializador nativo do Python, muito mais rápido que o padrão (Serpent)
# para transmitir listas e dicionários simples como o nosso tabuleiro.
Pyro5.config.SERIALIZER = "marshal"

@Pyro5.api.expose  # Expõe a classe para ser acessível remotamente via RMI
@Pyro5.api.behavior(instance_mode="single")  # Garante que todos os clientes usem a MESMA instância do jogo
class DaraRemoteServer:
    def __init__(self):
        # Inicializa a lógica do jogo (Regras, Tabuleiro, Movimentos)
        self.game = DaraEngine()
        # Dicionário para armazenar o "endereço" (URI) de cada cliente conectado
        self.client_uris = {} 

    def register_client(self, client_uri):
        """ Recebe a URI do cliente e atribui um ID (Jogador 1 ou 2) """
        pid = len(self.client_uris) + 1
        if pid <= 2:
            print(f"[SERVIDOR] Jogador {pid} registrado. URI: {client_uri}")
            self.client_uris[pid] = client_uri
            return pid
        return 0 # Retorna 0 se a sala já estiver cheia
    
    @Pyro5.api.oneway # cliente envia a ação e volta a rodar a UI na hora
    def execute_action(self, player_id, msg):
        """ Processa as jogadas ou desistência enviadas pelos clientes """
        
        # Caso o cliente tenha clicado no botão 'Desistir'
        if msg.get('type') == 'give_up':
            winner = 3 - player_id # O vencedor é o outro jogador
            self.finalizar_jogo(winner, f"O Jogador {player_id} desistiu!")
            return

        # Tenta processar a jogada na Engine (retorna True se for um movimento válido)
        if self.game.process_action(player_id, msg):
            state = self.game.get_state()
            # Se após a jogada alguém venceu
            if state["winner"]:
                self.finalizar_jogo(state["winner"], f"Fim de jogo! Jogador {state['winner']} venceu!")
            else:
                # Se o jogo continua, avisa todos os clientes para redesenharem o tabuleiro
                self.broadcast_update()

    def finalizar_jogo(self, winner, motivo):
        """ Encerra a partida e avisa o vencedor """
        self.send_chat("SISTEMA", motivo)
        state = self.game.get_state()
        state["winner"] = winner # Garante que o estado final tenha o vencedor definido
        
        # Percorre todos os clientes para enviar o estado final
        for uri in self.client_uris.values():
            try:
                with Pyro5.api.Proxy(uri) as p:
                    p.update_ui(state) # Força a atualização da tela final
            except: pass

    def send_chat(self, user, text):
        """ Distribui mensagens de chat para todos os participantes """
        for uri in self.client_uris.values():
            try:
                with Pyro5.api.Proxy(uri) as p:
                    # 'oneway' aqui evita que o servidor trave se um cliente estiver lento
                    p._pyroOneway.add("receive_chat")
                    p.receive_chat(user, text)
            except: pass

    def broadcast_update(self):
        """ Envia o estado atual do tabuleiro para todos os jogadores """
        state = self.game.get_state()
        for pid, uri in self.client_uris.items():
            try:
                # Criamos um Proxy (túnel) temporário para falar com o cliente
                with Pyro5.api.Proxy(uri) as p:
                    p._pyroOneway.add("update_ui")
                    p.update_ui(state)
            except Exception as e:
                print(f"[SERVIDOR] Erro ao atualizar Jogador {pid}: {e}")

    def start_game(self):
        """ Início da partida após os 2 jogadores conectarem """
        print("[SERVIDOR] Realizando sorteio de quem começa...")
        # Lógica de Sorteio Aleatório
        self.game.turn = random.choice([1, 2])
        print(f"[SERVIDOR] O Jogador {self.game.turn} venceu o sorteio!")
        
        # Manda o comando para os clientes saírem do lobby e abrirem o tabuleiro
        for pid, uri in self.client_uris.items():
            try:
                with Pyro5.api.Proxy(uri) as p:
                    p.trigger_start()
            except: pass
        
        # Aguarda 1 segundo para garantir que as janelas do Tkinter abriram
        time.sleep(1) 
        
        # Envia os dados iniciais do tabuleiro e anuncia o vencedor do sorteio no chat
        self.broadcast_update()
        self.send_chat("SISTEMA", f"Partida Iniciada! O Jogador {self.game.turn} começa.")

def run():
    # Daemon: O serviço que fica "ouvindo" as chamadas na rede
    # host '0.0.0.0' permite conexões de qualquer IP na mesma rede
    daemon = Pyro5.api.Daemon(host="0.0.0.0", port=5000)
    instancia = DaraRemoteServer()
    # Registra o objeto com um nome amigável para o cliente encontrar
    uri = daemon.register(instancia, "dara.game")
    
    print("--- SERVIDOR RMI DARA ONLINE ---")
    print(f"URI: {uri}")

    def monitor():
        """ Thread secundária que fica vigiando a sala de espera (Lobby) """
        while len(instancia.client_uris) < 2:
            time.sleep(1)
        print("[SERVIDOR] 2 Jogadores na sala. Chamando start_game...")
        instancia.start_game()
    
    # Inicia a thread de monitoramento para não travar o loop principal do servidor
    threading.Thread(target=monitor, daemon=True).start()
    
    # Loop infinito que mantém o servidor vivo e processando requisições
    daemon.requestLoop()

if __name__ == "__main__":
    run()