import pygame
import time
import threading
import numpy as np
import os
import sys
import logging
import traceback

# --- Tkinter Imports ---
import tkinter as tk
from tkinter import ttk, messagebox

# --- Configuração do Logging (mantida para depuração) ---
LOG_FILENAME = "rb_timer_app_gui.log"
try:
    if hasattr(sys, '_MEIPASS'):
        log_file_path = os.path.join(os.path.dirname(sys.executable), LOG_FILENAME)
    else:
        log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_FILENAME)
except Exception:
    log_file_path = LOG_FILENAME

logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(threadName)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s',
    filemode='w'
)

class StreamToLogger:
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())
    def flush(self): pass

sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

logging.info("-----------------------------------------------------")
logging.info("Aplicação RBTimer com GUI iniciada.")
# --- Fim da Configuração do Logging ---


# --- Configurações Globais ---
RB_BUTTON_INDEX = 5
# DELAY_SECONDS será agora gerenciado pela GUI, mas precisa de um valor inicial
INITIAL_DELAY_SECONDS = 5.2
# Usaremos uma lista para DELAY_SECONDS para que seja mutável e acessível por referência entre threads
# de forma mais simples ou uma instância de uma classe, mas para um valor, uma lista de 1 elemento funciona.
# Melhor ainda: uma variável global que atualizamos com uma função
current_delay_seconds = INITIAL_DELAY_SECONDS # Mutável global

# --- Variáveis Globais para Threads e Pygame ---
timer_event = threading.Event()
last_rb_press_time = 0.0
sound_to_play = None
joystick = None
pygame_running = True # Flag para controlar o loop do Pygame
app_running = True    # Flag geral para controlar a aplicação e threads

# --- Tkinter Variáveis Globais (serão inicializadas na GUI) ---
root = None
status_var = None
delay_var = None
pygame_thread = None
timer_sound_thread = None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
        logging.debug(f"Bundle, base_path: {base_path}")
    except Exception:
        base_path = os.path.abspath(".")
        logging.debug(f"Script, base_path: {base_path}")
    path_to_resource = os.path.join(base_path, relative_path)
    logging.debug(f"Path to resource '{relative_path}': {path_to_resource}")
    return path_to_resource

SOUND_FILE_PATH = resource_path("beep.wav")

def update_status(message):
    if status_var:
        # GUI updates devem ser feitas no thread principal do Tkinter
        root.after(0, lambda: status_var.set(message))
    logging.info(f"Status Update: {message}")

def generate_simple_beep(frequency=440, duration_ms=200, sample_rate=44100):
    update_status("Gerando beep padrão...")
    try:
        n_samples = int(sample_rate * duration_ms / 1000.0)
        buf = np.zeros((n_samples, 2), dtype=np.int16)
        max_sample = 2**(15) - 1
        for s in range(n_samples):
            t = float(s) / sample_rate
            value = int(max_sample * np.sin(2 * np.pi * frequency * t))
            buf[s][0] = value
            buf[s][1] = value
        sound = pygame.sndarray.make_sound(buf)
        update_status("Beep padrão gerado.")
        return sound
    except Exception as e:
        logging.error(f"Falha ao gerar som de beep: {e}", exc_info=True)
        update_status("Falha ao gerar beep.")
        return None

def timer_and_sound_task():
    global last_rb_press_time, sound_to_play, current_delay_seconds
    update_status("Thread do timer iniciada. Aguardando RB...")
    try:
        while app_running: # Usa a flag geral da aplicação
            if not timer_event.wait(timeout=0.5):
                if not app_running: break
                continue
            timer_event.clear()
            current_activation_time = last_rb_press_time
            
            # Garante que estamos lendo a versão mais atual do delay
            delay_to_use = float(delay_var.get()) if delay_var and delay_var.get() else current_delay_seconds
            update_status(f"RB! Timer de {delay_to_use:.1f}s iniciado.")
            
            time_to_wait_remaining = delay_to_use
            
            while time_to_wait_remaining > 0 and app_running:
                wait_interval = min(time_to_wait_remaining, 0.1)
                if timer_event.wait(timeout=wait_interval): # Novo RB pressionado?
                    timer_event.clear()
                    current_activation_time = last_rb_press_time
                    delay_to_use = float(delay_var.get()) if delay_var and delay_var.get() else current_delay_seconds # Re-ler delay
                    update_status(f"RB Reset! Novo timer de {delay_to_use:.1f}s.")
                    time_to_wait_remaining = delay_to_use
                else:
                    elapsed_since_activation = time.time() - current_activation_time
                    time_to_wait_remaining = delay_to_use - elapsed_since_activation
            
            if app_running and time_to_wait_remaining <= 0:
                update_status(f"Timer finalizado. Tocando som...")
                if sound_to_play:
                    try:
                        sound_to_play.play()
                    except pygame.error as e_play:
                        logging.error(f"Erro ao reproduzir som: {e_play}", exc_info=True)
                        update_status("Erro ao tocar som.")
                else:
                    update_status("Nenhum som para tocar.")
                update_status("Aguardando RB...") # Volta ao estado inicial
            elif not app_running:
                update_status("Timer interrompido (app finalizando).")
                break
    except Exception as e_thread:
        logging.critical(f"Erro fatal na thread do timer: {e_thread}", exc_info=True)
        update_status(f"Erro na thread do timer: {e_thread}")
    finally:
        logging.info("Thread do timer finalizada.")
        update_status("Thread do timer finalizada.")


