import sys
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORTA_LB = 8080
SERVIDORES = [
    "http://127.0.0.1:8001",
    "http://127.0.0.1:8002",
    "http://127.0.0.1:8003"
]
INTERVALO_HEALTH_CHECK = 2.0

algoritmo_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "rr"
ALGORITMO = "LeastConnections" if algoritmo_arg == "lc" else "RoundRobin"

indice_atual = 0
trava_lb = threading.Lock()
conexoes_ativas = {s: 0 for s in SERVIDORES}
total_atendidas = {s: 0 for s in SERVIDORES}
status_saude = {s: True for s in SERVIDORES}


def formatar_metricas(dicionario):
    partes = [f"{s.split(':')[-1]}:{v}" for s, v in dicionario.items()]
    return " ".join(partes)


def formatar_saude():
    partes = [f"{s.split(':')[-1]}:{'ON' if status_saude[s] else 'OFF'}" for s in SERVIDORES]
    return " ".join(partes)


def adquirir_servidor(ignorados=None):
    global indice_atual
    if ignorados is None:
        ignorados = set()

    with trava_lb:
        disponiveis = [s for s in SERVIDORES if status_saude[s] and s not in ignorados]
        if not disponiveis:
            return None, formatar_metricas(conexoes_ativas), formatar_metricas(total_atendidas)

        total_servidores = len(SERVIDORES)
        escolhido = None

        if ALGORITMO == "RoundRobin":
            for i in range(total_servidores):
                candidato = SERVIDORES[(indice_atual + i) % total_servidores]
                if candidato in disponiveis:
                    escolhido = candidato
                    indice_atual = (SERVIDORES.index(escolhido) + 1) % total_servidores
                    break
        else:
            menor_carga = None
            for i in range(total_servidores):
                candidato = SERVIDORES[(indice_atual + i) % total_servidores]
                if candidato in disponiveis:
                    carga = conexoes_ativas[candidato]
                    if menor_carga is None or carga < menor_carga:
                        menor_carga = carga
                        escolhido = candidato
            indice_atual = (SERVIDORES.index(escolhido) + 1) % total_servidores

        conexoes_ativas[escolhido] += 1
        return escolhido, formatar_metricas(conexoes_ativas), formatar_metricas(total_atendidas)


def registrar_sucesso(servidor):
    with trava_lb:
        total_atendidas[servidor] += 1
        return formatar_metricas(conexoes_ativas), formatar_metricas(total_atendidas), formatar_saude()


def marcar_servidor_offline(servidor, motivo):
    with trava_lb:
        if status_saude[servidor]:
            status_saude[servidor] = False
            porta = servidor.split(":")[-1]
            print(
                f"[LB Health] QUEDA DETECTADA na instancia {porta} ({motivo}) | "
                f"Status: [{formatar_saude()}]",
                flush=True
            )


def liberar_servidor(servidor):
    with trava_lb:
        if conexoes_ativas[servidor] > 0:
            conexoes_ativas[servidor] -= 1


def monitorar_saude_servidores():
    while True:
        for servidor in SERVIDORES:
            url_health = f"{servidor}/health"
            saudavel_agora = False
            try:
                req = urllib.request.Request(url_health, method="GET")
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        saudavel_agora = True
            except Exception:
                saudavel_agora = False

            with trava_lb:
                estava_saudavel = status_saude[servidor]
                if estava_saudavel and not saudavel_agora:
                    status_saude[servidor] = False
                    porta = servidor.split(":")[-1]
                    print(
                        f"[LB Health] Instancia {porta} OFFLINE no Health Check | "
                        f"Status: [{formatar_saude()}]",
                        flush=True
                    )
                elif not estava_saudavel and saudavel_agora:
                    status_saude[servidor] = True
                    porta = servidor.split(":")[-1]
                    print(
                        f"[LB Health] Instancia {porta} RECUPERADA e reintegrada | "
                        f"Status: [{formatar_saude()}]",
                        flush=True
                    )
        time.sleep(INTERVALO_HEALTH_CHECK)


class ServidorBalanceador(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class ManipuladorBalanceador(BaseHTTPRequestHandler):

    def do_GET(self):
        tentativas_falhas = set()

        while len(tentativas_falhas) < len(SERVIDORES):
            destino, _, _ = adquirir_servidor(ignorados=tentativas_falhas)
            if destino is None:
                break

            url_destino = f"{destino}{self.path}"
            porta_destino = destino.split(":")[-1]

            try:
                req = urllib.request.Request(url_destino, method="GET")
                with urllib.request.urlopen(req, timeout=3.0) as resposta:
                    corpo = resposta.read()
                    ativas_str, total_str, saude_str = registrar_sucesso(destino)
                    print(
                        f"[LB] Destino: {porta_destino} | Alg: {ALGORITMO} | "
                        f"Nos: [{saude_str}] | Acumulado: [{total_str}]",
                        flush=True
                    )
                    self.send_response(resposta.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(corpo)))
                    self.end_headers()
                    self.wfile.write(corpo)
                    return
            except Exception as erro:
                tentativas_falhas.add(destino)
                marcar_servidor_offline(destino, type(erro).__name__)
                print(
                    f"[LB Failover] Redirecionando requisicao que falhou na instancia {porta_destino}...",
                    flush=True
                )
            finally:
                liberar_servidor(destino)

        erro_json = json.dumps({
            "erro": "Nenhum servidor disponivel na ShopNow",
            "status_cluster": formatar_saude()
        }).encode("utf-8")
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(erro_json)))
        self.end_headers()
        self.wfile.write(erro_json)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    thread_hc = threading.Thread(target=monitorar_saude_servidores, daemon=True)
    thread_hc.start()

    balanceador = ServidorBalanceador(("127.0.0.1", PORTA_LB), ManipuladorBalanceador)
    print(
        f"[LB] Balanceador iniciado em http://127.0.0.1:{PORTA_LB} | "
        f"Algoritmo: {ALGORITMO} | Health Check: Ativo ({INTERVALO_HEALTH_CHECK}s)",
        flush=True
    )
    try:
        balanceador.serve_forever()
    except KeyboardInterrupt:
        print("\n[LB] Balanceador encerrado.", flush=True)
        balanceador.server_close()