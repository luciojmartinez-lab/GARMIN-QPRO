"""Modern single-window desktop interface for GARMIN-QPRO."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
import tempfile
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import customtkinter as ctk

from garmin_qpro.garmin import (
    DEFAULT_TOKEN_STORE,
    GarminMfaCancelledError,
    connect_garmin,
    diagnose_login_error,
    garminconnect_package_version,
)
from garmin_qpro.history import (
    CONVERTER_VERSION,
    HistoryFilters,
    HistoryStatus,
)

from .controller import DesktopActivityStatus, DesktopActivityView, parse_drop_paths
from .dialogs import GarminDiagnosticDialog, GarminLoginDialog, GarminMfaDialog
from .presentation import (
    STATUS_LABELS,
    display_activity_name,
    format_activity_datetime,
    validate_clipboard_rows,
)
from .theme import (
    BACKGROUND,
    BLUE,
    BLUE_DARK,
    BLUE_LIGHT,
    CARD_RADIUS,
    ERROR,
    FONT,
    FONT_SEMIBOLD,
    LINE,
    MONO_FONT,
    MUTED,
    SUCCESS,
    SURFACE,
    TEXT,
    WARNING,
)
from .workspace import DesktopWorkspace, RemoteActivityStatus, RemoteActivityView

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # Drag and drop remains optional in source environments.
    DND_FILES = None
    TkinterDnD = None

PageCallback = Callable[[], None]


class GarminQProDesktopApp:
    """Operational desktop workspace backed by the production converter."""

    PAGE_REMOTE = "remote"
    PAGE_HISTORY = "history"
    PAGE_IMPORT = "import"
    PAGE_CONNECTION = "connection"

    def __init__(
        self,
        root: tk.Tk,
        *,
        workspace: DesktopWorkspace | None = None,
    ) -> None:
        self.root = root
        self.workspace = workspace or DesktopWorkspace()
        self._active_page = self.PAGE_REMOTE
        self._busy = False
        self._remote_ids: dict[str, str] = {}
        self._import_ids: dict[str, int] = {}
        self._history_ids: dict[str, int] = {}
        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.root.title("GARMIN-QPRO")
        self.root.configure(background=BACKGROUND)
        self.root.minsize(1050, 680)
        self.root.geometry("1380x840")

        self._build_ttk_style()
        self._build_shell()
        self._build_remote_page()
        self._build_history_page()
        self._build_import_page()
        self._build_connection_page()
        self._configure_drop_target()
        self._show_page(self.PAGE_REMOTE)
        self._refresh_all_views()
        self.root.after(300, self._restore_session)

    def _build_ttk_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(
            "Garmin.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            borderwidth=0,
            rowheight=31,
            font=(FONT, 9),
        )
        style.configure(
            "Garmin.Treeview.Heading",
            background="#EEF2F7",
            foreground=TEXT,
            borderwidth=0,
            relief="flat",
            font=(FONT_SEMIBOLD, 9),
            padding=(8, 8),
        )
        style.map(
            "Garmin.Treeview",
            background=[("selected", BLUE_LIGHT)],
            foreground=[("selected", BLUE_DARK)],
        )
        style.configure(
            "Garmin.TCombobox",
            padding=5,
            font=(FONT, 9),
        )

    def _build_shell(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(
            self.root,
            fg_color=BLUE,
            corner_radius=0,
            height=72,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, padx=(20, 28), pady=12, sticky="w")
        ctk.CTkLabel(
            brand,
            text="GARMIN-QPRO",
            text_color="white",
            font=(FONT_SEMIBOLD, 20),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            brand,
            text="Conversión y archivo de entrenamiento",
            text_color="#DCEEFF",
            font=(FONT, 11),
        ).grid(row=1, column=0, sticky="w")

        navigation = ctk.CTkFrame(header, fg_color="transparent")
        navigation.grid(row=0, column=1, padx=8, pady=14, sticky="e")
        labels = (
            (self.PAGE_REMOTE, "Actividades nuevas"),
            (self.PAGE_HISTORY, "Historial"),
            (self.PAGE_IMPORT, "Importar FIT / ZIP"),
            (self.PAGE_CONNECTION, "Conexión"),
        )
        for column, (page, label) in enumerate(labels):
            button = ctk.CTkButton(
                navigation,
                text=label,
                width=130,
                height=34,
                corner_radius=6,
                fg_color="transparent",
                hover_color=BLUE_DARK,
                text_color="white",
                font=(FONT_SEMIBOLD, 10),
                command=lambda selected=page: self._show_page(selected),
            )
            button.grid(row=0, column=column, padx=3)
            self._nav_buttons[page] = button

        ctk.CTkLabel(
            header,
            text=f"Beta {CONVERTER_VERSION}",
            text_color="white",
            fg_color=BLUE_DARK,
            corner_radius=12,
            font=(FONT_SEMIBOLD, 9),
            width=92,
            height=26,
        ).grid(row=0, column=2, padx=(12, 20))

        body = ctk.CTkFrame(self.root, fg_color=BACKGROUND, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self._build_dashboard(body)

        self.page_host = ctk.CTkFrame(body, fg_color="transparent")
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Preparado")
        ctk.CTkLabel(
            self.root,
            textvariable=self.status_var,
            anchor="w",
            text_color=MUTED,
            fg_color="#EEF2F7",
            corner_radius=0,
            height=28,
            padx=18,
            font=(FONT, 9),
        ).grid(row=2, column=0, sticky="ew")

    def _build_dashboard(self, parent: ctk.CTkFrame) -> None:
        dashboard = ctk.CTkFrame(parent, fg_color="transparent")
        dashboard.grid(row=0, column=0, sticky="ew", padx=18, pady=14)
        for column in range(4):
            dashboard.grid_columnconfigure(column, weight=1, uniform="summary")

        self.connection_summary = self._summary_card(
            dashboard, 0, "Garmin", "Sin conexión", MUTED
        )
        self.new_summary = self._summary_card(
            dashboard, 1, "Actividades nuevas", "0", BLUE
        )
        self.history_summary = self._summary_card(
            dashboard, 2, "Guardadas", "0", SUCCESS
        )
        self.review_summary = self._summary_card(
            dashboard, 3, "Pendientes de revisión", "0", WARNING
        )

    def _summary_card(
        self,
        parent: ctk.CTkFrame,
        column: int,
        title: str,
        value: str,
        color: str,
    ) -> ctk.CTkLabel:
        card = ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=LINE,
        )
        card.grid(
            row=0,
            column=column,
            padx=(0 if column == 0 else 5, 0 if column == 3 else 5),
            sticky="ew",
        )
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(10, 0), sticky="ew")
        label = ctk.CTkLabel(
            card,
            text=value,
            text_color=color,
            font=(FONT_SEMIBOLD, 17),
            anchor="w",
        )
        label.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        return label

    def _new_page(self, name: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.page_host, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        self._pages[name] = page
        return page

    def _page_header(
        self,
        page: ctk.CTkFrame,
        title: str,
        subtitle: str,
    ) -> ctk.CTkFrame:
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text=title,
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 18),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=subtitle,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=1, column=0, sticky="w")
        return header

    def _card(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=SURFACE,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=LINE,
        )

    def _primary_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        width: int = 120,
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=32,
            corner_radius=6,
            fg_color=BLUE,
            hover_color=BLUE_DARK,
            font=(FONT_SEMIBOLD, 10),
        )

    def _secondary_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        width: int = 108,
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=width,
            height=32,
            corner_radius=6,
            fg_color=SURFACE,
            hover_color="#EEF2F7",
            text_color=TEXT,
            border_width=1,
            border_color=LINE,
            font=(FONT_SEMIBOLD, 10),
        )

    def _build_remote_page(self) -> None:
        page = self._new_page(self.PAGE_REMOTE)
        header = self._page_header(
            page,
            "Actividades nuevas",
            "Actividades de Garmin que todavía no están en el historial local",
        )
        self._secondary_button(
            header, "Actualizar", self._refresh_remote, width=105
        ).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        self._primary_button(
            header, "Convertir selección", self._convert_remote, width=155
        ).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        table_card = self._card(content)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(1, weight=1)
        self.remote_empty_var = tk.StringVar(
            value="Conecta Garmin para consultar actividades."
        )
        ctk.CTkLabel(
            table_card,
            textvariable=self.remote_empty_var,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(10, 5), sticky="ew")
        self.remote_tree = self._make_tree(
            table_card,
            ("date", "activity", "profile", "key", "status"),
            ("Fecha", "Actividad", "Perfil", "Clave", "Estado"),
            (115, 270, 125, 65, 125),
            selectmode="extended",
        )
        self.remote_tree.bind("<<TreeviewSelect>>", self._show_remote_detail)

        detail = self._card(content)
        detail.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(
            detail,
            text="Detalle",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 13),
            anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="ew")
        self.remote_detail_var = tk.StringVar(value="Ninguna actividad seleccionada")
        ctk.CTkLabel(
            detail,
            textvariable=self.remote_detail_var,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")

        key_bar = ctk.CTkFrame(detail, fg_color="transparent")
        key_bar.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")
        key_bar.grid_columnconfigure(0, weight=1)
        self.remote_key_var = tk.StringVar()
        self.remote_key_combo = ttk.Combobox(
            key_bar,
            textvariable=self.remote_key_var,
            values=self.workspace.importer.available_qpro_keys,
            state="readonly",
            width=9,
            style="Garmin.TCombobox",
        )
        self.remote_key_combo.grid(row=0, column=0, sticky="w")
        self._secondary_button(
            key_bar, "Aplicar clave", self._apply_remote_key, width=110
        ).grid(row=0, column=1, padx=(8, 0))
        self._secondary_button(
            key_bar, "Copiar fila", self._copy_remote_rows, width=100
        ).grid(row=0, column=2, padx=(8, 0))

        self.remote_warning_var = tk.StringVar()
        ctk.CTkLabel(
            detail,
            textvariable=self.remote_warning_var,
            text_color=WARNING,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=3, column=0, padx=14, pady=(0, 8), sticky="ew")
        self.remote_preview = self._make_preview(detail)
        self.remote_preview.grid(row=4, column=0, padx=14, pady=(0, 14), sticky="nsew")

    def _build_history_page(self) -> None:
        page = self._new_page(self.PAGE_HISTORY)
        header = self._page_header(
            page,
            "Historial",
            "Conversiones locales con control de revisión y duplicados",
        )
        self._secondary_button(
            header, "Actualizar", self._refresh_history, width=105
        ).grid(row=0, column=1, rowspan=2)

        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        filters = self._card(content)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        filters.grid_columnconfigure(0, weight=1)
        self.history_search_var = tk.StringVar()
        search = ctk.CTkEntry(
            filters,
            textvariable=self.history_search_var,
            placeholder_text="Buscar actividad",
            height=32,
            corner_radius=6,
            border_color=LINE,
            fg_color=SURFACE,
            text_color=TEXT,
        )
        search.grid(row=0, column=0, padx=(12, 6), pady=10, sticky="ew")
        self.history_key_var = tk.StringVar(value="Todas")
        key_values = ("Todas",) + self.workspace.importer.available_qpro_keys
        ttk.Combobox(
            filters,
            textvariable=self.history_key_var,
            values=key_values,
            state="readonly",
            width=10,
            style="Garmin.TCombobox",
        ).grid(row=0, column=1, padx=6)
        self.history_status_var = tk.StringVar(value="Activas")
        ttk.Combobox(
            filters,
            textvariable=self.history_status_var,
            values=("Activas", "Pendiente", "Convertida", "Revisada", "Archivada"),
            state="readonly",
            width=12,
            style="Garmin.TCombobox",
        ).grid(row=0, column=2, padx=6)
        self._primary_button(
            filters, "Filtrar", self._refresh_history, width=90
        ).grid(row=0, column=3, padx=(6, 12))

        history_card = self._card(content)
        history_card.grid(row=1, column=0, sticky="nsew")
        history_card.grid_columnconfigure(0, weight=1)
        history_card.grid_rowconfigure(0, weight=1)
        self.history_tree = self._make_tree(
            history_card,
            ("date", "activity", "profile", "key", "status", "source"),
            ("Fecha", "Actividad", "Perfil", "Clave", "Estado", "Origen"),
            (125, 340, 135, 65, 100, 90),
            selectmode="browse",
            row=0,
        )
        self.history_tree.bind("<<TreeviewSelect>>", self._show_history_detail)

        action_bar = ctk.CTkFrame(history_card, fg_color="transparent")
        action_bar.grid(row=1, column=0, padx=12, pady=10, sticky="ew")
        action_bar.grid_columnconfigure(0, weight=1)
        self.history_warning_var = tk.StringVar()
        ctk.CTkLabel(
            action_bar,
            textvariable=self.history_warning_var,
            text_color=WARNING,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self._secondary_button(
            action_bar, "Copiar", self._copy_history, width=82
        ).grid(row=0, column=1, padx=3)
        self._secondary_button(
            action_bar, "Reconvertir", self._reconvert_history, width=100
        ).grid(row=0, column=2, padx=3)
        self._secondary_button(
            action_bar, "Marcar revisada", self._mark_history_reviewed, width=120
        ).grid(row=0, column=3, padx=3)
        self._secondary_button(
            action_bar, "Archivar", self._archive_history, width=82
        ).grid(row=0, column=4, padx=3)
        ctk.CTkButton(
            action_bar,
            text="Eliminar",
            command=self._delete_history,
            width=82,
            height=32,
            corner_radius=6,
            fg_color=SURFACE,
            hover_color="#FDECEC",
            text_color=ERROR,
            border_width=1,
            border_color=LINE,
            font=(FONT_SEMIBOLD, 10),
        ).grid(row=0, column=5, padx=(3, 0))

        self.history_preview = self._make_preview(history_card, height=4)
        self.history_preview.grid(
            row=2, column=0, padx=12, pady=(0, 12), sticky="nsew"
        )

    def _build_import_page(self) -> None:
        page = self._new_page(self.PAGE_IMPORT)
        header = self._page_header(
            page,
            "Importar FIT / ZIP",
            "Conversión local de archivos originales, incluso sin conexión",
        )
        self._secondary_button(
            header, "Limpiar lista", self._clear_imports, width=110
        ).grid(row=0, column=1, rowspan=2, padx=(8, 0))
        self._primary_button(
            header, "Añadir archivos", self._choose_files, width=125
        ).grid(row=0, column=2, rowspan=2, padx=(8, 0))

        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=3)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        list_card = self._card(content)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(1, weight=1)
        self.drop_area = ctk.CTkFrame(
            list_card,
            fg_color=BLUE_LIGHT,
            border_width=1,
            border_color="#B8D8F5",
            corner_radius=6,
            height=58,
        )
        self.drop_area.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        self.drop_area.grid_propagate(False)
        self.drop_area.grid_columnconfigure(0, weight=1)
        self.drop_label = ctk.CTkLabel(
            self.drop_area,
            text="FIT / ZIP   ·   Arrastra o selecciona archivos",
            text_color=BLUE_DARK,
            font=(FONT_SEMIBOLD, 11),
        )
        self.drop_label.grid(row=0, column=0, sticky="nsew", pady=17)

        self.import_tree = self._make_tree(
            list_card,
            ("file", "activity", "profile", "key", "status"),
            ("Archivo", "Actividad", "Perfil", "Clave", "Estado"),
            (180, 250, 125, 65, 120),
            selectmode="extended",
        )
        self.import_tree.bind("<<TreeviewSelect>>", self._show_import_detail)

        detail = self._card(content)
        detail.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(4, weight=1)
        ctk.CTkLabel(
            detail,
            text="Resultado",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 13),
            anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="ew")
        self.import_detail_var = tk.StringVar(value="Ninguna actividad seleccionada")
        ctk.CTkLabel(
            detail,
            textvariable=self.import_detail_var,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")
        import_actions = ctk.CTkFrame(detail, fg_color="transparent")
        import_actions.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")
        import_actions.grid_columnconfigure(0, weight=1)
        self.import_key_var = tk.StringVar()
        self.import_key_combo = ttk.Combobox(
            import_actions,
            textvariable=self.import_key_var,
            values=self.workspace.importer.available_qpro_keys,
            state="readonly",
            width=9,
            style="Garmin.TCombobox",
        )
        self.import_key_combo.grid(row=0, column=0, sticky="w")
        self._secondary_button(
            import_actions, "Aplicar clave", self._apply_import_key, width=110
        ).grid(row=0, column=1, padx=(8, 0))
        self._secondary_button(
            import_actions, "Copiar fila", self._copy_import_rows, width=100
        ).grid(row=0, column=2, padx=(8, 0))
        self._secondary_button(
            import_actions, "Copiar todas", self._copy_all_imports, width=105
        ).grid(row=0, column=3, padx=(8, 0))
        self.import_warning_var = tk.StringVar()
        ctk.CTkLabel(
            detail,
            textvariable=self.import_warning_var,
            text_color=WARNING,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(row=3, column=0, padx=14, pady=(0, 8), sticky="ew")
        self.import_preview = self._make_preview(detail)
        self.import_preview.grid(row=4, column=0, padx=14, pady=(0, 14), sticky="nsew")

    def _build_connection_page(self) -> None:
        page = self._new_page(self.PAGE_CONNECTION)
        self._page_header(
            page,
            "Conexión y almacenamiento",
            "La contraseña no se guarda; la sesión se protege con Windows",
        )
        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        connection_card = self._card(content)
        connection_card.grid(row=0, column=0, sticky="new", padx=(0, 6))
        connection_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            connection_card,
            text="Garmin Connect",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 14),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 4), sticky="ew")
        self.connection_detail_var = tk.StringVar(value="Sin conexión")
        ctk.CTkLabel(
            connection_card,
            textvariable=self.connection_detail_var,
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, padx=16, pady=(0, 14), sticky="ew")
        connection_actions = ctk.CTkFrame(connection_card, fg_color="transparent")
        connection_actions.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="w")
        self.connect_button = self._primary_button(
            connection_actions, "Conectar", self._connect_garmin, width=110
        )
        self.connect_button.grid(row=0, column=0)
        self._secondary_button(
            connection_actions, "Desconectar", self._disconnect_garmin, width=110
        ).grid(row=0, column=1, padx=(8, 0))

        storage_card = self._card(content)
        storage_card.grid(row=0, column=1, sticky="new", padx=(6, 0))
        storage_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            storage_card,
            text="Historial local",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 14),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(16, 4), sticky="ew")
        ctk.CTkLabel(
            storage_card,
            text=str(self.workspace.history.path),
            text_color=MUTED,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=500,
        ).grid(row=1, column=0, padx=16, pady=(0, 6), sticky="ew")
        ctk.CTkLabel(
            storage_card,
            text="23 columnas QPro · sesión local cifrada con Windows DPAPI",
            text_color=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=2, column=0, padx=16, pady=(0, 5), sticky="ew")
        ctk.CTkLabel(
            storage_card,
            text=f"garminconnect {garminconnect_package_version()}",
            text_color=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

    def _make_tree(
        self,
        parent: ctk.CTkFrame,
        columns: tuple[str, ...],
        headings: tuple[str, ...],
        widths: tuple[int, ...],
        *,
        selectmode: str,
        row: int = 1,
    ) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 12))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            selectmode=selectmode,
            style="Garmin.Treeview",
        )
        for name, heading, width in zip(columns, headings, widths, strict=True):
            tree.heading(name, text=heading)
            tree.column(name, width=width, minwidth=55, anchor="w")
        tree.tag_configure("error", foreground=ERROR)
        tree.tag_configure("review", foreground=WARNING)
        tree.tag_configure("ok", foreground=SUCCESS)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scrollbar.set)
        return tree

    def _make_preview(
        self,
        parent: tk.Misc,
        *,
        height: int = 7,
    ) -> tk.Text:
        preview = tk.Text(
            parent,
            height=height,
            wrap="none",
            font=(MONO_FONT, 9),
            state="disabled",
            borderwidth=1,
            relief="solid",
            background="#FBFCFE",
            foreground=TEXT,
            highlightthickness=0,
            padx=8,
            pady=8,
        )
        return preview

    def _configure_drop_target(self) -> None:
        available = bool(getattr(self.root, "_garmin_qpro_dnd_available", False))
        if not available or DND_FILES is None:
            self.drop_label.configure(text="FIT / ZIP   ·   Selecciona archivos")
            return
        for target in (self.drop_area, self.drop_label):
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", self._on_drop)

    def _show_page(self, page: str) -> None:
        self._active_page = page
        self._pages[page].tkraise()
        for name, button in self._nav_buttons.items():
            active = name == page
            button.configure(
                fg_color="white" if active else "transparent",
                text_color=BLUE if active else "white",
                hover_color="white" if active else BLUE_DARK,
            )
        if page == self.PAGE_HISTORY:
            self._refresh_history()

    def _restore_session(self) -> None:
        self._run_task(
            "Restaurando la sesión de Garmin...",
            self.workspace.restore_garmin,
            lambda restored: self._after_restore(bool(restored)),
            on_error=self._show_garmin_login_error,
        )

    def _after_restore(self, restored: bool) -> None:
        self._refresh_connection()
        if restored:
            self._refresh_remote()

    def _connect_garmin(self) -> None:
        credentials = GarminLoginDialog(self.root).show()
        if credentials is None:
            return

        def prompt_mfa() -> str:
            code = GarminMfaDialog(self.root).show()
            if not code:
                raise GarminMfaCancelledError(
                    "Garmin verification was cancelled"
                )
            return code

        self.status_var.set("Conectando con Garmin...")
        self.root.update_idletasks()
        try:
            self.workspace.connect_garmin(
                email=credentials.email,
                password=credentials.password,
                prompt_mfa=prompt_mfa,
            )
        except Exception as exc:
            self._refresh_connection()
            self._show_garmin_login_error(exc)
            return
        finally:
            credentials = None
        self._refresh_connection()
        self._refresh_remote()

    def _disconnect_garmin(self) -> None:
        if not messagebox.askyesno(
            "Desconectar Garmin",
            "Se eliminará la sesión guardada en este equipo.",
            parent=self.root,
        ):
            return
        self.workspace.disconnect_garmin()
        self._refresh_remote_tree()
        self._refresh_connection()
        self.status_var.set("Garmin desconectado")

    def _refresh_remote(self) -> None:
        if not self.workspace.connected:
            self._show_page(self.PAGE_CONNECTION)
            self.status_var.set("Conecta Garmin para consultar actividades")
            return
        self._run_task(
            "Consultando actividades nuevas...",
            lambda: self.workspace.refresh_remote_activities(limit=30),
            lambda _result: self._after_remote_refresh(),
        )

    def _after_remote_refresh(self) -> None:
        self._refresh_remote_tree()
        self._refresh_dashboard()
        self.status_var.set("Actividades de Garmin actualizadas")

    def _refresh_remote_tree(self) -> None:
        self.remote_tree.delete(*self.remote_tree.get_children())
        self._remote_ids.clear()
        for view in self.workspace.remote_activities:
            iid = f"garmin:{view.activity_id}"
            self._remote_ids[iid] = view.activity_id
            self.remote_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    format_activity_datetime(view.activity_datetime),
                    display_activity_name(
                        view.workout_name,
                        view.profile_name,
                        view.name,
                    ),
                    view.profile_name or view.activity_type or "",
                    view.qpro_key or "",
                    self._remote_status_label(view),
                ),
                tags=(self._remote_tag(view),),
            )
        count = len(self.workspace.remote_activities)
        self.remote_empty_var.set(
            f"{count} actividad(es) nueva(s)"
            if count
            else (
                "No hay actividades nuevas."
                if self.workspace.connected
                else "Conecta Garmin para consultar actividades."
            )
        )
        self._show_remote_detail()

    def _show_remote_detail(self, _event: object | None = None) -> None:
        selected = self._selected_remote_views()
        if not selected:
            self.remote_detail_var.set("Ninguna actividad seleccionada")
            self.remote_warning_var.set("")
            self._set_preview(self.remote_preview, "")
            return
        view = selected[0]
        self.remote_detail_var.set(
            f"{display_activity_name(view.workout_name, view.profile_name, view.name)}\n"
            f"Clave: {view.qpro_key or 'sin resolver'} · "
            f"Origen: {view.resolution_source or 'pendiente'}"
        )
        self.remote_warning_var.set(view.warning)
        self.remote_key_var.set(view.qpro_key or "")
        self._set_preview(self.remote_preview, view.tsv or "")

    def _apply_remote_key(self) -> None:
        selected = self._selected_remote_views()
        key = self.remote_key_var.get().strip()
        if len(selected) != 1 or not key:
            self.status_var.set("Selecciona una actividad y una clave")
            return
        try:
            self.workspace.set_remote_key(selected[0].activity_id, key)
        except Exception as exc:
            self._show_safe_error("No se pudo aplicar la clave", exc)
            return
        self._refresh_remote_tree()
        self.remote_tree.selection_set(f"garmin:{selected[0].activity_id}")
        self._show_remote_detail()

    def _convert_remote(self) -> None:
        selected = self._selected_remote_views()
        if not selected:
            self.status_var.set("Selecciona al menos una actividad")
            return
        ids = tuple(view.activity_id for view in selected)
        self._run_task(
            "Convirtiendo actividades...",
            lambda: self.workspace.convert_remote(ids),
            lambda _result: self._after_remote_conversion(),
        )

    def _after_remote_conversion(self) -> None:
        self._refresh_remote_tree()
        self._refresh_history()
        self._refresh_dashboard()
        self.status_var.set("Conversión terminada")

    def _copy_remote_rows(self) -> None:
        rows = tuple(
            view.tsv for view in self._selected_remote_views() if view.tsv is not None
        )
        self._copy_rows(rows)

    def _choose_files(self) -> None:
        values = filedialog.askopenfilenames(
            parent=self.root,
            title="Seleccionar actividades Garmin",
            filetypes=(
                ("Actividades Garmin", "*.fit *.FIT *.zip *.ZIP"),
                ("Todos los archivos", "*.*"),
            ),
        )
        if values:
            self._process_import_paths(tuple(Path(value) for value in values))

    def _on_drop(self, event: object) -> None:
        raw_data = getattr(event, "data", "")
        paths = parse_drop_paths(raw_data, self.root.tk.splitlist)
        if paths:
            self._show_page(self.PAGE_IMPORT)
            self._process_import_paths(paths)

    def _process_import_paths(self, paths: tuple[Path, ...]) -> None:
        self._run_task(
            "Procesando archivos...",
            lambda: self.workspace.import_paths(paths),
            lambda _result: self._after_import(),
        )

    def _after_import(self) -> None:
        self._refresh_import_tree(select_last=True)
        self._refresh_history()
        self._refresh_dashboard()
        self.status_var.set("Archivos procesados")

    def _refresh_import_tree(self, *, select_last: bool = False) -> None:
        current = self.import_tree.selection()
        self.import_tree.delete(*self.import_tree.get_children())
        self._import_ids.clear()
        for view in self.workspace.importer.items:
            iid = f"import:{view.item_id}"
            self._import_ids[iid] = view.item_id
            self.import_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    view.input_name,
                    display_activity_name(
                        view.workout_name,
                        view.sport_profile_name,
                        view.source_name,
                    ),
                    view.sport_profile_name or "",
                    view.qpro_key or "",
                    view.message,
                ),
                tags=(self._import_tag(view),),
            )
        target = None
        if select_last and self.workspace.importer.items:
            target = f"import:{self.workspace.importer.items[-1].item_id}"
        elif current and current[0] in self._import_ids:
            target = current[0]
        if target:
            self.import_tree.selection_set(target)
            self.import_tree.see(target)
        self._show_import_detail()

    def _show_import_detail(self, _event: object | None = None) -> None:
        views = self._selected_import_views()
        if not views:
            self.import_detail_var.set("Ninguna actividad seleccionada")
            self.import_warning_var.set("")
            self._set_preview(self.import_preview, "")
            return
        view = views[0]
        self.import_detail_var.set(
            f"{display_activity_name(view.workout_name, view.sport_profile_name, view.source_name)}\n"
            f"Clave: {view.qpro_key or 'sin resolver'} · {view.message}"
        )
        self.import_warning_var.set(view.warning)
        self.import_key_var.set(view.qpro_key or "")
        self._set_preview(self.import_preview, view.tsv or "")

    def _apply_import_key(self) -> None:
        views = self._selected_import_views()
        key = self.import_key_var.get().strip()
        if len(views) != 1 or not key:
            self.status_var.set("Selecciona una actividad pendiente y una clave")
            return
        try:
            self.workspace.apply_import_key(views[0].item_id, key)
        except Exception as exc:
            self._show_safe_error("No se pudo aplicar la clave", exc)
            return
        self._refresh_import_tree()
        self._refresh_history()
        self._refresh_dashboard()

    def _copy_import_rows(self) -> None:
        rows = tuple(
            view.tsv for view in self._selected_import_views() if view.tsv is not None
        )
        self._copy_rows(rows)

    def _copy_all_imports(self) -> None:
        rows = tuple(
            view.tsv
            for view in self.workspace.importer.items
            if view.can_copy and view.tsv is not None
        )
        self._copy_rows(rows)

    def _clear_imports(self) -> None:
        self.workspace.importer.clear()
        self._refresh_import_tree()
        self.status_var.set("Lista de importación vacía")

    def _refresh_history(self) -> None:
        status_text = self.history_status_var.get()
        status_by_label = {label: status for status, label in STATUS_LABELS.items()}
        status = status_by_label.get(status_text)
        filters = HistoryFilters(
            search=self.history_search_var.get().strip() or None,
            qpro_key=(
                None
                if self.history_key_var.get() in {"", "Todas"}
                else self.history_key_var.get()
            ),
            status=status,
            include_archived=status is HistoryStatus.ARCHIVED,
        )
        records = self.workspace.history_items(filters)
        self.history_tree.delete(*self.history_tree.get_children())
        self._history_ids.clear()
        for record in records:
            iid = f"history:{record.id}"
            self._history_ids[iid] = record.id
            self.history_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    format_activity_datetime(record.activity_datetime or record.converted_at),
                    display_activity_name(
                        record.workout_name,
                        record.profile_name,
                        record.source_name,
                    ),
                    record.profile_name or "",
                    record.qpro_key,
                    STATUS_LABELS[record.status],
                    record.source_type.upper(),
                ),
                tags=("review" if record.warnings else "ok",),
            )
        self._show_history_detail()
        self._refresh_dashboard()

    def _show_history_detail(self, _event: object | None = None) -> None:
        record = self._selected_history_record()
        if record is None:
            self.history_warning_var.set("")
            self._set_preview(self.history_preview, "")
            return
        warning = "; ".join(record.warnings)
        if record.manual_key:
            warning = (
                f"{warning}; " if warning else ""
            ) + "Clave seleccionada manualmente"
        self.history_warning_var.set(warning)
        self._set_preview(self.history_preview, record.tsv)

    def _copy_history(self) -> None:
        record = self._selected_history_record()
        self._copy_rows((record.tsv,)) if record else None

    def _mark_history_reviewed(self) -> None:
        self._change_history_status(HistoryStatus.REVIEWED)

    def _archive_history(self) -> None:
        self._change_history_status(HistoryStatus.ARCHIVED)

    def _change_history_status(self, status: HistoryStatus) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        self.workspace.set_history_status(record.id, status)
        self._refresh_history()
        self.status_var.set(f"Actividad marcada como {STATUS_LABELS[status].lower()}")

    def _delete_history(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        if not messagebox.askyesno(
            "Eliminar del historial",
            "Esta acción elimina la conversión local, no la actividad de Garmin.",
            parent=self.root,
        ):
            return
        self.workspace.delete_history(record.id)
        self._refresh_history()
        self.status_var.set("Conversión eliminada del historial")

    def _reconvert_history(self) -> None:
        record = self._selected_history_record()
        if record is None:
            return
        manual_path: Path | None = None
        if record.garmin_activity_id is None:
            value = filedialog.askopenfilename(
                parent=self.root,
                title="Seleccionar el FIT o ZIP original",
                filetypes=(
                    ("Actividades Garmin", "*.fit *.FIT *.zip *.ZIP"),
                    ("Todos los archivos", "*.*"),
                ),
            )
            if not value:
                return
            manual_path = Path(value)
        key = record.qpro_key if record.manual_key else None
        self._run_task(
            "Reconvirtiendo actividad...",
            lambda: self.workspace.reconvert_history(
                record.id,
                explicit_qpro_key=key,
                manual_path=manual_path,
            ),
            lambda _result: self._after_history_reconvert(),
        )

    def _after_history_reconvert(self) -> None:
        self._refresh_history()
        self.status_var.set("Actividad reconvertida")

    def _refresh_connection(self) -> None:
        connected = self.workspace.connected
        self.connection_summary.configure(
            text="Conectado" if connected else "Sin conexión",
            text_color=SUCCESS if connected else MUTED,
        )
        email = self.workspace.garmin_email
        self.connection_detail_var.set(
            f"Sesión activa\n{email or ''}".strip()
            if connected
            else "Sin conexión. El historial y la importación local siguen disponibles."
        )
        self.connect_button.configure(state="disabled" if connected else "normal")

    def _refresh_dashboard(self) -> None:
        self._refresh_connection()
        self.new_summary.configure(text=str(len(self.workspace.remote_activities)))
        self.history_summary.configure(text=str(self.workspace.history.count()))
        self.review_summary.configure(
            text=str(self.workspace.history.count(status=HistoryStatus.PENDING))
        )

    def _refresh_all_views(self) -> None:
        self._refresh_remote_tree()
        self._refresh_import_tree()
        self._refresh_history()
        self._refresh_connection()

    def _run_task(
        self,
        label: str,
        action: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        quiet_error: bool = False,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        if self._busy:
            self.status_var.set("Hay una operación en curso")
            return
        self._busy = True
        self.status_var.set(label)

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                self.root.after(
                    0,
                    lambda error=exc: self._finish_task_error(
                        error,
                        quiet=quiet_error,
                        on_error=on_error,
                    ),
                )
                return
            self.root.after(0, lambda: self._finish_task_success(result, on_success))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_task_success(
        self,
        result: Any,
        on_success: Callable[[Any], None],
    ) -> None:
        self._busy = False
        on_success(result)

    def _finish_task_error(
        self,
        error: Exception,
        *,
        quiet: bool,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        self._busy = False
        self._refresh_connection()
        if on_error is not None:
            on_error(error)
        elif not quiet:
            self._show_safe_error("No se pudo completar la operación", error)
        else:
            self.status_var.set("Preparado")

    def _show_garmin_login_error(self, error: Exception) -> None:
        diagnostic = diagnose_login_error(error)
        self.status_var.set(diagnostic.title)
        GarminDiagnosticDialog(self.root, diagnostic).show()

    def _show_safe_error(self, title: str, _error: Exception) -> None:
        messagebox.showerror(
            title,
            "La operación no se ha completado. El historial local no se ha alterado.",
            parent=self.root,
        )
        self.status_var.set("Operación no completada")

    def _copy_rows(self, rows: tuple[str, ...]) -> None:
        if not rows:
            self.status_var.set("No hay filas válidas seleccionadas")
            return
        try:
            value = validate_clipboard_rows(rows)
        except ValueError as exc:
            messagebox.showerror("Fila no válida", str(exc), parent=self.root)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status_var.set(
            "Fila copiada" if len(rows) == 1 else f"{len(rows)} filas copiadas"
        )

    def _selected_remote_views(self) -> tuple[RemoteActivityView, ...]:
        selected = set(self.remote_tree.selection())
        return tuple(
            view
            for view in self.workspace.remote_activities
            if f"garmin:{view.activity_id}" in selected
        )

    def _selected_import_views(self) -> tuple[DesktopActivityView, ...]:
        selected_ids = {
            self._import_ids[iid]
            for iid in self.import_tree.selection()
            if iid in self._import_ids
        }
        return tuple(
            view
            for view in self.workspace.importer.items
            if view.item_id in selected_ids
        )

    def _selected_history_record(self) -> Any | None:
        selection = self.history_tree.selection()
        if not selection:
            return None
        record_id = self._history_ids.get(selection[0])
        return self.workspace.history.get(record_id) if record_id is not None else None

    @staticmethod
    def _remote_status_label(view: RemoteActivityView) -> str:
        return {
            RemoteActivityStatus.READY: "Lista",
            RemoteActivityStatus.NEEDS_KEY: "Elegir clave",
            RemoteActivityStatus.ERROR: "Error",
            RemoteActivityStatus.CONVERTED: "Convertida",
        }[view.status]

    @staticmethod
    def _remote_tag(view: RemoteActivityView) -> str:
        if view.status is RemoteActivityStatus.ERROR:
            return "error"
        if view.requires_manual_review or view.status is RemoteActivityStatus.NEEDS_KEY:
            return "review"
        return "ok"

    @staticmethod
    def _import_tag(view: DesktopActivityView) -> str:
        if view.status is DesktopActivityStatus.FAILED:
            return "error"
        if view.requires_manual_review:
            return "review"
        return "ok"

    @staticmethod
    def _set_preview(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")


def create_root() -> tk.Tk:
    if TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
            root._garmin_qpro_dnd_available = True  # type: ignore[attr-defined]
            return root
        except RuntimeError:
            pass
    root = tk.Tk()
    root._garmin_qpro_dnd_available = False  # type: ignore[attr-defined]
    return root


def main() -> None:
    if "--smoke-test-garmin" in sys.argv:
        try:
            reader = connect_garmin(token_store=DEFAULT_TOKEN_STORE)
            reader.list_activities(limit=1)
        except Exception:
            raise SystemExit(5) from None
        raise SystemExit(0)

    if (
        "--smoke-test-dpapi" in sys.argv
        or "--smoke-test-keyring" in sys.argv
    ):
        from garmin_qpro.garmin.session import (
            DpapiSessionVault,
            StoredGarminSession,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "session.dpapi"
            vault = DpapiSessionVault(path=path)
            saved = False
            try:
                expected = StoredGarminSession(
                    email="smoke-test@example.invalid",
                    token_data="temporary-token-" * 2_000,
                )
                vault.save(expected)
                saved = True
                encrypted = path.read_bytes()
                valid = (
                    vault.load() == expected
                    and expected.email.encode() not in encrypted
                    and expected.token_data.encode() not in encrypted
                )
            except Exception:
                valid = False
            finally:
                if saved:
                    try:
                        vault.clear()
                    except Exception:
                        valid = False
        raise SystemExit(0 if valid else 4)

    if "--smoke-test-diagnostic-dialog" in sys.argv:
        root = create_root()
        root.withdraw()
        valid = False
        try:
            root.attributes("-alpha", 0.55)
            dialog = GarminDiagnosticDialog(
                root,
                diagnose_login_error(RuntimeError("smoke test")),
            )
            root.after(100, dialog.close_button.invoke)
            dialog.show()
            valid = (
                abs(float(root.attributes("-alpha")) - 1.0) < 0.001
                and root.grab_current() is None
            )
        except Exception:
            valid = False
        finally:
            root.destroy()
        raise SystemExit(0 if valid else 6)

    root = create_root()
    if "--smoke-test-dnd" in sys.argv:
        available = bool(
            getattr(root, "_garmin_qpro_dnd_available", False)
        )
        root.destroy()
        raise SystemExit(0 if available else 3)
    GarminQProDesktopApp(root)
    root.mainloop()
