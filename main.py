import tkinter as tk
from tkinter import ttk, messagebox
import pygame
import time
import threading
import numpy as np
import os
import sys
import logging
import traceback

# --- Configuração do Logging ---
LOG_FILENAME = "farm_helper_gui.log"
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

logging.info("-----------------------------------------------------")
logging.info("Aplicação FarmHelper GUI: Início do script.")

try:
    import pygame
    logging.info(f"Pygame importado com sucesso. Versão: {pygame.version.ver}")
except ImportError:
    logging.error("FALHA AO IMPORTAR PYGAME. O módulo 'pygame' não foi encontrado.")
    print("AVISO DE MÓDULO: O módulo 'pygame' não foi encontrado. O som personalizado e a detecção de controle não funcionarão. Instale com: pip install pygame")
    pygame = None

# --- Configurações Globais da Lógica Base ---
ACTION_BUTTON_INDEX_DEFAULT = 5 # RB como padrão
INITIAL_DELAY_SECONDS = 5.2
current_delay_seconds = INITIAL_DELAY_SECONDS
program_start_time = time.time()
action_press_count = 0

timer_event = threading.Event()
last_action_press_time = 0.0
sound_to_play = None
joystick = None
pygame_running = True
app_running = True

# --- Variáveis de Controle de Captura de Botão ---
capturing_button_mode = False
target_button_index = ACTION_BUTTON_INDEX_DEFAULT # Inicializa com o padrão RB

# --- Variáveis Globais para a UI ---
ui_root = None
ui_status_var = None
ui_delay_var = None
ui_controller_status_var = None
ui_time_remaining_var = None
ui_progress_var = None
ui_program_runtime_var = None
ui_action_press_count_var = None
ui_action_button_display_var = None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
        logging.debug(f"Bundle, base_path: {base_path}")
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
        logging.debug(f"Script, base_path: {base_path}")
    path_to_resource = os.path.join(base_path, relative_path)
    logging.debug(f"Path to resource '{relative_path}': {path_to_resource}")
    return path_to_resource

logging.info("Prestes a chamar resource_path para SOUND_FILE_PATH.")
SOUND_FILE_PATH = resource_path("beep.wav")
logging.info(f"SOUND_FILE_PATH definido como: {SOUND_FILE_PATH}")


def update_main_status_ui(message):
    if ui_root and ui_status_var and ui_root.winfo_exists():
        ui_root.after(0, lambda: ui_status_var.set(message))
    logging.info(f"Status UI Principal: {message}")

def update_controller_status_ui(message):
    if ui_root and ui_controller_status_var and ui_root.winfo_exists():
        ui_root.after(0, lambda: ui_controller_status_var.set(message))
    logging.info(f"Status Controle UI: {message}")

def update_action_button_display_ui():
    global target_button_index
    if ui_root and ui_action_button_display_var and ui_root.winfo_exists():
        display_text = f"Índice: {target_button_index}" if target_button_index is not None else "Nenhum (Clique em 'Definir Botão')"
        ui_root.after(0, lambda: ui_action_button_display_var.set(display_text))
    logging.info(f"Display do botão de ação atualizado para: {target_button_index}")


