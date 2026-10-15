from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from isso_facilita.ai_audit import read_ai_decisions

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
BOT_URL = "http://127.0.0.1:8000/health"
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
WHATSAPP_URL = "http://127.0.0.1:3001/health"
BOT_MODULE = "isso_facilita.app:app"
ENV_KEY = "AI_CURATION_ENABLED"
_ENV_LINE = re.compile(
    rf"^(?P<prefix>\s*(?:export\s+)?{ENV_KEY}\s*=\s*)"
    r"(?P<value>[^#\r\n]*?)"
    r"(?P<suffix>\s*(?:#.*)?)$",
    re.IGNORECASE | re.MULTILINE,
)


def _read_env_text(env_path: Path) -> tuple[str, bool]:
    raw = env_path.read_bytes()
    has_utf8_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), has_utf8_bom


def read_ai_enabled(env_path: Path = ENV_PATH) -> bool | None:
    """Read only the AI switch without loading or exposing other environment values."""
    if not env_path.exists():
        return None
    content, _ = _read_env_text(env_path)
    match = _ENV_LINE.search(content)
    if not match:
        return None
    value = match.group("value").strip().strip('"\'').lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return None


def write_ai_enabled(enabled: bool, env_path: Path = ENV_PATH) -> None:
    """Atomically change only AI_CURATION_ENABLED, preserving the rest of .env."""
    if not env_path.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {env_path}")

    original, has_utf8_bom = _read_env_text(env_path)
    value = "true" if enabled else "false"
    if _ENV_LINE.search(original):
        updated = _ENV_LINE.sub(
            lambda match: f"{match.group('prefix')}{value}{match.group('suffix')}",
            original,
        )
    else:
        separator = "" if not original or original.endswith(("\n", "\r")) else os.linesep
        updated = f"{original}{separator}{ENV_KEY}={value}{os.linesep}"

    temporary = env_path.with_name(f"{env_path.name}.tmp")
    try:
        encoded = updated.encode("utf-8")
        if has_utf8_bom:
            encoded = b"\xef\xbb\xbf" + encoded
        temporary.write_bytes(encoded)
        os.replace(temporary, env_path)
    finally:
        temporary.unlink(missing_ok=True)


def get_bot_health(timeout: float = 1.5) -> dict[str, object] | None:
    try:
        with urlopen(BOT_URL, timeout=timeout) as response:  # noqa: S310 - fixed localhost URL
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_url_available(url: str, timeout: float = 0.5) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed localhost URLs
            return 200 <= response.status < 500
    except (OSError, URLError, ValueError):
        return False


def get_service_statuses(timeout: float = 0.5) -> dict[str, bool]:
    return {
        "bot": get_bot_health(timeout) is not None,
        "whatsapp": is_url_available(WHATSAPP_URL, timeout),
        "ollama": is_url_available(OLLAMA_URL, timeout),
    }


def _powershell_process_ids(project_root: Path = PROJECT_ROOT) -> list[int]:
    script = (
        "$root = $env:ISSO_FACILITA_PROJECT_ROOT; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -and "
        "$_.CommandLine.Contains($root) -and "
        f"$_.CommandLine.Contains('{BOT_MODULE}') }} | "
        "Select-Object -ExpandProperty ProcessId"
    )
    environment = os.environ.copy()
    environment["ISSO_FACILITA_PROJECT_ROOT"] = str(project_root.resolve())
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env=environment,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("Não foi possível localizar o processo atual do bot.")
    return [int(line) for line in result.stdout.splitlines() if line.strip().isdigit()]


def stop_bot(project_root: Path = PROJECT_ROOT) -> None:
    for process_id in _powershell_process_ids(project_root):
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=15,
        )


def _listener_processes(port: int) -> list[tuple[int, str]]:
    script = (
        f"Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty OwningProcess -Unique | "
        "ForEach-Object { $process = Get-CimInstance Win32_Process "
        "-Filter ('ProcessId = ' + $_); "
        "if ($process) { Write-Output ($process.ProcessId.ToString() + '|' + $process.Name) } }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Não foi possível verificar o serviço local na porta {port}.")
    processes: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        process_id, separator, name = line.strip().partition("|")
        if separator and process_id.isdigit():
            processes.append((int(process_id), name.strip().lower()))
    return processes


