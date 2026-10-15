from __future__ import annotations

import json
import os
import re
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
    BACKGROUND = "#101820"
    PANEL = "#17232d"
    TEXT = "#f4f7f9"
    MUTED = "#a8b5bf"
    GREEN = "#35c47c"
    RED = "#ef6461"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.busy = False
        self.log_records: dict[str, dict[str, object]] = {}
        root.title("Isso Facilita — Controle da IA")
        root.geometry("1080x720")
        root.minsize(860, 600)
        root.configure(bg=self.BACKGROUND)

        panel = tk.Frame(root, bg=self.PANEL, padx=24, pady=20)
        panel.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            panel,
            text="ISSO FACILITA",
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Segoe UI", 18, "bold"),
        ).pack()
        tk.Label(
            panel,
            text="Controle local da curadoria por IA",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(pady=(2, 20))

        self.ai_status = tk.Label(
            panel,
            text="Verificando IA...",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 14, "bold"),
        )
        self.ai_status.pack()
        self.bot_status = tk.Label(
            panel,
            text="Verificando bot...",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.bot_status.pack(pady=(4, 18))

        buttons = tk.Frame(panel, bg=self.PANEL)
        buttons.pack(fill="x")
        self.enable_button = tk.Button(
            buttons,
            text="ATIVAR IA",
            command=lambda: self.set_enabled(True),
            bg=self.GREEN,
            fg="#07150e",
            activebackground="#55d493",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=11,
            cursor="hand2",
        )
        self.enable_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.disable_button = tk.Button(
            buttons,
            text="DESATIVAR IA",
            command=lambda: self.set_enabled(False),
            bg=self.RED,
            fg="#210706",
            activebackground="#f27f7d",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=11,
            cursor="hand2",
        )
        self.disable_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.detail = tk.Label(
            panel,
            text="A troca reinicia somente o bot. Ollama e WhatsApp continuam ligados.",
            wraplength=360,
            justify="center",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        )
        self.detail.pack(pady=(14, 12))

        tk.Frame(panel, bg="#2a3a46", height=1).pack(fill="x", pady=(0, 12))
        log_header = tk.Frame(panel, bg=self.PANEL)
        log_header.pack(fill="x", pady=(0, 8))
        tk.Label(
            log_header,
            text="AVALIAÇÕES DA IA",
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        self.log_summary = tk.Label(
            log_header,
            text="Carregando histórico...",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        )
        self.log_summary.pack(side="right")

        style = ttk.Style(root)
        style.configure(
            "AiLog.Treeview",
            background="#101820",
            fieldbackground="#101820",
            foreground=self.TEXT,
            rowheight=27,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "AiLog.Treeview.Heading",
            background="#273845",
            foreground="#101820",
            font=("Segoe UI", 9, "bold"),
        )
        style.map("AiLog.Treeview", background=[("selected", "#35556b")])

        table_frame = tk.Frame(panel, bg=self.PANEL)
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
        self.log_table.tag_configure("accepted", foreground="#62d89b")
        self.log_table.tag_configure("rejected", foreground="#ff8a87")
        self.log_table.tag_configure("error", foreground="#f2c66d")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.log_table.yview)
        self.log_table.configure(yscrollcommand=scrollbar.set)
        self.log_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.log_table.bind("<<TreeviewSelect>>", self.show_selected_log)
        self.log_table.bind("<Double-1>", self.open_selected_link)

        log_actions = tk.Frame(panel, bg=self.PANEL)
        log_actions.pack(fill="x", pady=(10, 0))
        self.log_detail = tk.Text(
            log_actions,
            height=4,
            wrap="word",
            bg="#101820",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            padx=10,
            pady=8,
            font=("Segoe UI", 9),
        )
        self.log_detail.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.log_detail.insert("1.0", "Selecione uma avaliação para ver o motivo e o link.")
        self.log_detail.configure(state="disabled")
        action_buttons = tk.Frame(log_actions, bg=self.PANEL)
        action_buttons.pack(side="right", fill="y")
        tk.Button(
            action_buttons,
            text="ATUALIZAR",
            command=self.load_log,
            bg="#526979",
            fg=self.TEXT,
            activebackground="#678295",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(fill="x", pady=(0, 6))
        tk.Button(
            action_buttons,
            text="ABRIR LINK",
            command=self.open_selected_link,
            bg="#2f81b7",
            fg=self.TEXT,
            activebackground="#4297cf",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        ).pack(fill="x")

        self.refresh_status()
        self.refresh_log()

    def refresh_status(self) -> None:
        if self.busy:
            return
        health = get_bot_health()
        configured = read_ai_enabled()
        active = health.get("ai_curation") if health else configured
        if active is True:
            self.ai_status.configure(text="IA ATIVADA", fg=self.GREEN)
        elif active is False:
            self.ai_status.configure(text="IA DESATIVADA", fg=self.RED)
        else:
            self.ai_status.configure(text="ESTADO DESCONHECIDO", fg=self.MUTED)
        self.bot_status.configure(
            text="BOT ONLINE" if health else "BOT OFFLINE",
            fg=self.GREEN if health else self.RED,
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
        self.enable_button.configure(state="disabled")
        self.disable_button.configure(state="disabled")
        self.ai_status.configure(text="APLICANDO...", fg=self.MUTED)
        self.bot_status.configure(text="Reiniciando o bot", fg=self.MUTED)
        threading.Thread(target=self._apply, args=(enabled,), daemon=True).start()

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
        self.enable_button.configure(state="normal")
        self.disable_button.configure(state="normal")
        self.detail.configure(
            text="IA ativada e bot reiniciado."
            if enabled
            else "IA desativada e bot reiniciado."
        )
        self.refresh_status()

    def _finish_error(self, message: str) -> None:
        self.busy = False
        self.enable_button.configure(state="normal")
        self.disable_button.configure(state="normal")
        self.detail.configure(text="Não foi possível aplicar a alteração.")
        self.refresh_status()
        messagebox.showerror("Isso Facilita", message, parent=self.root)


def main() -> None:
    root = tk.Tk()
    AiControlWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