def update_timer_display_ui(remaining_seconds, current_target_delay):
    if ui_root and ui_time_remaining_var and ui_root.winfo_exists():
        minutes = int(remaining_seconds // 60)
        seconds_part = remaining_seconds % 60
        ui_root.after(0, lambda m=minutes, s=seconds_part: ui_time_remaining_var.set(f"{m:02d}:{s:05.2f}"))

    if ui_root and ui_progress_var and current_target_delay > 0 and ui_root.winfo_exists():
        progress = ((current_target_delay - remaining_seconds) / current_target_delay) * 100
        progress = max(0, min(100, progress))
        ui_root.after(0, lambda p=progress: ui_progress_var.set(p))

def update_runtime_stats_ui():
    global app_running, program_start_time
    if ui_root and ui_program_runtime_var and app_running and ui_root.winfo_exists():
        elapsed_seconds = time.time() - program_start_time
        hours = int(elapsed_seconds // 3600)
        minutes = int((elapsed_seconds % 3600) // 60)
        seconds = int(elapsed_seconds % 60)
        ui_program_runtime_var.set(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        if ui_root.winfo_exists():
            ui_root.after(1000, update_runtime_stats_ui)

def update_action_press_count_ui():
    global action_press_count
    if ui_root and ui_action_press_count_var and ui_root.winfo_exists():
        ui_action_press_count_var.set(str(action_press_count))

def increment_action_press_count_and_update_ui():
    global action_press_count
    action_press_count += 1
    update_action_press_count_ui()

def generate_simple_beep(frequency=440, duration_ms=200, sample_rate=44100):
    if not (pygame and hasattr(pygame, 'sndarray')):
        logging.warning("Pygame sndarray não disponível para gerar beep.")
        return None
    update_main_status_ui("Gerando beep padrão...")
    try:
        n_samples = int(sample_rate * duration_ms / 1000.0)
        buf = np.zeros((n_samples, 2), dtype=np.int16)
        max_sample = 2**(15) - 1
        for s_idx in range(n_samples):
            t_sample = float(s_idx) / sample_rate
            value = int(max_sample * np.sin(2 * np.pi * frequency * t_sample))
            buf[s_idx][0] = value
            buf[s_idx][1] = value
        sound = pygame.sndarray.make_sound(buf)
        update_main_status_ui("Beep padrão gerado.")
        return sound
    except Exception as e_beep:
        logging.error(f"Falha ao gerar som de beep: {e_beep}", exc_info=True)
        update_main_status_ui("Falha ao gerar beep.")
        return None

def timer_and_sound_task():
    global last_action_press_time, sound_to_play, current_delay_seconds, app_running
    logging.info("Thread timer_and_sound_task iniciada.")
    update_main_status_ui("Aguardando Botão de Ação...")
    try:
        while app_running:
            if not timer_event.wait(timeout=0.5):
                if not app_running:
                    logging.debug("timer_and_sound_task: app_running é False, saindo do loop de espera.")
                    break
                continue

            logging.debug("timer_and_sound_task: timer_event recebido.")
            timer_event.clear()
            current_activation_time = last_action_press_time

            delay_to_use = float(ui_delay_var.get()) if ui_root and ui_delay_var and ui_delay_var.get() else current_delay_seconds
            update_main_status_ui(f"Botão! Timer de {delay_to_use:.1f}s iniciado.")
            logging.info(f"Timer iniciado com delay: {delay_to_use}s")

            time_elapsed_total = 0

            while time_elapsed_total < delay_to_use and app_running:
                time_remaining = delay_to_use - time_elapsed_total
                update_timer_display_ui(time_remaining, delay_to_use)
                wait_interval = min(time_remaining, 0.05)

                if timer_event.wait(timeout=wait_interval):
                    logging.debug("timer_and_sound_task: timer_event recebido durante a contagem (reset).")
                    timer_event.clear()
                    current_activation_time = last_action_press_time
                    delay_to_use = float(ui_delay_var.get()) if ui_root and ui_delay_var and ui_delay_var.get() else current_delay_seconds
                    update_main_status_ui(f"Botão Reset! Novo timer de {delay_to_use:.1f}s.")
                    logging.info(f"Timer resetado com novo delay: {delay_to_use}s")
                    time_elapsed_total = 0
                    continue

                if not app_running:
                    logging.debug("timer_and_sound_task: app_running é False, saindo do loop de contagem.")
                    break
                time_elapsed_total = time.time() - current_activation_time

            if app_running and time_elapsed_total >= delay_to_use:
                update_timer_display_ui(0, delay_to_use)
                update_main_status_ui("Timer finalizado. Tocando som...")
                logging.info("Timer finalizado, tentando tocar som.")

                should_play_sound = True
                if FarmHelperApp.instance and FarmHelperApp.instance.sound_enabled_var:
                    should_play_sound = FarmHelperApp.instance.sound_enabled_var.get()

                if should_play_sound and sound_to_play:
                    try:
                        # O volume já foi definido no sound_to_play pelo slider
                        sound_to_play.play()
                        logging.debug("Som reproduzido.")
                    except pygame.error as e_play:
                        logging.error(f"Erro ao reproduzir som: {e_play}", exc_info=True)
                        update_main_status_ui("Erro ao tocar som.")
                elif not sound_to_play:
                    update_main_status_ui("Nenhum som para tocar.")
                    logging.warning("Tentativa de tocar som, mas sound_to_play é None.")
                else:
                    update_main_status_ui("Som desabilitado.")
                    logging.info("Som desabilitado pela UI.")
                update_main_status_ui("Aguardando Botão de Ação...")
            elif not app_running:
                update_main_status_ui("Timer interrompido (app_running False).")
                logging.info("Timer interrompido pois app_running se tornou False.")
                break
    except Exception as e_thread:
        logging.critical(f"Erro fatal na thread do timer: {e_thread}", exc_info=True)
        update_main_status_ui(f"Erro na thread do timer: {e_thread}")
    finally:
        logging.info("Thread timer_and_sound_task finalizada.")
        if app_running: update_main_status_ui("Thread do timer parada.")


def pygame_loop():
    global joystick, sound_to_play, last_action_press_time, pygame_running, app_running, \
           capturing_button_mode, target_button_index
    logging.info("Thread pygame_loop iniciada.")

    if not pygame:
        logging.error("Pygame não está disponível no início do pygame_loop. Encerrando thread.")
        update_controller_status_ui("🔴 Pygame não disponível.")
        return

    try:
        update_controller_status_ui("Inicializando Pygame...")
        pygame.init()
        if not pygame.get_init():
            logging.error("Falha ao inicializar Pygame dentro do pygame_loop.")
            update_controller_status_ui("🔴 Falha Pygame Init.")
            return

        pygame.joystick.init()
        if not pygame.joystick.get_init():
            logging.warning("Módulo Pygame Joystick não pôde ser inicializado.")
            update_controller_status_ui("⚠️ Joystick não disponível.")

        pygame.mixer.init()
        if not pygame.mixer.get_init():
            logging.warning("Módulo Pygame Mixer não pôde ser inicializado.")
            update_main_status_ui("⚠️ Mixer de áudio não disponível.")
        else: # Se o mixer inicializou, definir o volume global do mixer (para futuros sons se necessário)
            if FarmHelperApp.instance and FarmHelperApp.instance.volume_var:
                 # pygame.mixer.music.set_volume(FarmHelperApp.instance.volume_var.get()) # Para música
                 pass # Para sons individuais, o volume é definido no objeto Sound

        logging.info("Pygame (core, joystick, mixer) inicializado/verificado no pygame_loop.")

        joystick_count = pygame.joystick.get_count()
        logging.info(f"Controles detectados: {joystick_count}")
        if joystick_count == 0:
            update_controller_status_ui("Nenhum controle detectado!")
        else:
            try:
                joystick = pygame.joystick.Joystick(0)
                joystick.init()
                controller_name = joystick.get_name()
                update_controller_status_ui(f"🟢 {controller_name[:30]}")
                logging.info(f"Controle detectado: {controller_name}")
            except pygame.error as e_joy_init:
                logging.error(f"Erro ao inicializar joystick 0: {e_joy_init}")
                update_controller_status_ui("🔴 Erro ao iniciar controle.")

        try:
            if os.path.exists(SOUND_FILE_PATH):
                sound_to_play = pygame.mixer.Sound(SOUND_FILE_PATH)
                logging.info(f"Arquivo de som '{SOUND_FILE_PATH}' carregado.")
            else:
                logging.warning(f"Arquivo de som '{SOUND_FILE_PATH}' não encontrado. Gerando beep.")
                update_main_status_ui("Arquivo beep.wav não encontrado. Gerando som...")
                sound_to_play = generate_simple_beep()
        except pygame.error as e_sound:
            logging.error(f"Não foi possível carregar o som '{SOUND_FILE_PATH}': {e_sound}", exc_info=True)
            update_main_status_ui("Erro ao carregar som. Tentando beep...")
            sound_to_play = generate_simple_beep()

        if not sound_to_play:
            update_main_status_ui("Falha no beep. Sem áudio.")
            logging.error("sound_to_play continua None após tentativas de carga/geração.")
        else:
            # --- NOVO: Aplicar volume inicial ao som carregado ---
            if FarmHelperApp.instance and FarmHelperApp.instance.volume_var:
                initial_volume = FarmHelperApp.instance.volume_var.get()
                sound_to_play.set_volume(initial_volume)
                logging.info(f"Volume inicial do som '{SOUND_FILE_PATH or 'beep'}' definido para {initial_volume:.2f}")


        while pygame_running and app_running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    logging.info("Evento QUIT do Pygame recebido.")
                    pygame_running = False; app_running = False
                    if ui_root and ui_root.winfo_exists(): ui_root.event_generate("<<AppClosing>>")
                    break

                if event.type == pygame.JOYDEVICEADDED:
                    logging.info(f"Novo joystick detectado: {event.device_index}")
                    joystick_count = pygame.joystick.get_count()
                    if joystick_count > 0 and (joystick is None or not joystick.get_init()):
                        try:
                            new_joystick_idx = event.device_index
                            joystick = pygame.joystick.Joystick(new_joystick_idx)
                            joystick.init()
                            controller_name = joystick.get_name()
                            update_controller_status_ui(f"🟢 {controller_name[:30]}")
                            logging.info(f"Novo controle conectado: {controller_name}")
                        except pygame.error as e_joy_add:
                            logging.error(f"Erro ao inicializar novo joystick {new_joystick_idx}: {e_joy_add}")
                            update_controller_status_ui("🔴 Erro ao adicionar controle.")

                if event.type == pygame.JOYDEVICEREMOVED:
                    logging.info(f"Joystick removido: instance_id {event.instance_id}")
                    if joystick and hasattr(joystick, 'get_instance_id') and event.instance_id == joystick.get_instance_id():
                        joystick.quit()
                        joystick = None
                        update_controller_status_ui("🔴 Controle desconectado.")
                        if pygame.joystick.get_count() > 0:
                            try:
                                joystick = pygame.joystick.Joystick(0)
                                joystick.init()
                                controller_name = joystick.get_name()
                                update_controller_status_ui(f"🟢 {controller_name[:30]} (Alternativo)")
                                logging.info(f"Controle alternativo conectado: {controller_name}")
                            except pygame.error as e_joy_alt:
                                logging.error(f"Erro ao inicializar joystick alternativo: {e_joy_alt}")
                                update_controller_status_ui("🔴 Erro controle alternativo.")

                if event.type == pygame.JOYBUTTONDOWN:
                    if capturing_button_mode:
                        target_button_index = event.button
                        capturing_button_mode = False
                        update_action_button_display_ui()
                        update_main_status_ui(f"Botão de Ação definido: Índice {target_button_index}. Aguardando...")
                        logging.info(f"Modo de captura: Botão {target_button_index} capturado.")
                        if FarmHelperApp.instance and hasattr(FarmHelperApp.instance, 'define_button_btn'):
                            if FarmHelperApp.instance.define_button_btn.winfo_exists():
                                FarmHelperApp.instance.define_button_btn.config(state=tk.NORMAL, text="🎯 Definir Botão de Ação")

                    elif target_button_index is not None:
                        logging.debug(f"Botão do controle pressionado: {event.button} no joystick {event.instance_id}. Alvo: {target_button_index}")
                        if joystick and hasattr(joystick, 'get_instance_id') and \
                           event.instance_id == joystick.get_instance_id() and \
                           event.button == target_button_index:
                            logging.info(f"Botão de Ação ({target_button_index}) Pressionado no controle!")
                            last_action_press_time = time.time()
                            increment_action_press_count_and_update_ui()
                            timer_event.set()
            if not pygame_running: break
            time.sleep(0.02)
    except Exception as e_pygame:
        logging.critical(f"Erro crítico na thread Pygame: {e_pygame}", exc_info=True)
        update_controller_status_ui(f"Erro Pygame: {e_pygame}")
    finally:
        if pygame and pygame.get_init():
            pygame.quit()
        logging.info("Thread Pygame e Pygame finalizados.")
        if app_running : update_controller_status_ui("Pygame finalizado.")
        if app_running:
            app_running = False
            if ui_root and ui_root.winfo_exists(): ui_root.event_generate("<<AppClosing>>")

class ScrolledFrame(ttk.Frame):
    def __init__(self, parent, *args, **kw):
        canvas_bg_color = kw.pop('bg', '#1a1a1a')
        ttk.Frame.__init__(self, parent, *args, **kw)

        vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=tk.FALSE)
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0,
                                yscrollcommand=vscrollbar.set, bg=canvas_bg_color)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.TRUE)
        vscrollbar.config(command=self.canvas.yview)
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.interior = ttk.Frame(self.canvas, style='Interior.TFrame', padding=kw.get('padding', (5,5)))
        self.interior_id = self.canvas.create_window(0, 0, window=self.interior, anchor=tk.NW)
        self.interior.bind('<Configure>', self._configure_interior)
        self.canvas.bind('<Configure>', self._configure_canvas)

    def _configure_interior(self, event):
        size = (self.interior.winfo_reqwidth(), self.interior.winfo_reqheight())
        self.canvas.config(scrollregion=(0, 0, size[0], size[1]))
        if self.interior.winfo_reqwidth() != self.canvas.winfo_width():
            self.canvas.config(width=max(self.interior.winfo_reqwidth(), self.canvas.winfo_width()))

    def _configure_canvas(self, event):
        if self.interior.winfo_reqwidth() != self.canvas.winfo_width():
            self.canvas.itemconfigure(self.interior_id, width=self.canvas.winfo_width())

class FarmHelperApp:
    instance = None
    def __init__(self, master_root):
        global ui_root, ui_status_var, ui_delay_var, ui_controller_status_var, \
               ui_time_remaining_var, ui_progress_var, current_delay_seconds, \
               ui_program_runtime_var, ui_action_press_count_var, ui_action_button_display_var

        FarmHelperApp.instance = self
        self.master_root = master_root
        ui_root = master_root
        self.master_root.title("🎮 FarmHelper Pro - Gaming Timer Assistant")
        self.master_root.geometry("1400x750")
        self.master_root.minsize(1200, 600)
        self.master_root.configure(bg='#0d1117')
        self.center_window()

        ui_status_var = tk.StringVar(master_root, value="🚀 Inicializando sistema...")
        ui_delay_var = tk.StringVar(master_root, value=f"{INITIAL_DELAY_SECONDS:.1f}")
        current_delay_seconds = INITIAL_DELAY_SECONDS
        ui_controller_status_var = tk.StringVar(master_root, value="🔍 Verificando controles...")
        ui_time_remaining_var = tk.StringVar(master_root, value="--:--")
        ui_progress_var = tk.DoubleVar(master_root, value=0.0)
        self.sound_enabled_var = tk.BooleanVar(master_root, value=True)
        ui_program_runtime_var = tk.StringVar(master_root, value="00:00:00")
        ui_action_press_count_var = tk.StringVar(master_root, value="0")
        ui_action_button_display_var = tk.StringVar(master_root, value=f"Índice: {target_button_index}")

        # --- NOVO: Variável para o volume ---
        self.initial_volume = 0.7 # 70%
        self.volume_var = tk.DoubleVar(master_root, value=self.initial_volume)


        self.setup_styles()
        self.create_widgets() # Chamado após setup_styles
        self.setup_ui_bindings()

        update_main_status_ui("✅ Interface carregada com sucesso!")
        if ui_root.winfo_exists():
            update_runtime_stats_ui()
        update_action_press_count_ui()
        update_action_button_display_ui()
        self.on_volume_change(self.volume_var.get()) # Para definir o label de porcentagem inicial

    def center_window(self):
        self.master_root.update_idletasks()
        width = self.master_root.winfo_width()
        height = self.master_root.winfo_height()
        x = (self.master_root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master_root.winfo_screenheight() // 2) - (height // 2)
        self.master_root.geometry(f'{width}x{height}+{x}+{y}')

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.colors = {
            'bg_primary': '#0d1117', 'bg_secondary': '#161b22', 'bg_tertiary': '#21262d',
            'accent_blue': '#58a6ff', 'accent_green': '#3fb950', 'accent_orange': '#d29922',
            'accent_red': '#f85149', 'accent_purple': '#a5a5ff', 'text_primary': '#f0f6fc',
            'text_secondary': '#8b949e', 'text_muted': '#6e7681', 'border': '#30363d',
            'hover': '#262c36',
        }
        styles_config = {
            'TFrame': {'background': self.colors['bg_primary'], 'relief': 'flat', 'borderwidth': 0},
            'Card.TFrame': {'background': self.colors['bg_tertiary'], 'relief': 'flat', 'borderwidth': 1, 'lightcolor': self.colors['border'], 'darkcolor': self.colors['border']},
            'Column.TFrame': {'background': self.colors['bg_primary'], 'relief': 'flat'},
            'TLabel': {'font': ('Segoe UI', 10), 'foreground': self.colors['text_primary'], 'background': self.colors['bg_primary']},
            'Title.TLabel': {'font': ('Segoe UI', 24, 'bold'), 'foreground': self.colors['accent_blue'], 'background': self.colors['bg_primary']},
            'Subtitle.TLabel': {'font': ('Segoe UI', 12), 'foreground': self.colors['text_secondary'], 'background': self.colors['bg_primary']},
            'SectionTitle.TLabel': {'font': ('Segoe UI', 14, 'bold'), 'foreground': self.colors['accent_blue'], 'background': self.colors['bg_tertiary'], 'padding': (15, 10, 15, 5)},
            'Status.TLabel': {'font': ('Segoe UI', 11), 'foreground': self.colors['text_primary'], 'background': self.colors['bg_tertiary'], 'padding': (15, 12), 'anchor': 'center', 'relief': 'flat'},
            'Controller.Status.TLabel': {'font': ('Segoe UI', 10), 'foreground': self.colors['text_primary'], 'background': self.colors['bg_tertiary'], 'padding': (15, 8), 'anchor': 'center'},
            'Stats.TLabel': {'font': ('Segoe UI', 10), 'foreground': self.colors['text_secondary'], 'background': self.colors['bg_tertiary']}, # Removido padding global aqui, será por widget
            'Timer.TLabel': {'font': ('Consolas', 42, 'bold'), 'foreground': self.colors['accent_green'], 'background': self.colors['bg_tertiary'], 'anchor': 'center', 'padding': (20, 15)},
            'Modern.TButton': {'font': ('Segoe UI', 10, 'bold'), 'padding': (20, 12), 'background': self.colors['accent_blue'], 'foreground': self.colors['text_primary'], 'relief': 'flat', 'borderwidth': 0, 'focuscolor': 'none'},
            'Success.TButton': {'font': ('Segoe UI', 11, 'bold'), 'padding': (20, 15), 'background': self.colors['accent_green'], 'foreground': self.colors['text_primary'], 'relief': 'flat', 'borderwidth': 0, 'focuscolor': 'none'},
            'Warning.TButton': {'font': ('Segoe UI', 10, 'bold'), 'padding': (20, 12), 'background': self.colors['accent_orange'], 'foreground': self.colors['text_primary'], 'relief': 'flat', 'borderwidth': 0, 'focuscolor': 'none'},
            'TProgressbar': {'thickness': 25, 'background': self.colors['accent_green'], 'troughcolor': self.colors['bg_secondary'], 'borderwidth': 0, 'lightcolor': self.colors['accent_green'], 'darkcolor': self.colors['accent_green']},
            'TCheckbutton': {'font': ('Segoe UI', 10), 'foreground': self.colors['text_primary'], 'background': self.colors['bg_tertiary'], 'indicatorcolor': self.colors['text_primary'], 'padding': (0,0), 'focuscolor': 'none'}, # Removido padding global aqui
            # --- NOVO: Estilo para o TScale (Slider de Volume) ---
            'Volume.Horizontal.TScale': {
                'troughcolor': self.colors['bg_secondary'],
                'background': self.colors['accent_blue'],  # Cor do thumb (botão deslizante)
                'relief': 'flat',
                'sliderrelief': 'flat',
                'borderwidth': 0,
                'sliderthickness': 18, # Altura do canal e thumb
                'focuscolor': 'none' # Remove o anel de foco padrão do Tk
            }
        }
        for style_name, config in styles_config.items():
            self.style.configure(style_name, **config)

        self.style.map('Modern.TButton', background=[('active', self.colors['hover']), ('pressed', self.colors['accent_blue'])], foreground=[('active', self.colors['text_primary']), ('pressed', self.colors['text_primary'])])
        self.style.map('Success.TButton', background=[('active', '#2ea043'), ('pressed', self.colors['accent_green'])], foreground=[('active', self.colors['text_primary']), ('pressed', self.colors['text_primary'])])
        self.style.map('Warning.TButton', background=[('active', '#bb8009'), ('pressed', self.colors['accent_orange'])], foreground=[('active', self.colors['text_primary']), ('pressed', self.colors['text_primary'])])
        self.style.map('TCheckbutton', background=[('active', self.colors['hover'])], indicatorcolor=[('selected', self.colors['accent_green'])])
        # --- NOVO: Estilo de map para o TScale ---
        self.style.map('Volume.Horizontal.TScale',
            background=[('active', self.colors['accent_purple']), ('pressed', self.colors['accent_purple'])], # Thumb quando interagindo
            troughcolor=[('active', self.colors['hover'])]
        )

    def create_section(self, parent_column, title_text, icon=""):
        section_frame = ttk.Frame(parent_column, style='TFrame')
        section_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        card_frame = ttk.Frame(section_frame, style='Card.TFrame')
        card_frame.pack(fill=tk.X)
        title_text_with_icon = f"{icon} {title_text}" if icon else title_text
        title_label = ttk.Label(card_frame, text=title_text_with_icon, style='SectionTitle.TLabel')
        title_label.pack(fill=tk.X)
        separator = tk.Frame(card_frame, height=1, bg=self.colors['border'])
        separator.pack(fill=tk.X, padx=15)
        content_frame = ttk.Frame(card_frame, style='Card.TFrame')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 10))
        return content_frame

    def create_widgets(self):
        self.main_app_container = ttk.Frame(self.master_root, style='TFrame')
        self.main_app_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        header_frame = ttk.Frame(self.main_app_container, style='TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 25))
        title_label = ttk.Label(header_frame, text="🎮 FarmHelper Pro", style='Title.TLabel')
        title_label.pack()
        subtitle_label = ttk.Label(header_frame, text="Advanced Gaming Timer & Automation Assistant", style='Subtitle.TLabel')
        subtitle_label.pack(pady=(5, 0))
        divider = tk.Frame(header_frame, height=2, bg=self.colors['accent_blue'])
        divider.pack(fill=tk.X, pady=(15, 0))

        columns_frame = ttk.Frame(self.main_app_container, style='TFrame')
        columns_frame.pack(fill=tk.BOTH, expand=True)

        left_column = ttk.Frame(columns_frame, style='Column.TFrame')
        left_column.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        left_column.configure(width=420); left_column.pack_propagate(False)

        middle_column = ttk.Frame(columns_frame, style='Column.TFrame')
        middle_column.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        middle_column.configure(width=480); middle_column.pack_propagate(False)

        right_column = ttk.Frame(columns_frame, style='Column.TFrame')
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # === COLUNA ESQUERDA - Controles ===
        controller_section_content = self.create_section(left_column, "Controle & Configuração", "🎮")
        controller_status_frame = ttk.Frame(controller_section_content, style='Card.TFrame')
        controller_status_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        ttk.Label(controller_status_frame, text="Status do Controle:", font=('Segoe UI', 9, 'bold'), foreground=self.colors['text_secondary'], background=self.colors['bg_tertiary']).pack(pady=(10, 5))
        ttk.Label(controller_status_frame, textvariable=ui_controller_status_var, style='Controller.Status.TLabel', wraplength=350).pack(fill=tk.X, pady=(0, 10))
        action_button_frame = ttk.Frame(controller_section_content, style='Card.TFrame')
        action_button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        ttk.Label(action_button_frame, text="Botão de Ação Configurado:", font=('Segoe UI', 9, 'bold'), foreground=self.colors['text_secondary'], background=self.colors['bg_tertiary']).pack(pady=(10, 5))
        button_display_frame = ttk.Frame(action_button_frame, style='Card.TFrame')
        button_display_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Label(button_display_frame, textvariable=ui_action_button_display_var, font=('Consolas', 11, 'bold'), foreground=self.colors['accent_purple'], background=self.colors['bg_tertiary']).pack(pady=5)
        buttons_frame = ttk.Frame(controller_section_content, style='Card.TFrame')
        buttons_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        self.define_button_btn = ttk.Button(buttons_frame, text="🎯 Definir Botão de Ação", command=self.start_button_capture_mode, style='Modern.TButton')
        self.define_button_btn.pack(fill=tk.X, pady=(10, 5))
        ttk.Button(buttons_frame, text="🔄 Verificar Controles", command=self.ui_init_joystick_command, style='Modern.TButton').pack(fill=tk.X, pady=(5, 10))

        delay_section_content = self.create_section(left_column, "Configurações de Tempo", "⏱️")
        delay_config_frame = ttk.Frame(delay_section_content, style='Card.TFrame')
        delay_config_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        ttk.Label(delay_config_frame, text="Delay do Timer (segundos):", font=('Segoe UI', 9, 'bold'), foreground=self.colors['text_secondary'], background=self.colors['bg_tertiary']).pack(pady=(10, 5))
        delay_input_container = ttk.Frame(delay_config_frame, style='Card.TFrame')
        delay_input_container.pack(pady=(0, 10))
        delay_spinbox = tk.Spinbox(delay_input_container, from_=0.1, to=600.0, increment=0.1, textvariable=ui_delay_var, width=12, font=('Consolas', 12, 'bold'), bg=self.colors['bg_secondary'], fg=self.colors['text_primary'], relief='flat', bd=5, justify=tk.CENTER, insertbackground=self.colors['accent_blue'], selectbackground=self.colors['accent_blue'])
        delay_spinbox.pack(pady=5)
        delay_spinbox.bind('<Return>', lambda e: self.apply_delay_from_ui()); delay_spinbox.bind('<FocusOut>', lambda e: self.apply_delay_from_ui())

        # === COLUNA MEIO - Timer Principal ===
        timer_section_content = self.create_section(middle_column, "Status do Timer", "🎯")
        status_frame = ttk.Frame(timer_section_content, style='Card.TFrame')
        status_frame.pack(fill=tk.X, padx=15, pady=(10, 20))
        ttk.Label(status_frame, textvariable=ui_status_var, style='Status.TLabel', wraplength=400).pack(fill=tk.X, pady=10)
        progress_frame = ttk.Frame(timer_section_content, style='Card.TFrame')
        progress_frame.pack(fill=tk.X, padx=15, pady=(0, 20))
        ttk.Label(progress_frame, text="Progresso:", font=('Segoe UI', 9, 'bold'), foreground=self.colors['text_secondary'], background=self.colors['bg_tertiary']).pack(pady=(10, 5))
        progress_bar = ttk.Progressbar(progress_frame, variable=ui_progress_var, maximum=100, style='TProgressbar', length=400)
        progress_bar.pack(pady=(0, 15), padx=20)
        timer_display_frame = ttk.Frame(timer_section_content, style='Card.TFrame')
        timer_display_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        ttk.Label(timer_display_frame, text="Tempo Restante:", font=('Segoe UI', 11, 'bold'), foreground=self.colors['text_secondary'], background=self.colors['bg_tertiary']).pack(pady=(15, 5))
        self.time_label_widget = tk.Label(timer_display_frame, textvariable=ui_time_remaining_var, font=('Consolas', 48, 'bold'), bg=self.colors['bg_tertiary'], fg=self.colors['accent_green'])
        self.time_label_widget.pack(pady=(5, 20))

        # === COLUNA DIREITA - Opções e Estatísticas ===
        options_section_content = self.create_section(right_column, "Opções", "⚙️")

        # Checkbox de som
        sound_check_frame = ttk.Frame(options_section_content, style='Card.TFrame')
        sound_check_frame.pack(fill=tk.X, padx=15, pady=(10,5)) # Menos pady bottom
        sound_check = ttk.Checkbutton(sound_check_frame, text="🔊 Som habilitado", variable=self.sound_enabled_var, style='TCheckbutton')
        sound_check.pack(anchor=tk.W, pady=5) # Menos pady

        # --- NOVO: Controles de Volume ---
        volume_control_frame = ttk.Frame(options_section_content, style='Card.TFrame')
        volume_control_frame.pack(fill=tk.X, padx=15, pady=(5, 15)) # pady top para separar do check

        volume_label = ttk.Label(volume_control_frame, text="🎧 Volume:", style='Stats.TLabel', background=self.colors['bg_tertiary'])
        volume_label.pack(side=tk.LEFT, padx=(0, 10), pady=5)

        self.volume_slider = ttk.Scale(volume_control_frame, from_=0.0, to=1.0,
                                       orient=tk.HORIZONTAL, variable=self.volume_var,
                                       command=self.on_volume_change, style='Volume.Horizontal.TScale')
        self.volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=5)

        self.volume_percentage_label = ttk.Label(volume_control_frame, text="", style='Stats.TLabel', background=self.colors['bg_tertiary'], width=4, anchor=tk.E)
        self.volume_percentage_label.pack(side=tk.LEFT, padx=(10, 0), pady=5)
        # --- FIM NOVO: Controles de Volume ---

        stats_section_content = self.create_section(right_column, "Estatísticas", "📊")
        stats_frame = ttk.Frame(stats_section_content, style='Card.TFrame')
        stats_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        runtime_container = ttk.Frame(stats_frame, style='Card.TFrame')
        runtime_container.pack(fill=tk.X, pady=(10, 8))
        ttk.Label(runtime_container, text="⏰ Tempo de Execução:", style='Stats.TLabel', padding=(0,0,5,0)).pack(anchor=tk.W) # Padding no label
        ttk.Label(runtime_container, textvariable=ui_program_runtime_var, font=('Consolas', 12, 'bold'), foreground=self.colors['accent_blue'], background=self.colors['bg_tertiary']).pack(anchor=tk.W, padx=(20, 0))
        action_container = ttk.Frame(stats_frame, style='Card.TFrame')
        action_container.pack(fill=tk.X, pady=(8, 10))
        ttk.Label(action_container, text="🎯 Ações Executadas:", style='Stats.TLabel', padding=(0,0,5,0)).pack(anchor=tk.W) # Padding no label
        ttk.Label(action_container, textvariable=ui_action_press_count_var, font=('Consolas', 12, 'bold'), foreground=self.colors['accent_green'], background=self.colors['bg_tertiary']).pack(anchor=tk.W, padx=(20, 0))

        app_controls_section_content = self.create_section(right_column, "Controles", "🕹️")
        controls_frame = ttk.Frame(app_controls_section_content, style='Card.TFrame')
        controls_frame.pack(fill=tk.X, padx=15, pady=(10, 15))
        self.start_stop_btn = ttk.Button(controls_frame, text="▶️ Iniciar Monitoramento", command=self.toggle_app_running, style='Success.TButton')
        self.start_stop_btn.pack(fill=tk.X, pady=(10, 8))
        ttk.Button(controls_frame, text="💥 Simular Ação (F5)", command=self.simulate_action_press_ui, style='Modern.TButton').pack(fill=tk.X, pady=4)
        ttk.Button(controls_frame, text="🔄 Reset Timer (ESC)", command=self.reset_visual_timer_ui, style='Warning.TButton').pack(fill=tk.X, pady=(4, 10))

    # --- NOVO: Função para lidar com a mudança de volume ---
    def on_volume_change(self, value_str):
        try:
            volume = float(value_str)
            if self.volume_percentage_label and self.volume_percentage_label.winfo_exists():
                self.volume_percentage_label.config(text=f"{int(volume * 100)}%")

            if pygame and pygame.mixer.get_init() and sound_to_play:
                sound_to_play.set_volume(volume)
                logging.info(f"Volume do som ajustado para: {volume:.2f}")
            elif pygame and pygame.mixer.get_init():
                 # Se sound_to_play ainda não foi carregado, o volume será aplicado quando ele for.
                 # pygame.mixer.music.set_volume(volume) # Se fosse usar música
                 pass
        except ValueError:
            logging.error(f"Valor inválido para volume: {value_str}")
        except Exception as e:
            logging.error(f"Erro ao definir volume: {e}", exc_info=True)


    def setup_ui_bindings(self):
        self.master_root.protocol("WM_DELETE_WINDOW", self.ui_on_app_closing)
        self.master_root.bind("<<AppClosing>>", lambda e: self.ui_on_app_closing() if app_running else None)
        self.master_root.bind('<F5>', lambda event: self.simulate_action_press_ui())
        self.master_root.bind('<Escape>', lambda event: self.reset_visual_timer_ui())

    def start_button_capture_mode(self):
        global capturing_button_mode
        if joystick is None or not (hasattr(joystick, 'get_init') and joystick.get_init()):
            messagebox.showwarning("Controle Necessário", "Conecte um controle antes de definir o botão.", parent=self.master_root)
            return
        capturing_button_mode = True
        update_main_status_ui("🎯 Pressione qualquer botão no controle...")
        logging.info("Modo de captura de botão ATIVADO. Aguardando entrada do usuário.")
        if hasattr(self, 'define_button_btn') and self.define_button_btn.winfo_exists():
            self.define_button_btn.config(state=tk.DISABLED, text="⏳ Aguardando...")
        self.master_root.after(10000, self._check_capture_timeout)

    def _check_capture_timeout(self):
        global capturing_button_mode
        if capturing_button_mode:
            capturing_button_mode = False
            update_main_status_ui("⚠️ Captura cancelada (timeout). Tente novamente.")
            logging.warning("Modo de captura de botão TIMEOUT.")
            if hasattr(self, 'define_button_btn') and self.define_button_btn.winfo_exists():
                self.define_button_btn.config(state=tk.NORMAL, text="🎯 Definir Botão de Ação")

    def apply_delay_from_ui(self):
        global current_delay_seconds
        try:
            new_delay = float(ui_delay_var.get())
            if new_delay > 0:
                current_delay_seconds = new_delay
                update_main_status_ui(f"✅ Delay configurado: {current_delay_seconds:.1f}s")
                logging.info(f"Delay da UI atualizado para: {current_delay_seconds}")
            else:
                messagebox.showerror("Erro de Validação", "O delay deve ser um número positivo.", parent=self.master_root)
                ui_delay_var.set(f"{current_delay_seconds:.1f}")
        except ValueError:
            messagebox.showerror("Erro de Validação", "Por favor, insira um número válido para o delay.", parent=self.master_root)
            ui_delay_var.set(f"{current_delay_seconds:.1f}")
        self.master_root.focus_set()

    def toggle_app_running(self):
        global app_running, pygame_running
        if app_running:
            if messagebox.askyesno("Parar Monitoramento", "Deseja parar o monitoramento e fechar as tarefas de fundo?", parent=self.master_root):
                update_main_status_ui("🛑 Parando monitoramento...")
                app_running = False
                pygame_running = False
                if timer_event: timer_event.set()
                self.start_stop_btn.configure(text="▶️ Reiniciar (Requer Restart)", style='Warning.TButton')
                self.start_stop_btn.configure(state=tk.DISABLED)
                update_controller_status_ui("🔴 Monitoramento parado.")
        else:
            if messagebox.askyesno("Reiniciar Aplicação", "Para reiniciar o monitoramento, a aplicação precisa ser reiniciada. Deseja fazer isso agora?", parent=self.master_root):
                self.ui_on_app_closing(force_quit=True, restart=True)

    def simulate_action_press_ui(self):
        global last_action_press_time, timer_event, app_running, target_button_index
        if not app_running:
            messagebox.showwarning("Aviso", "O monitoramento não está ativo.", parent=self.master_root)
            return
        if target_button_index is None:
            messagebox.showwarning("Aviso", "Nenhum botão de ação foi definido. Clique em 'Definir Botão de Ação'.", parent=self.master_root)
            return
        logging.info("Simulando pressão do Botão de Ação pela UI.")
        last_action_press_time = time.time()
        increment_action_press_count_and_update_ui()
        timer_event.set()
        update_main_status_ui("💥 Ação simulada com sucesso!")

    def reset_visual_timer_ui(self):
        if ui_root and ui_root.winfo_exists():
            update_timer_display_ui(0, 1)
            if ui_progress_var: ui_progress_var.set(0)
            update_main_status_ui("🔄 Timer resetado. Aguardando próxima ação...")

    def ui_init_joystick_command(self):
        logging.info("Botão 'Verificar Controles' pressionado. A detecção é automática.")
        update_controller_status_ui("🔍 Verificando controles...")
        if joystick is None or not (hasattr(joystick, 'get_init') and joystick.get_init()):
             update_controller_status_ui("⚠️ Nenhum controle detectado. Conecte um controle.")
        else:
             update_controller_status_ui(f"🟢 {joystick.get_name()[:25]} (Verificado)")

    def ui_on_app_closing(self, force_quit=False, restart=False):
        global app_running, pygame_running, pygame_thread_global, timer_sound_thread_global
        confirmed_to_close = force_quit
        if not force_quit:
            confirmed_to_close = messagebox.askokcancel("Sair", "Você tem certeza que quer sair do FarmHelper Pro?", parent=self.master_root)

        if confirmed_to_close:
            logging.info("Usuário confirmou o fechamento pela GUI.")
            update_main_status_ui("🔄 Finalizando aplicação...")
            app_running = False
            pygame_running = False
            if timer_event: timer_event.set()

            if pygame_thread_global and pygame_thread_global.is_alive():
                logging.info("Aguardando thread Pygame...")
                pygame_thread_global.join(timeout=1.0)
            if timer_sound_thread_global and timer_sound_thread_global.is_alive():
                logging.info("Aguardando thread Timer/Som...")
                timer_sound_thread_global.join(timeout=1.0)

            if self.master_root and self.master_root.winfo_exists():
                self.master_root.destroy()
            logging.info("Aplicação GUI finalizada.")

            if restart:
                logging.info("Reiniciando a aplicação...")
                python = sys.executable
                os.execl(python, python, *sys.argv)