def pygame_loop():
    global joystick, sound_to_play, last_rb_press_time, pygame_running, app_running
    
    try:
        update_status("Inicializando Pygame...")
        pygame.init()
        pygame.joystick.init()
        pygame.mixer.init()
        logging.info("Pygame inicializado.")

        joystick_count = pygame.joystick.get_count()
        logging.info(f"Controles detectados: {joystick_count}")
        if joystick_count == 0:
            update_status("Nenhum controle detectado!")
            # Não vamos sair, a GUI ainda pode funcionar para configurar
        else:
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            update_status(f"Controle: {joystick.get_name()[:30]}") # Limita o nome
            logging.info(f"Controle detectado: {joystick.get_name()}")

        update_status("Carregando som...")
        try:
            sound_to_play = pygame.mixer.Sound(SOUND_FILE_PATH)
            logging.info(f"Arquivo de som '{SOUND_FILE_PATH}' carregado.")
            update_status("Som carregado. Aguardando RB...")
        except pygame.error as e_sound:
            logging.error(f"Não foi possível carregar o som: {e_sound}", exc_info=True)
            update_status("Erro ao carregar som. Tentando beep...")
            sound_to_play = generate_simple_beep()
            if not sound_to_play:
                update_status("Falha no beep. Sem áudio.")
        
        # Loop principal de eventos do Pygame
        while pygame_running and app_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: # Evento de fechar janela Pygame (se houver)
                    logging.info("Evento QUIT do Pygame recebido.")
                    pygame_running = False
                    app_running = False # Sinaliza para toda a aplicação fechar
                    if root: root.event_generate("<<AppClosing>>") # Evento customizado
                    break
                
                if event.type == pygame.JOYBUTTONDOWN:
                    logging.debug(f"Botão do controle pressionado: {event.button}")
                    if joystick and event.instance_id == joystick.get_instance_id() and event.button == RB_BUTTON_INDEX:
                        last_rb_press_time = time.time()
                        timer_event.set() # Sinaliza para a thread do timer

            if not pygame_running: break
            time.sleep(0.02) # Pequena pausa

    except Exception as e_pygame:
        logging.critical(f"Erro crítico na thread Pygame: {e_pygame}", exc_info=True)
        update_status(f"Erro Pygame: {e_pygame}")
    finally:
        pygame.quit()
        logging.info("Thread Pygame e Pygame finalizados.")
        update_status("Pygame finalizado.")
        # Se o Pygame fechar, a aplicação inteira deve fechar
        if app_running: # Se ainda não foi sinalizado para fechar
            app_running = False
            if root: root.event_generate("<<AppClosing>>")


def apply_delay():
    global current_delay_seconds
    try:
        new_delay = float(delay_var.get())
        if new_delay > 0:
            current_delay_seconds = new_delay
            update_status(f"Delay atualizado para: {current_delay_seconds:.1f}s")
            logging.info(f"Delay atualizado para: {current_delay_seconds}")
        else:
            messagebox.showerror("Erro de Validação", "O delay deve ser um número positivo.")
            delay_var.set(f"{current_delay_seconds:.1f}") # Restaura o valor anterior
    except ValueError:
        messagebox.showerror("Erro de Validação", "Por favor, insira um número válido para o delay.")
        delay_var.set(f"{current_delay_seconds:.1f}") # Restaura o valor anterior

