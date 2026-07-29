"""Tk desktop interface for GARMIN-QPRO."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .controller import (
    DesktopActivityController,
    DesktopActivityStatus,
    DesktopActivityView,
    parse_drop_paths,
)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # Drag and drop is optional outside the packaged app.
    DND_FILES = None
    TkinterDnD = None


class GarminQProDesktopApp:
    """Single-window Windows interface."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        controller: DesktopActivityController | None = None,
    ) -> None:
        self.root = root
        self.controller = controller or DesktopActivityController()
        self._tree_item_ids: dict[str, int] = {}

        self.root.title("GARMIN-QPRO Beta")
        self.root.minsize(900, 620)
        self.root.geometry("1120x720")

        self._build_style()
        self._build_layout()
        self._configure_drop_target()
        self._refresh()

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("Drop.TLabel", font=("Segoe UI", 11), padding=18)
        style.configure("Status.TLabel", padding=(8, 4))
        style.configure("Accent.TButton", padding=(12, 7))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=(16, 14, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="GARMIN-QPRO", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            header,
            text="Anadir archivos",
            command=self._choose_files,
            style="Accent.TButton",
        ).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(
            header,
            text="Copiar todas",
            command=self._copy_all,
        ).grid(row=0, column=3, padx=(8, 0))
        ttk.Button(header, text="Limpiar", command=self._clear).grid(
            row=0, column=4, padx=(8, 0)
        )

        self.drop_area = ttk.Label(
            self.root,
            text="Arrastra aqui archivos FIT o ZIP",
            anchor="center",
            relief="solid",
            style="Drop.TLabel",
        )
        self.drop_area.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )

        list_frame = ttk.Frame(self.root, padding=(16, 0))
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("file", "activity", "key", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("file", text="Archivo")
        self.tree.heading("activity", text="Actividad")
        self.tree.heading("key", text="Clave")
        self.tree.heading("status", text="Estado")
        self.tree.column("file", width=210, minwidth=130)
        self.tree.column("activity", width=390, minwidth=180)
        self.tree.column("key", width=75, minwidth=60, anchor="center")
        self.tree.column("status", width=180, minwidth=120)
        self.tree.tag_configure("failed", foreground="#a32626")
        self.tree.tag_configure("review", foreground="#8a5a00")
        self.tree.tag_configure("ok", foreground="#166534")
        self.tree.bind("<<TreeviewSelect>>", self._on_selection)
        self.tree.grid(row=0, column=0, sticky="nsew")

        list_scroll = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=list_scroll.set)

        details = ttk.Frame(self.root, padding=16)
        details.grid(row=3, column=0, sticky="nsew")
        details.columnconfigure(0, weight=1)
        details.rowconfigure(2, weight=1)

        actions = ttk.Frame(details)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        actions.columnconfigure(0, weight=1)
        self.detail_label = ttk.Label(actions, text="Ninguna actividad seleccionada")
        self.detail_label.grid(row=0, column=0, sticky="w")
        self.key_var = tk.StringVar()
        self.key_combo = ttk.Combobox(
            actions,
            textvariable=self.key_var,
            values=self.controller.available_qpro_keys,
            state="readonly",
            width=8,
        )
        self.key_combo.grid(row=0, column=1, padx=(8, 4))
        self.apply_key_button = ttk.Button(
            actions,
            text="Aplicar clave",
            command=self._apply_manual_key,
        )
        self.apply_key_button.grid(row=0, column=2, padx=(4, 12))
        self.copy_row_button = ttk.Button(
            actions,
            text="Copiar fila",
            command=self._copy_selected,
        )
        self.copy_row_button.grid(row=0, column=3)

        self.warning_var = tk.StringVar()
        self.warning_label = ttk.Label(
            details,
            textvariable=self.warning_var,
            foreground="#8a5a00",
            wraplength=1020,
        )
        self.warning_label.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        preview_frame = ttk.Frame(details)
        preview_frame.grid(row=2, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        self.tsv_preview = tk.Text(
            preview_frame,
            height=7,
            wrap="none",
            font=("Consolas", 10),
            state="disabled",
            borderwidth=1,
            relief="solid",
        )
        self.tsv_preview.grid(row=0, column=0, sticky="nsew")
        preview_x = ttk.Scrollbar(
            preview_frame,
            orient="horizontal",
            command=self.tsv_preview.xview,
        )
        preview_x.grid(row=1, column=0, sticky="ew")
        self.tsv_preview.configure(xscrollcommand=preview_x.set)

        self.status_var = tk.StringVar()
        ttk.Label(
            self.root,
            textvariable=self.status_var,
            style="Status.TLabel",
            relief="sunken",
            anchor="w",
        ).grid(row=4, column=0, sticky="ew")

    def _configure_drop_target(self) -> None:
        if not getattr(self.root, "_garmin_qpro_dnd_available", False):
            self.drop_area.configure(text="Selecciona archivos FIT o ZIP")
            return
        self.drop_area.drop_target_register(DND_FILES)
        self.drop_area.dnd_bind("<<Drop>>", self._on_drop)

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
            self._process_paths(tuple(Path(value) for value in values))

    def _on_drop(self, event: object) -> None:
        raw_data = getattr(event, "data", "")
        paths = parse_drop_paths(raw_data, self.root.tk.splitlist)
        if paths:
            self._process_paths(paths)

    def _process_paths(self, paths: tuple[Path, ...]) -> None:
        self.status_var.set("Procesando actividades...")
        self.root.update_idletasks()
        self.controller.process_paths(paths)
        self._refresh(select_last=True)

    def _refresh(self, *, select_last: bool = False) -> None:
        current_id = self._selected_item_id()
        self.tree.delete(*self.tree.get_children())
        self._tree_item_ids.clear()

        for view in self.controller.items:
            iid = str(view.item_id)
            self._tree_item_ids[iid] = view.item_id
            activity_name = (
                view.workout_name
                or view.sport_profile_name
                or view.source_name
                or "Actividad sin nombre"
            )
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    view.input_name,
                    activity_name,
                    view.qpro_key or "",
                    view.message,
                ),
                tags=(self._tag_for_view(view),),
            )

        target_id = None
        if select_last and self.controller.items:
            target_id = self.controller.items[-1].item_id
        elif current_id is not None:
            target_id = current_id

        if target_id is not None and str(target_id) in self._tree_item_ids:
            self.tree.selection_set(str(target_id))
            self.tree.focus(str(target_id))
            self.tree.see(str(target_id))

        items = self.controller.items
        converted = sum(item.can_copy for item in items)
        review = sum(item.requires_manual_review for item in items)
        self.status_var.set(
            f"{len(items)} actividad(es) | {converted} fila(s) valida(s)"
            f" | {review} pendiente(s) de revision"
        )
        self._show_selected()

    def _on_selection(self, _event: object) -> None:
        self._show_selected()

    def _show_selected(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            self.detail_label.configure(text="Ninguna actividad seleccionada")
            self.warning_var.set("")
            self._set_preview("")
            self.key_combo.configure(state="disabled")
            self.apply_key_button.configure(state="disabled")
            self.copy_row_button.configure(state="disabled")
            return

        view = self.controller.get_item(item_id)
        activity_name = (
            view.workout_name
            or view.sport_profile_name
            or view.source_name
            or view.input_name
        )
        self.detail_label.configure(
            text=f"{activity_name} | {view.qpro_key or 'Sin clave'}"
        )
        self.warning_var.set(view.warning)
        self._set_preview(view.tsv or "")

        needs_key = view.status is DesktopActivityStatus.NEEDS_KEY
        self.key_combo.configure(state="readonly" if needs_key else "disabled")
        self.apply_key_button.configure(
            state="normal" if needs_key else "disabled"
        )
        self.copy_row_button.configure(
            state="normal" if view.can_copy else "disabled"
        )
        if view.qpro_key:
            self.key_var.set(view.qpro_key)
        elif needs_key and not self.key_var.get():
            self.key_var.set(self.controller.available_qpro_keys[0])

    def _apply_manual_key(self) -> None:
        item_id = self._selected_item_id()
        key = self.key_var.get().strip()
        if item_id is None or not key:
            return
        try:
            self.controller.apply_manual_key(item_id, key)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo aplicar la clave",
                str(exc),
                parent=self.root,
            )
            return
        self._refresh()

    def _copy_selected(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return
        try:
            self._copy_to_clipboard(self.controller.tsv_for_item(item_id))
        except ValueError as exc:
            messagebox.showwarning("Fila no disponible", str(exc), parent=self.root)

    def _copy_all(self) -> None:
        tsv = self.controller.all_tsv()
        if not tsv:
            messagebox.showinfo(
                "Sin filas",
                "No hay filas validas para copiar.",
                parent=self.root,
            )
            return
        self._copy_to_clipboard(tsv)

    def _copy_to_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update_idletasks()
        self.status_var.set("Copiado al portapapeles")

    def _clear(self) -> None:
        self.controller.clear()
        self.key_var.set("")
        self._refresh()

    def _selected_item_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._tree_item_ids.get(selection[0])

    def _set_preview(self, value: str) -> None:
        self.tsv_preview.configure(state="normal")
        self.tsv_preview.delete("1.0", "end")
        self.tsv_preview.insert("1.0", value)
        self.tsv_preview.configure(state="disabled")

    @staticmethod
    def _tag_for_view(view: DesktopActivityView) -> str:
        if view.status is DesktopActivityStatus.FAILED:
            return "failed"
        if view.requires_manual_review:
            return "review"
        return "ok"


def create_root() -> tk.Tk:
    if TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
            root._garmin_qpro_dnd_available = True  # type: ignore[attr-defined]
            return root
        except RuntimeError:
            # File selection remains available if the native tkdnd library
            # cannot load in a particular local Python installation.
            pass
    root = tk.Tk()
    root._garmin_qpro_dnd_available = False  # type: ignore[attr-defined]
    return root


def main() -> None:
    root = create_root()
    GarminQProDesktopApp(root)
    root.mainloop()
