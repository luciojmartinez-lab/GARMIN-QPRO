"""Purpose-built modal dialogs for Garmin authentication."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from garmin_qpro.garmin import GarminLoginDiagnostic

from .theme import (
    BACKGROUND,
    BLUE,
    BLUE_DARK,
    CARD_RADIUS,
    FONT,
    FONT_SEMIBOLD,
    LINE,
    MUTED,
    SURFACE,
    TEXT,
)

LOGIN_DIALOG_WIDTH = 620
LOGIN_DIALOG_HEIGHT = 390


@dataclass(frozen=True, slots=True)
class LoginCredentials:
    email: str
    password: str


class GarminLoginDialog:
    """Wide login form that keeps credentials only in memory."""

    def __init__(self, parent: tk.Misc) -> None:
        self.result: LoginCredentials | None = None
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Conectar Garmin")
        self.window.geometry(f"{LOGIN_DIALOG_WIDTH}x{LOGIN_DIALOG_HEIGHT}")
        self.window.minsize(580, 360)
        self.window.configure(fg_color=BACKGROUND)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(0, weight=1)

        panel = ctk.CTkFrame(
            self.window,
            fg_color=SURFACE,
            corner_radius=CARD_RADIUS,
            border_width=1,
            border_color=LINE,
        )
        panel.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Garmin Connect",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 20),
            anchor="w",
        ).grid(row=0, column=0, padx=22, pady=(20, 2), sticky="ew")
        ctk.CTkLabel(
            panel,
            text="La contraseña se utiliza solo para iniciar la sesión y no se guarda.",
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=1, column=0, padx=22, pady=(0, 16), sticky="ew")

        ctk.CTkLabel(
            panel,
            text="Correo",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 10),
            anchor="w",
        ).grid(row=2, column=0, padx=22, pady=(0, 4), sticky="ew")
        self.email_entry = ctk.CTkEntry(
            panel,
            height=38,
            corner_radius=6,
            border_color=LINE,
            fg_color=SURFACE,
            text_color=TEXT,
        )
        self.email_entry.grid(row=3, column=0, padx=22, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(
            panel,
            text="Contraseña",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 10),
            anchor="w",
        ).grid(row=4, column=0, padx=22, pady=(0, 4), sticky="ew")
        self.password_entry = ctk.CTkEntry(
            panel,
            show="•",
            height=38,
            corner_radius=6,
            border_color=LINE,
            fg_color=SURFACE,
            text_color=TEXT,
        )
        self.password_entry.grid(
            row=5,
            column=0,
            padx=22,
            pady=(0, 18),
            sticky="ew",
        )

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=6, column=0, padx=22, pady=(0, 20), sticky="e")
        ctk.CTkButton(
            buttons,
            text="Cancelar",
            width=100,
            height=34,
            corner_radius=6,
            fg_color=SURFACE,
            hover_color="#EEF2F7",
            text_color=TEXT,
            border_width=1,
            border_color=LINE,
            command=self._cancel,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            buttons,
            text="Conectar",
            width=110,
            height=34,
            corner_radius=6,
            fg_color=BLUE,
            hover_color=BLUE_DARK,
            command=self._accept,
        ).grid(row=0, column=1)

        self.window.bind("<Return>", lambda _event: self._accept())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        self.window.after(100, self.email_entry.focus_set)

    def show(self) -> LoginCredentials | None:
        self.window.wait_window()
        return self.result

    def _accept(self) -> None:
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        if not email or not password:
            return
        self.result = LoginCredentials(email=email, password=password)
        self.password_entry.delete(0, "end")
        self.window.destroy()

    def _cancel(self) -> None:
        self.password_entry.delete(0, "end")
        self.result = None
        self.window.destroy()


class GarminMfaDialog:
    def __init__(self, parent: tk.Misc) -> None:
        self.result: str | None = None
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Verificación de Garmin")
        self.window.geometry("520x260")
        self.window.resizable(False, False)
        self.window.configure(fg_color=BACKGROUND)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.window,
            text="Verificación en dos pasos",
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 18),
            anchor="w",
        ).grid(row=0, column=0, padx=24, pady=(24, 4), sticky="ew")
        ctk.CTkLabel(
            self.window,
            text="Introduce el código nuevo enviado por Garmin.",
            text_color=MUTED,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=1, column=0, padx=24, pady=(0, 14), sticky="ew")
        self.code_entry = ctk.CTkEntry(
            self.window,
            height=42,
            corner_radius=6,
            border_color=LINE,
            fg_color=SURFACE,
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 15),
        )
        self.code_entry.grid(row=2, column=0, padx=24, sticky="ew")
        buttons = ctk.CTkFrame(self.window, fg_color="transparent")
        buttons.grid(row=3, column=0, padx=24, pady=22, sticky="e")
        ctk.CTkButton(
            buttons,
            text="Cancelar",
            width=100,
            fg_color=SURFACE,
            hover_color="#EEF2F7",
            text_color=TEXT,
            border_width=1,
            border_color=LINE,
            command=self._cancel,
        ).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkButton(
            buttons,
            text="Verificar",
            width=110,
            fg_color=BLUE,
            hover_color=BLUE_DARK,
            command=self._accept,
        ).grid(row=0, column=1)
        self.window.bind("<Return>", lambda _event: self._accept())
        self.window.bind("<Escape>", lambda _event: self._cancel())
        self.window.after(100, self.code_entry.focus_set)

    def show(self) -> str | None:
        self.window.wait_window()
        return self.result

    def _accept(self) -> None:
        code = self.code_entry.get().strip()
        if not code:
            return
        self.result = code
        self.code_entry.delete(0, "end")
        self.window.destroy()

    def _cancel(self) -> None:
        self.code_entry.delete(0, "end")
        self.result = None
        self.window.destroy()


class GarminDiagnosticDialog:
    def __init__(
        self,
        parent: tk.Misc,
        diagnostic: GarminLoginDiagnostic,
    ) -> None:
        self.parent = parent
        self._closed = False
        try:
            self._parent_state = parent.state()
        except (AttributeError, tk.TclError):
            self._parent_state = None
        self.window = ctk.CTkToplevel(parent)
        self.window.title(diagnostic.title)
        self.window.geometry("660x430")
        self.window.minsize(620, 400)
        self.window.configure(fg_color=BACKGROUND)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.window,
            text=diagnostic.title,
            text_color=TEXT,
            font=(FONT_SEMIBOLD, 19),
            anchor="w",
        ).grid(row=0, column=0, padx=26, pady=(24, 6), sticky="ew")
        ctk.CTkLabel(
            self.window,
            text=diagnostic.message,
            text_color=TEXT,
            font=(FONT, 11),
            justify="left",
            anchor="w",
            wraplength=600,
        ).grid(row=1, column=0, padx=26, pady=(0, 14), sticky="ew")
        ctk.CTkLabel(
            self.window,
            text=diagnostic.action,
            text_color=BLUE_DARK,
            fg_color="#E8F2FC",
            corner_radius=6,
            font=(FONT_SEMIBOLD, 10),
            justify="left",
            anchor="w",
            wraplength=570,
            padx=14,
            pady=10,
        ).grid(row=2, column=0, padx=26, pady=(0, 18), sticky="ew")
        ctk.CTkLabel(
            self.window,
            text="Diagnóstico técnico anonimizado",
            text_color=MUTED,
            font=(FONT_SEMIBOLD, 9),
            anchor="w",
        ).grid(row=3, column=0, padx=26, pady=(0, 4), sticky="ew")
        diagnostic_box = ctk.CTkTextbox(
            self.window,
            height=88,
            corner_radius=6,
            border_width=1,
            border_color=LINE,
            fg_color=SURFACE,
            text_color=TEXT,
            font=("Consolas", 10),
        )
        diagnostic_box.grid(row=4, column=0, padx=26, sticky="ew")
        diagnostic_box.insert("1.0", diagnostic.technical_text)
        diagnostic_box.configure(state="disabled")

        buttons = ctk.CTkFrame(self.window, fg_color="transparent")
        buttons.grid(row=5, column=0, padx=26, pady=22, sticky="e")
        copy_button = ctk.CTkButton(
            buttons,
            text="Copiar diagnóstico",
            width=145,
            fg_color=SURFACE,
            hover_color="#EEF2F7",
            text_color=TEXT,
            border_width=1,
            border_color=LINE,
        )

        def copy_diagnostic() -> None:
            self.window.clipboard_clear()
            self.window.clipboard_append(diagnostic.technical_text)
            self.window.update_idletasks()
            copy_button.configure(text="Copiado")

        copy_button.configure(command=copy_diagnostic)
        copy_button.grid(row=0, column=0, padx=(0, 8))
        self.close_button = ctk.CTkButton(
            buttons,
            text="Cerrar",
            width=100,
            fg_color=BLUE,
            hover_color=BLUE_DARK,
            command=self.close,
        )
        self.close_button.grid(row=0, column=1)
        self.window.bind("<Escape>", self._handle_escape)

    def show(self) -> None:
        try:
            self.window.wait_window()
        finally:
            self.close()

    def _handle_escape(self, _event: object | None = None) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                if self.window.grab_current() is self.window:
                    self.window.grab_release()
            except (AttributeError, tk.TclError):
                pass
            try:
                if self.window.winfo_exists():
                    self.window.destroy()
            except (AttributeError, tk.TclError):
                pass
        finally:
            self._restore_parent()

    def _restore_parent(self) -> None:
        try:
            if self._parent_state is not None:
                self.parent.state(self._parent_state)
        except (AttributeError, tk.TclError):
            pass
        finally:
            try:
                self.parent.attributes("-alpha", 1.0)
                self.parent.update_idletasks()
            except (AttributeError, tk.TclError):
                pass