pygame_thread_global = None
timer_sound_thread_global = None

if __name__ == "__main__":
    print("🚀 Iniciando FarmHelper Pro...")
    logging.info("Bloco __main__ iniciado.")

    main_tk_root = tk.Tk()
    print("✅ Interface Tkinter criada.")
    logging.info("Root Tkinter criado.")

    app_ui = FarmHelperApp(main_tk_root)
    print("✅ FarmHelper Pro carregado.")
    logging.info("Instância de FarmHelperApp criada.")

    try:
        print("🔧 Iniciando threads de background...")
        pygame_thread_global = threading.Thread(target=pygame_loop, name="PygameThread", daemon=True)
        pygame_thread_global.start()
        print("✅ Thread Pygame iniciada.")
        logging.info("PygameThread iniciada.")

        timer_sound_thread_global = threading.Thread(target=timer_and_sound_task, name="TimerSoundThread", daemon=True)
        timer_sound_thread_global.start()
        print("✅ Thread Timer iniciada.")
        logging.info("TimerSoundThread iniciada.")

        print("🎮 FarmHelper Pro está pronto! Iniciando interface...")
        main_tk_root.mainloop()
        print("👋 Interface finalizada.")
        logging.info("mainloop do Tkinter finalizado.")

    except Exception as e_global:
        print(f"❌ Erro crítico: {e_global}")
        logging.critical(f"Erro global não capturado na inicialização: {e_global}", exc_info=True)
        if main_tk_root and main_tk_root.winfo_exists():
            messagebox.showerror("Erro Crítico", f"Ocorreu um erro fatal:\n{e_global}\nVerifique o arquivo de log.")
    finally:
        print("🔄 Finalizando aplicação...")
        logging.info("Aplicação finalizada a partir do bloco __main__.")
        app_running = False
        pygame_running = False
        if timer_event: timer_event.set()

        if pygame_thread_global and pygame_thread_global.is_alive():
            pygame_thread_global.join(timeout=0.5)
        if timer_sound_thread_global and timer_sound_thread_global.is_alive():
            timer_sound_thread_global.join(timeout=0.5)

        logging.info("------------------ FIM DA EXECUÇÃO ------------------")