def _stop_listener_service(port: int, expected_processes: set[str]) -> None:
    for process_id, process_name in _listener_processes(port):
        if process_name not in expected_processes:
            raise RuntimeError(
                f"A porta {port} pertence a um processo inesperado ({process_name}); "
                "ele não foi encerrado."
            )
        subprocess.run(
            ["taskkill.exe", "/PID", str(process_id), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=20,
        )


def stop_everything(timeout: float = 15) -> dict[str, bool]:
    errors: list[str] = []
    for action in (
        stop_bot,
        lambda: _stop_listener_service(3001, {"node.exe"}),
        lambda: _stop_listener_service(11434, {"ollama.exe"}),
    ):
        try:
            action()
        except Exception as error:
            errors.append(str(error))

    deadline = time.monotonic() + timeout
    statuses = get_service_statuses()
    while any(statuses.values()) and time.monotonic() < deadline:
        time.sleep(0.35)
        statuses = get_service_statuses()
    if errors:
        raise RuntimeError(" ".join(errors))
    if any(statuses.values()):
        active = ", ".join(name for name, running in statuses.items() if running)
        raise TimeoutError(f"Estes serviços não encerraram a tempo: {active}.")
    return statuses


def _detached_flags() -> int:
    return (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def _start_detached(
    command: list[str],
    working_directory: Path,
    log_path: Path,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(  # noqa: S603 - validated local executables and fixed arguments
            command,
            cwd=working_directory,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=_detached_flags(),
        )


def _wait_for_url(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_url_available(url):
            return
        time.sleep(0.4)
    raise TimeoutError(f"O serviço local {url} não iniciou a tempo.")


def start_ollama(project_root: Path = PROJECT_ROOT) -> None:
    if is_url_available(OLLAMA_URL):
        return
    default_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    executable = shutil.which("ollama") or (str(default_path) if default_path.exists() else "")
    if not executable:
        raise FileNotFoundError("O executável do Ollama não foi encontrado.")
    _start_detached(
        [executable, "serve"],
        project_root,
        project_root / "data" / "ollama-desktop.log",
    )
    _wait_for_url(OLLAMA_URL, 20)


def start_whatsapp(project_root: Path = PROJECT_ROOT) -> None:
    if is_url_available(WHATSAPP_URL):
        return
    default_path = Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "nodejs" / "node.exe"
    executable = shutil.which("node") or (str(default_path) if default_path.exists() else "")
    server = project_root / "whatsapp-web-bridge" / "src" / "server.js"
    if not executable:
        raise FileNotFoundError("O executável do Node.js não foi encontrado.")
    if not server.exists():
        raise FileNotFoundError(f"Ponte do WhatsApp não encontrada: {server}")
    _start_detached(
        [executable, str(server)],
        server.parents[1],
        project_root / "data" / "whatsapp-desktop.log",
    )
    _wait_for_url(WHATSAPP_URL, 30)


def start_everything(project_root: Path = PROJECT_ROOT) -> dict[str, bool]:
    start_ollama(project_root)
    start_whatsapp(project_root)
    if get_bot_health() is None:
        start_bot(project_root)
        _wait_for_url(BOT_URL, 20)
    return get_service_statuses()


def start_bot(project_root: Path = PROJECT_ROOT) -> None:
    pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        raise FileNotFoundError(f"Python do projeto não encontrado: {pythonw}")

    data_directory = project_root / "data"
    data_directory.mkdir(exist_ok=True)
    log_path = data_directory / "bot-desktop.log"
    creation_flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(  # noqa: S603 - fixed local executable and arguments
            [
                str(pythonw),
                "-m",
                "uvicorn",
                BOT_MODULE,
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creation_flags,
        )


def restart_bot(project_root: Path = PROJECT_ROOT, timeout: float = 20) -> dict[str, object]:
    stop_bot(project_root)
    deadline = time.monotonic() + 8
    while get_bot_health() is not None and time.monotonic() < deadline:
        time.sleep(0.25)
    if get_bot_health() is not None:
        raise TimeoutError("O processo anterior do bot não encerrou.")

    start_bot(project_root)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = get_bot_health()
        if health is not None:
            return health
        time.sleep(0.4)
    raise TimeoutError("O bot não respondeu na porta 8000 após a reinicialização.")


class AiControlWindow:
    BACKGROUND = "#0a0f18"
    SURFACE = "#121a27"
    SURFACE_ALT = "#172233"
    BORDER = "#243247"
    TEXT = "#f5f7fb"
    MUTED = "#93a1b5"
    ACCENT = "#7c6cff"
    ACCENT_HOVER = "#9185ff"
    GREEN = "#38d996"
    GREEN_SOFT = "#173b31"
    RED = "#ff7080"
    RED_SOFT = "#40212b"
    BLUE = "#62b7ff"
    BLUE_HOVER = "#7bc3ff"
    AMBER = "#f2c66d"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.busy = False
        self.log_records: dict[str, dict[str, object]] = {}
        root.title("Isso Facilita — Controle da IA")
        root.geometry("1180x820")
        root.minsize(980, 720)
        root.configure(bg=self.BACKGROUND)
        root.option_add("*Font", "{Segoe UI} 9")

        container = tk.Frame(root, bg=self.BACKGROUND)
        container.pack(fill="both", expand=True, padx=26, pady=22)

        header = tk.Frame(container, bg=self.BACKGROUND)
        header.pack(fill="x", pady=(0, 18))
        brand_mark = tk.Label(
            header,
            text="IF",
            bg=self.ACCENT,
            fg="#ffffff",
            font=("Segoe UI", 15, "bold"),
            padx=12,
            pady=8,
        )
        brand_mark.pack(side="left", padx=(0, 12))
        brand_text = tk.Frame(header, bg=self.BACKGROUND)
        brand_text.pack(side="left")
        tk.Label(
            brand_text,
            text="Isso Facilita",
            bg=self.BACKGROUND,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 19),
        ).pack(anchor="w")
        tk.Label(
            brand_text,
            text="Central de controle da curadoria",
            bg=self.BACKGROUND,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(1, 0))

        status_group = tk.Frame(header, bg=self.BACKGROUND)
        status_group.pack(side="right")
        self.bot_status = tk.Label(
            status_group,
            text="●  VERIFICANDO BOT",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
            padx=13,
            pady=8,
        )
        self.bot_status.pack(side="right", padx=(8, 0))
        self.ai_status = tk.Label(
            status_group,
            text="●  VERIFICANDO IA",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
            padx=13,
            pady=8,
        )
        self.ai_status.pack(side="right")

        control_card = tk.Frame(
            container,
            bg=self.SURFACE,
            padx=20,
            pady=17,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        control_card.pack(fill="x", pady=(0, 16))
        ai_row = tk.Frame(control_card, bg=self.SURFACE)
        ai_row.pack(fill="x")
        control_copy = tk.Frame(ai_row, bg=self.SURFACE)
        control_copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            control_copy,
            text="Curadoria por inteligência artificial",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        self.detail = tk.Label(
            control_copy,
            text="Ative ou desative a IA. A troca reinicia somente o bot local.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.detail.pack(anchor="w", pady=(4, 0))

        buttons = tk.Frame(ai_row, bg=self.SURFACE)
        buttons.pack(side="right", padx=(24, 0))
        self.disable_button = self._make_button(
            buttons,
            text="DESATIVAR IA",
            command=lambda: self.set_enabled(False),
            background=self.RED_SOFT,
            hover="#53303a",
            foreground="#ffabb4",
        )
        self.disable_button.pack(side="left", padx=(0, 8))
        self.enable_button = self._make_button(
            buttons,
            text="ATIVAR IA",
            command=lambda: self.set_enabled(True),
            background=self.ACCENT,
            hover=self.ACCENT_HOVER,
            foreground="#ffffff",
        )
        self.enable_button.pack(side="left")

        tk.Frame(control_card, bg=self.BORDER, height=1).pack(fill="x", pady=15)
        services_row = tk.Frame(control_card, bg=self.SURFACE)
        services_row.pack(fill="x")
        services_copy = tk.Frame(services_row, bg=self.SURFACE)
        services_copy.pack(side="left", fill="x", expand=True)
        services_title = tk.Frame(services_copy, bg=self.SURFACE)
        services_title.pack(anchor="w")
        tk.Label(
            services_title,
            text="Serviços e memória",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 12),
        ).pack(side="left")
        self.services_status = tk.Label(
            services_title,
            text="●  VERIFICANDO",
            bg=self.SURFACE_ALT,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 8),
            padx=9,
            pady=4,
        )
        self.services_status.pack(side="left", padx=(10, 0))
        tk.Label(
            services_copy,
            text="Bot, WhatsApp Web e Ollama. Parar tudo descarrega o modelo da memória.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        service_buttons = tk.Frame(services_row, bg=self.SURFACE)
        service_buttons.pack(side="right", padx=(24, 0))
        self.start_all_button = self._make_button(
            service_buttons,
            text="INICIAR TUDO",
            command=self.start_all,
            background="#1d493b",
            hover="#265d4c",
            foreground="#8aefc1",
        )
        self.start_all_button.pack(side="left", padx=(0, 8))
        self.stop_all_button = self._make_button(
            service_buttons,
            text="PARAR TUDO",
            command=self.stop_all,
            background=self.RED,
            hover="#ff8895",
            foreground="#25080d",
        )
        self.stop_all_button.pack(side="left")

        log_card = tk.Frame(
            container,
            bg=self.SURFACE,
            padx=18,
            pady=16,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        log_card.pack(fill="both", expand=True)
        log_header = tk.Frame(log_card, bg=self.SURFACE)
        log_header.pack(fill="x", pady=(0, 12))
        log_title = tk.Frame(log_header, bg=self.SURFACE)
        log_title.pack(side="left")
        tk.Label(
            log_title,
            text="Avaliações da IA",
            bg=self.SURFACE,
            fg=self.TEXT,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        tk.Label(
            log_title,
            text="Acompanhe as decisões mais recentes em tempo real",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))
        self.log_summary = tk.Label(
            log_header,
            text="Carregando histórico...",
            bg=self.SURFACE_ALT,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=7,
        )
        self.log_summary.pack(side="right", anchor="n")

        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "AiLog.Treeview",
            background=self.SURFACE_ALT,
            fieldbackground=self.SURFACE_ALT,
            foreground=self.TEXT,
            rowheight=31,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "AiLog.Treeview.Heading",
            background="#202d40",
            foreground="#bec9d8",
            borderwidth=0,
            relief="flat",
            padding=(8, 9),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "AiLog.Treeview",
            background=[("selected", "#2a3e5d")],
            foreground=[("selected", "#ffffff")],
        )
        style.map("AiLog.Treeview.Heading", background=[("active", "#26364d")])
        style.configure(
            "Vertical.TScrollbar",
            background="#33445c",
            troughcolor=self.SURFACE_ALT,
            bordercolor=self.SURFACE_ALT,
            arrowcolor=self.MUTED,
            relief="flat",
        )

        table_frame = tk.Frame(log_card, bg=self.SURFACE_ALT)
        table_frame.pack(fill="both", expand=True)
        columns = ("time", "status", "score", "marketplace", "title", "link")
        self.log_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            style="AiLog.Treeview",
            selectmode="browse",
        )
        headings = {
            "time": "Data e hora",
            "status": "Resultado",
            "score": "Nota",
            "marketplace": "Origem",
            "title": "Produto",
            "link": "Link afiliado",
        }
        widths = {
            "time": 145,
            "status": 85,
            "score": 55,
            "marketplace": 85,
            "title": 315,
            "link": 280,
        }
        for column in columns:
            self.log_table.heading(column, text=headings[column])
            self.log_table.column(column, width=widths[column], minwidth=50, anchor="w")
        self.log_table.tag_configure("accepted", foreground="#72e3ad")
        self.log_table.tag_configure("rejected", foreground="#ff9aa5")
        self.log_table.tag_configure("error", foreground=self.AMBER)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.log_table.yview)
        self.log_table.configure(yscrollcommand=scrollbar.set)
        self.log_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.log_table.bind("<<TreeviewSelect>>", self.show_selected_log)
        self.log_table.bind("<Double-1>", self.open_selected_link)

        detail_header = tk.Label(
            log_card,
            text="DETALHES DA DECISÃO",
            bg=self.SURFACE,
            fg="#74849a",
            font=("Segoe UI Semibold", 8),
        )
        detail_header.pack(anchor="w", pady=(13, 6))
        log_actions = tk.Frame(log_card, bg=self.SURFACE)
        log_actions.pack(fill="x")
        self.log_detail = tk.Text(
            log_actions,
            height=4,
            wrap="word",
            bg=self.SURFACE_ALT,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            padx=13,
            pady=10,
            font=("Segoe UI", 9),
            selectbackground="#35557e",
        )
        self.log_detail.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self.log_detail.insert("1.0", "Selecione uma avaliação para ver o motivo e o link.")
        self.log_detail.configure(state="disabled")
        action_buttons = tk.Frame(log_actions, bg=self.SURFACE)
        action_buttons.pack(side="right", fill="y")
        self._make_button(
            action_buttons,
            text="ATUALIZAR",
            command=self.load_log,
            background="#26364c",
            hover="#31445e",
            foreground="#d6deea",
        ).pack(fill="x", pady=(0, 6))
        self._make_button(
            action_buttons,
            text="ABRIR LINK",
            command=self.open_selected_link,
            background=self.BLUE,
            hover=self.BLUE_HOVER,
            foreground="#071521",
        ).pack(fill="x")

        tk.Label(
            container,
            text="Histórico salvo apenas neste computador  •  Atualização automática a cada 3 s",
            bg=self.BACKGROUND,
            fg="#637187",
            font=("Segoe UI", 8),
        ).pack(anchor="e", pady=(9, 0))

        self.refresh_status()
        self.refresh_log()

    def _make_button(
        self,
        parent: tk.Misc,
        *,
        text: str,
        command: object,
        background: str,
        hover: str,
        foreground: str,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=hover,
            activeforeground=foreground,
            disabledforeground="#68778c",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI Semibold", 9),
            padx=18,
            pady=10,
            cursor="hand2",
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=background))
        return button

    def refresh_status(self) -> None:
        if self.busy:
            return
        health = get_bot_health(0.5)
        statuses = {
            "bot": health is not None,
            "whatsapp": is_url_available(WHATSAPP_URL),
            "ollama": is_url_available(OLLAMA_URL),
        }
        configured = read_ai_enabled()
        active = health.get("ai_curation") if health else configured
        if not statuses["bot"]:
            self.ai_status.configure(
                text="●  IA PARADA",
                fg=self.MUTED,
                bg=self.SURFACE,
            )
        elif active is True:
            self.ai_status.configure(
                text="●  IA ATIVADA",
                fg=self.GREEN,
                bg=self.GREEN_SOFT,
            )
        elif active is False:
            self.ai_status.configure(
                text="●  IA DESATIVADA",
                fg=self.RED,
                bg=self.RED_SOFT,
            )
        else:
            self.ai_status.configure(
                text="●  ESTADO DESCONHECIDO",
                fg=self.MUTED,
                bg=self.SURFACE,
            )
        self.bot_status.configure(
            text="●  BOT ONLINE" if statuses["bot"] else "●  BOT OFFLINE",
            fg=self.GREEN if statuses["bot"] else self.RED,
            bg=self.GREEN_SOFT if statuses["bot"] else self.RED_SOFT,
        )
        online_count = sum(statuses.values())
        if online_count == len(statuses):
            self.services_status.configure(
                text="●  TUDO ONLINE",
                fg=self.GREEN,
                bg=self.GREEN_SOFT,
            )
        elif online_count == 0:
            self.services_status.configure(
                text="●  TUDO PARADO",
                fg=self.MUTED,
                bg=self.SURFACE_ALT,
            )
        else:
            self.services_status.configure(
                text=f"●  {online_count}/3 ONLINE",
                fg=self.AMBER,
                bg="#3b3422",
            )
        self.root.after(3000, self.refresh_status)

    def refresh_log(self) -> None:
        self.load_log()
        self.root.after(3000, self.refresh_log)

    def load_log(self) -> None:
        selected_key = None
        selection = self.log_table.selection()
        if selection:
            selected = self.log_records.get(selection[0], {})
            selected_key = (selected.get("timestamp"), selected.get("product_id"))

        entries = read_ai_decisions()
        self.log_table.delete(*self.log_table.get_children())
        self.log_records.clear()
        counts = {"accepted": 0, "rejected": 0, "error": 0}
        selected_item = None
        labels = {"accepted": "ACEITO", "rejected": "RECUSADO", "error": "ERRO"}
        for index, entry in enumerate(entries):
            status = str(entry.get("status", "error"))
            counts[status] = counts.get(status, 0) + 1
            item_id = f"decision-{index}"
            timestamp = str(entry.get("timestamp", "")).replace("T", " ")
            score = entry.get("score")
            values = (
                timestamp[:19],
                labels.get(status, status.upper()),
                "—" if score is None else str(score),
                str(entry.get("marketplace", "")).title(),
                str(entry.get("title", "")),
                str(entry.get("affiliate_url", "")),
            )
            self.log_table.insert("", "end", iid=item_id, values=values, tags=(status,))
            self.log_records[item_id] = entry
            if selected_key == (entry.get("timestamp"), entry.get("product_id")):
                selected_item = item_id

        self.log_summary.configure(
            text=(
                f"{counts['accepted']} aceitos · {counts['rejected']} recusados"
                f" · {counts['error']} erros"
            )
            if entries
            else "Nenhuma avaliação registrada ainda"
        )
        if selected_item:
            self.log_table.selection_set(selected_item)
            self.log_table.see(selected_item)

    def show_selected_log(self, _event: object | None = None) -> None:
        selection = self.log_table.selection()
        if not selection:
            return
        entry = self.log_records.get(selection[0])
        if not entry:
            return
        status_labels = {"accepted": "ACEITO", "rejected": "RECUSADO", "error": "ERRO"}
        status = status_labels.get(str(entry.get("status")), "DESCONHECIDO")
        score = entry.get("score")
        threshold = entry.get("threshold")
        score_text = "sem nota" if score is None else f"nota {score} / corte {threshold}"
        detail = (
            f"{status} · {score_text}\n"
            f"Motivo: {entry.get('reason') or 'não informado'}\n"
            f"Link: {entry.get('affiliate_url') or 'não disponível'}"
        )
        self.log_detail.configure(state="normal")
        self.log_detail.delete("1.0", "end")
        self.log_detail.insert("1.0", detail)
        self.log_detail.configure(state="disabled")

    def open_selected_link(self, _event: object | None = None) -> None:
        selection = self.log_table.selection()
        if not selection:
            messagebox.showinfo(
                "Isso Facilita",
                "Selecione uma avaliação para abrir o link.",
                parent=self.root,
            )
            return
        link = str(self.log_records.get(selection[0], {}).get("affiliate_url", ""))
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            messagebox.showerror(
                "Isso Facilita",
                "Este item não possui um link válido.",
                parent=self.root,
            )
            return
        webbrowser.open(link)

    def set_enabled(self, enabled: bool) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_controls_state("disabled")
        self.ai_status.configure(
            text="●  APLICANDO...",
            fg=self.MUTED,
            bg=self.SURFACE,
        )
        self.bot_status.configure(
            text="●  REINICIANDO BOT",
            fg=self.MUTED,
            bg=self.SURFACE,
        )
        threading.Thread(target=self._apply, args=(enabled,), daemon=True).start()

    def start_all(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_controls_state("disabled")
        self.services_status.configure(
            text="●  INICIANDO...",
            fg=self.AMBER,
            bg="#3b3422",
        )
        self.detail.configure(text="Iniciando Ollama, WhatsApp Web e bot local...")
        threading.Thread(target=self._apply_services, args=(True,), daemon=True).start()

    def stop_all(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_controls_state("disabled")
        self.services_status.configure(
            text="●  ENCERRANDO...",
            fg=self.AMBER,
            bg="#3b3422",
        )
        self.detail.configure(text="Encerrando os serviços e liberando a memória do modelo...")
        threading.Thread(target=self._apply_services, args=(False,), daemon=True).start()

    def _apply_services(self, should_start: bool) -> None:
        try:
            statuses = start_everything() if should_start else stop_everything()
        except Exception as error:
            message = str(error)
            self.root.after(0, lambda: self._finish_error(message))
            return
        self.root.after(0, lambda: self._finish_services(should_start, statuses))

    def _set_controls_state(self, state: str) -> None:
        for button in (
            self.enable_button,
            self.disable_button,
            self.start_all_button,
            self.stop_all_button,
        ):
            button.configure(state=state)

    def _apply(self, enabled: bool) -> None:
        try:
            write_ai_enabled(enabled)
            health = restart_bot()
            actual = health.get("ai_curation") is True
            if actual != enabled:
                raise RuntimeError("O bot voltou com um estado de IA diferente do solicitado.")
        except Exception as error:
            message = str(error)
            self.root.after(0, lambda: self._finish_error(message))
            return
        self.root.after(0, lambda: self._finish_success(enabled))

    def _finish_success(self, enabled: bool) -> None:
        self.busy = False
        self._set_controls_state("normal")
        self.detail.configure(
            text="IA ativada e bot reiniciado."
            if enabled
            else "IA desativada e bot reiniciado."
        )
        self.refresh_status()

    def _finish_services(self, started: bool, statuses: dict[str, bool]) -> None:
        self.busy = False
        self._set_controls_state("normal")
        if started and all(statuses.values()):
            self.detail.configure(
                text="Todos os serviços foram iniciados. A sessão do WhatsApp foi preservada."
            )
        elif not started and not any(statuses.values()):
            self.detail.configure(
                text="Tudo parado. Bot, WhatsApp e modelo do Ollama foram retirados da memória."
            )
        self.refresh_status()

    def _finish_error(self, message: str) -> None:
        self.busy = False
        self._set_controls_state("normal")
        self.detail.configure(text="Não foi possível aplicar a alteração.")
        self.refresh_status()
        messagebox.showerror("Isso Facilita", message, parent=self.root)


def main() -> None:
    root = tk.Tk()
    AiControlWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