def on_app_closing():
    global app_running, pygame_running
    if messagebox.askokcancel("Sair", "Você tem certeza que quer sair?"):
        logging.info("Usuário confirmou o fechamento pela GUI.")
        update_status("Fechando aplicação...")
        app_running = False
        pygame_running = False
        
        if timer_event: timer_event.set() # Acorda a thread do timer para ela verificar app_running

        # Aguarda as threads terminarem
        if pygame_thread and pygame_thread.is_alive():
            logging.info("Aguardando thread Pygame...")
            pygame_thread.join(timeout=2.0)
        if timer_sound_thread and timer_sound_thread.is_alive():
            logging.info("Aguardando thread Timer/Som...")
            timer_sound_thread.join(timeout=2.0)
        
        if root: root.destroy()
        logging.info("Aplicação GUI finalizada.")

def setup_gui():
    global root, status_var, delay_var, current_delay_seconds

    root = tk.Tk()
    root.title("RB Timer")
    root.geometry("350x150") # Tamanho inicial da janela

    # --- Estilo (opcional, para melhorar a aparência) ---
    style = ttk.Style()
    # Tenta usar um tema mais moderno se disponível
    available_themes = style.theme_names()
    logging.debug(f"Temas disponíveis: {available_themes}")
    if "clam" in available_themes: # 'clam', 'alt', 'default', 'classic'
        style.theme_use("clam")
    elif "vista" in available_themes: # No Windows
        style.theme_use("vista")


    # --- Variáveis Tkinter ---
    status_var = tk.StringVar(root, value="Inicializando...")
    delay_var = tk.StringVar(root, value=f"{INITIAL_DELAY_SECONDS:.1f}")
    current_delay_seconds = INITIAL_DELAY_SECONDS # Garante que está sincronizado

    # --- Widgets ---
    main_frame = ttk.Frame(root, padding="10 10 10 10")
    main_frame.pack(expand=True, fill=tk.BOTH)

    status_label_title = ttk.Label(main_frame, text="Status:")
    status_label_title.grid(row=0, column=0, sticky=tk.W, pady=(0,5))
    
    status_display_label = ttk.Label(main_frame, textvariable=status_var, relief=tk.SUNKEN, padding=5, width=40)
    status_display_label.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0,10))

    delay_label = ttk.Label(main_frame, text="Delay (s):")
    delay_label.grid(row=2, column=0, sticky=tk.W, padx=(0,5))

    delay_entry = ttk.Entry(main_frame, textvariable=delay_var, width=10)
    delay_entry.grid(row=2, column=1, sticky=tk.W)

    apply_button = ttk.Button(main_frame, text="Aplicar Delay", command=apply_delay)
    apply_button.grid(row=3, column=0, columnspan=2, pady=(10,0))
    
    # Configurar pesos das colunas para expansão
    main_frame.columnconfigure(0, weight=1)
    main_frame.columnconfigure(1, weight=1)


    # --- Manipulador de Fechamento ---
    root.protocol("WM_DELETE_WINDOW", on_app_closing)
    # Evento customizado para ser disparado por outras threads quando precisam fechar a app
    root.bind("<<AppClosing>>", lambda e: on_app_closing() if app_running else None)


    update_status("GUI Pronta. Iniciando Pygame...")
    return root


if __name__ == "__main__":
    logging.info("Bloco __main__ iniciado.")
    
    try:
        root = setup_gui() # Configura e obtém a janela principal do Tkinter

        # Inicia a thread do Pygame
        pygame_thread = threading.Thread(target=pygame_loop, name="PygameThread", daemon=True)
        pygame_thread.start()

        # Inicia a thread do Timer e Som
        timer_sound_thread = threading.Thread(target=timer_and_sound_task, name="TimerSoundThread", daemon=True)
        timer_sound_thread.start()
        
        root.mainloop() # Inicia o loop principal do Tkinter (bloqueante)

    except Exception as e_global:
        logging.critical(f"Erro global não capturado na inicialização: {e_global}", exc_info=True)
        messagebox.showerror("Erro Crítico", f"Ocorreu um erro fatal:\n{e_global}\nVerifique o arquivo de log.")
    finally:
        logging.info("Aplicação finalizada a partir do bloco __main__.")
        # Garante que as flags de execução sejam falsas se o mainloop terminar por algum motivo
        app_running = False
        pygame_running = False
        if timer_event: timer_event.set() # Acorda threads que possam estar esperando

        # Tenta um join final se as threads ainda estiverem vivas (pouco provável se on_app_closing funcionou)
        if pygame_thread and pygame_thread.is_alive(): pygame_thread.join(timeout=0.5)
        if timer_sound_thread and timer_sound_thread.is_alive(): timer_sound_thread.join(timeout=0.5)
        
        logging.info("------------------ FIM DA EXECUÇÃO ------------------")