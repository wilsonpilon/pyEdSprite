import sqlite3
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
import os
import math
from collections import deque

import tkinter as tk
from tkinter import messagebox, simpledialog

import customtkinter as ctk


# ----------------------------
# Splashscreen (sem Pillow)
# ----------------------------
class SplashScreen(tk.Toplevel):
    def __init__(
        self,
        master: tk.Tk,
        image_candidates: List[str],
        show_ms: int = 1200,
        fade_ms: int = 900,
        fade_steps: int = 18,
    ) -> None:
        super().__init__(master)

        self._show_ms = int(show_ms)
        self._fade_ms = int(fade_ms)
        self._fade_steps = max(5, int(fade_steps))

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        self._img = self._load_first_image(image_candidates)

        self._container = tk.Frame(self, bg="#000000")
        self._container.pack(fill="both", expand=True)

        if self._img is not None:
            lbl = tk.Label(self._container, image=self._img, bd=0, bg="#000000")
            lbl.pack()
            self.update_idletasks()
            w, h = self._img.width(), self._img.height()
            self.geometry(f"{w}x{h}+{self._center_x(w)}+{self._center_y(h)}")
        else:
            lbl = tk.Label(
                self._container,
                text="pyEdSprite",
                fg="#FFFFFF",
                bg="#000000",
                font=("Segoe UI", 24, "bold"),
                padx=40,
                pady=30,
            )
            lbl.pack()
            self.update_idletasks()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"{w}x{h}+{self._center_x(w)}+{self._center_y(h)}")

        try:
            self.wm_attributes("-alpha", 1.0)
        except Exception:
            pass

        self.after(self._show_ms, self._start_fade_out)

    def _center_x(self, w: int) -> int:
        sw = self.winfo_screenwidth()
        return max(0, (sw - w) // 2)

    def _center_y(self, h: int) -> int:
        sh = self.winfo_screenheight()
        return max(0, (sh - h) // 2)

    def _load_first_image(self, candidates: List[str]) -> Optional[tk.PhotoImage]:
        for path in candidates:
            if not path:
                continue
            if not os.path.exists(path):
                continue
            try:
                return tk.PhotoImage(file=path)
            except Exception:
                continue
        return None

    def _start_fade_out(self) -> None:
        try:
            self.wm_attributes("-alpha")
        except Exception:
            self.destroy()
            return

        step_delay = max(10, self._fade_ms // self._fade_steps)
        self._fade_step(current=self._fade_steps, step_delay=step_delay)

    def _fade_step(self, current: int, step_delay: int) -> None:
        if current <= 0:
            self.destroy()
            return

        alpha = current / float(self._fade_steps)
        try:
            self.wm_attributes("-alpha", alpha)
        except Exception:
            self.destroy()
            return

        self.after(step_delay, lambda: self._fade_step(current - 1, step_delay))


def run_app_with_splash() -> None:
    app = SpriteEditorApp()
    app.withdraw()
    app.update_idletasks()

    splash = SplashScreen(
        master=app,
        image_candidates=["splashscreen.jpg", "splashscreen.png"],
        show_ms=1300,
        fade_ms=900,
        fade_steps=18,
    )

    def reveal_main() -> None:
        try:
            splash.destroy()
        except Exception:
            pass
        app.deiconify()
        app.lift()
        app.focus_force()

    splash.bind("<Destroy>", lambda _e: app.after(0, reveal_main))
    app.mainloop()


# ----------------------------
# MSX1 palette (TMS9918A-ish)
# ----------------------------
MSX1_PALETTE_HEX = [
    "#000000",  # 0 Transparent (visual: black)
    "#000000",  # 1 Black
    "#21C842",  # 2 Medium Green
    "#5EDC78",  # 3 Light Green
    "#5455ED",  # 4 Dark Blue
    "#7D76FC",  # 5 Light Blue
    "#D4524D",  # 6 Dark Red
    "#42EBF5",  # 7 Cyan
    "#FC5554",  # 8 Medium Red
    "#FF7978",  # 9 Light Red
    "#D4C154",  # 10 Dark Yellow
    "#E6CE80",  # 11 Light Yellow
    "#21B03B",  # 12 Dark Green
    "#C95BBA",  # 13 Magenta
    "#CCCCCC",  # 14 Gray
    "#FFFFFF",  # 15 White
]

# ============================
# UI scales
# ============================
EDITOR_SCALE = 16
THUMB_SCALE = 2
PREVIEW_SCALE = 2


# ----------------------------
# Brush model + helpers
# ----------------------------
@dataclass
class Brush:
    id: Optional[int]
    name: str
    width: int
    height: int
    rows: List[int]  # bitmask per row (<= 8 bits used)

    def validate(self) -> None:
        if not (1 <= self.width <= 8 and 1 <= self.height <= 8):
            raise ValueError("Brush deve ser 1..8 em largura/altura")
        if len(self.rows) != self.height:
            raise ValueError("Brush.rows deve ter height linhas")
        for r in self.rows:
            if not (0 <= r <= 0xFF):
                raise ValueError("Linha inválida no brush")

    def points_centered(self) -> List[Tuple[int, int]]:
        """Retorna offsets (dx,dy) com origem no centro do brush."""
        self.validate()
        ox = self.width // 2
        oy = self.height // 2
        pts: List[Tuple[int, int]] = []
        for y in range(self.height):
            row = self.rows[y]
            for x in range(self.width):
                if row & (1 << (self.width - 1 - x)):
                    pts.append((x - ox, y - oy))
        return pts

    @staticmethod
    def from_points(name: str, width: int, height: int, pts: List[Tuple[int, int]]) -> "Brush":
        rows = [0 for _ in range(height)]
        for x, y in pts:
            if 0 <= x < width and 0 <= y < height:
                rows[y] |= 1 << (width - 1 - x)
        return Brush(id=None, name=name, width=width, height=height, rows=rows)

    @staticmethod
    def square(name: str, size: int) -> "Brush":
        size = max(1, min(8, int(size)))
        rows = [((1 << size) - 1) for _ in range(size)]
        return Brush(id=None, name=name, width=size, height=size, rows=rows)

    @staticmethod
    def rect(name: str, width: int, height: int) -> "Brush":
        width = max(1, min(8, int(width)))
        height = max(1, min(8, int(height)))
        rows = [((1 << width) - 1) for _ in range(height)]
        return Brush(id=None, name=name, width=width, height=height, rows=rows)

    @staticmethod
    def round(name: str, diameter: int) -> "Brush":
        d = max(1, min(8, int(diameter)))
        r = (d - 1) / 2.0
        cx = (d - 1) / 2.0
        cy = (d - 1) / 2.0
        pts: List[Tuple[int, int]] = []
        for y in range(d):
            for x in range(d):
                if math.hypot(x - cx, y - cy) <= r + 0.001:
                    pts.append((x, y))
        return Brush.from_points(name=name, width=d, height=d, pts=pts)


# ----------------------------
# Data model (sprites)
# ----------------------------
@dataclass
class Sprite:
    size: int  # 8 or 16
    color_index: int  # 0..15 (MSX1 sprite color)
    rows: List[int]  # bitmask per row; width bits used

    @staticmethod
    def empty(size: int, color_index: int = 15) -> "Sprite":
        return Sprite(size=size, color_index=color_index, rows=[0 for _ in range(size)])

    def get_pixel(self, x: int, y: int) -> int:
        mask = 1 << (self.size - 1 - x)
        return 1 if (self.rows[y] & mask) else 0

    def set_pixel(self, x: int, y: int, value: int) -> None:
        mask = 1 << (self.size - 1 - x)
        if value:
            self.rows[y] |= mask
        else:
            self.rows[y] &= ~mask


# ----------------------------
# SQLite persistence
# ----------------------------
class SpriteDB:
    def __init__(self, db_path: str = "sprites.db") -> None:
        self.db_path = db_path
        self._init_db()
        self._init_brushes()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    sprite_size INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sprites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    sprite_index INTEGER NOT NULL,
                    color_index INTEGER NOT NULL,
                    bitmap BLOB NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(project_id, sprite_index)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS brushes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    mask BLOB NOT NULL,
                    created_at INTEGER NOT NULL,
                    user_defined INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    # ---------- Brushes ----------
    @staticmethod
    def _pack_brush(width: int, height: int, rows: List[int]) -> bytes:
        if not (1 <= width <= 8 and 1 <= height <= 8):
            raise ValueError("brush size inválido")
        if len(rows) != height:
            raise ValueError("rows inválidas")
        out = bytearray()
        for r in rows:
            out.append(r & 0xFF)
        return bytes(out)

    @staticmethod
    def _unpack_brush(width: int, height: int, blob: bytes) -> List[int]:
        if len(blob) != height:
            raise ValueError("mask inválida")
        return [int(b) & 0xFF for b in blob]

    def _init_brushes(self) -> None:
        """Insere pincéis predefinidos apenas se a tabela estiver vazia."""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM brushes")
            n = int(cur.fetchone()[0])
            if n > 0:
                return

            defaults: List[Brush] = [
                Brush(id=None, name="1x1 (pixel)", width=1, height=1, rows=[0b1]),
                Brush.rect(name="Quadrado 2x2", width=2, height=2),
                Brush.round(name="Redondo 3x3", diameter=3),
                Brush.rect(name="Retângulo 4x2", width=4, height=2),
                Brush.rect(name="Retângulo 2x4", width=2, height=4),
                Brush.round(name="Redondo 5x5", diameter=5),
            ]

            ts = int(time.time())
            for br in defaults:
                br.validate()
                blob = self._pack_brush(br.width, br.height, br.rows)
                conn.execute(
                    """
                    INSERT INTO brushes (name, width, height, mask, created_at, user_defined)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (br.name, br.width, br.height, blob, ts),
                )

    def list_brushes(self) -> List[Brush]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name, width, height, mask
                FROM brushes
                ORDER BY user_defined ASC, name ASC
                """
            )
            rows = cur.fetchall()

        out: List[Brush] = []
        for bid, name, w, h, blob in rows:
            rows_mask = self._unpack_brush(int(w), int(h), blob)
            out.append(Brush(id=int(bid), name=str(name), width=int(w), height=int(h), rows=rows_mask))
        return out

    def save_brush(self, name: str, width: int, height: int, rows: List[int], *, user_defined: bool = True) -> int:
        br = Brush(id=None, name=name, width=width, height=height, rows=rows)
        br.validate()
        blob = self._pack_brush(width, height, rows)
        ts = int(time.time())

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM brushes WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                bid = int(row[0])
                cur.execute(
                    """
                    UPDATE brushes
                    SET width = ?, height = ?, mask = ?, created_at = ?, user_defined = ?
                    WHERE id = ?
                    """,
                    (width, height, blob, ts, 1 if user_defined else 0, bid),
                )
                return bid

            cur.execute(
                """
                INSERT INTO brushes (name, width, height, mask, created_at, user_defined)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, width, height, blob, ts, 1 if user_defined else 0),
            )
            return int(cur.lastrowid)

    # ---------- Sprites ----------
    @staticmethod
    def _pack_rows(size: int, rows: List[int]) -> bytes:
        if size == 8:
            return bytes((r & 0xFF) for r in rows)
        if size == 16:
            out = bytearray()
            for r in rows:
                out.append((r >> 8) & 0xFF)
                out.append(r & 0xFF)
            return bytes(out)
        raise ValueError("size must be 8 or 16")

    @staticmethod
    def _unpack_rows(size: int, blob: bytes) -> List[int]:
        if size == 8:
            if len(blob) != 8:
                raise ValueError("bitmap inválido para 8x8")
            return [b for b in blob]
        if size == 16:
            if len(blob) != 32:
                raise ValueError("bitmap inválido para 16x16")
            rows2: List[int] = []
            for i in range(0, 32, 2):
                rows2.append((blob[i] << 8) | blob[i + 1])
            return rows2
        raise ValueError("size must be 8 or 16")

    def save_project(self, name: str, sprite_size: int, sprites: List[Sprite]) -> None:
        created_at = int(time.time())
        with self._connect() as conn:
            cur = conn.cursor()

            cur.execute("SELECT id FROM projects WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                project_id = row[0]
                cur.execute("DELETE FROM sprites WHERE project_id = ?", (project_id,))
                cur.execute(
                    "UPDATE projects SET sprite_size = ?, created_at = ? WHERE id = ?",
                    (sprite_size, created_at, project_id),
                )
            else:
                cur.execute(
                    "INSERT INTO projects (name, sprite_size, created_at) VALUES (?, ?, ?)",
                    (name, sprite_size, created_at),
                )
                project_id = cur.lastrowid

            for idx, sp in enumerate(sprites):
                blob = self._pack_rows(sprite_size, sp.rows)
                cur.execute(
                    """
                    INSERT INTO sprites (project_id, sprite_index, color_index, bitmap)
                    VALUES (?, ?, ?, ?)
                    """,
                    (project_id, idx, sp.color_index, blob),
                )

    def get_project_id_by_name(self, name: str) -> Optional[int]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM projects WHERE name = ?", (name,))
            row = cur.fetchone()
            return int(row[0]) if row else None

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, name, sprite_size, created_at
                FROM projects
                ORDER BY created_at DESC, name ASC
                """
            )
            rows = cur.fetchall()

        return [
            {"id": pid, "name": name, "sprite_size": ssize, "created_at": created_at}
            for (pid, name, ssize, created_at) in rows
        ]

    def load_project(self, project_id: int) -> Tuple[str, int, int, List[Sprite]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, sprite_size, created_at FROM projects WHERE id = ?", (project_id,))
            proj = cur.fetchone()
            if not proj:
                raise ValueError("Projeto não encontrado")

            name, sprite_size, created_at = proj

            cur.execute(
                """
                SELECT sprite_index, color_index, bitmap
                FROM sprites
                WHERE project_id = ?
                ORDER BY sprite_index ASC
                """,
                (project_id,),
            )
            spr_rows = cur.fetchall()

        sprites2: List[Sprite] = []
        for _sprite_index, color_index, bitmap in spr_rows:
            rows = self._unpack_rows(sprite_size, bitmap)
            sprites2.append(Sprite(size=sprite_size, color_index=color_index, rows=rows))

        expected = 256 if sprite_size == 8 else 64
        if len(sprites2) < expected:
            sprites2.extend([Sprite.empty(size=sprite_size, color_index=15) for _ in range(expected - len(sprites2))])
        elif len(sprites2) > expected:
            sprites2 = sprites2[:expected]

        return name, sprite_size, created_at, sprites2

    def load_first_sprite(self, project_id: int) -> Optional[Sprite]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT sprite_size FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            if not row:
                return None
            sprite_size = row[0]

            cur.execute(
                """
                SELECT color_index, bitmap
                FROM sprites
                WHERE project_id = ? AND sprite_index = 0
                """,
                (project_id,),
            )
            srow = cur.fetchone()
            if not srow:
                return Sprite.empty(size=sprite_size, color_index=15)

            color_index, bitmap = srow
            rows = self._unpack_rows(sprite_size, bitmap)
            return Sprite(size=sprite_size, color_index=color_index, rows=rows)


# ----------------------------
# Brush editor dialog
# ----------------------------
class BrushEditorDialog(ctk.CTkToplevel):
    def __init__(self, master: "SpriteEditorApp", initial: Optional[Brush] = None) -> None:
        super().__init__(master)
        self.title("Editor de Pincel (até 8x8)")
        self.geometry("560x520")
        self.transient(master)
        self.grab_set()

        self._result: Optional[Brush] = None

        self.w_var = tk.IntVar(value=initial.width if initial else 3)
        self.h_var = tk.IntVar(value=initial.height if initial else 3)

        self.shape_var = tk.StringVar(value="Redondo" if initial is None else "Personalizado")

        self._grid = [[0 for _ in range(8)] for _ in range(8)]
        if initial:
            for y in range(initial.height):
                row = initial.rows[y]
                for x in range(initial.width):
                    if row & (1 << (initial.width - 1 - x)):
                        self._grid[y][x] = 1

        top = ctk.CTkFrame(self)
        top.pack(side="top", fill="x", padx=12, pady=12)

        ctk.CTkLabel(top, text="Largura:").pack(side="left", padx=(0, 6))
        self.w_opt = ctk.CTkOptionMenu(top, values=[str(i) for i in range(1, 9)], command=self._on_w_changed)
        self.w_opt.pack(side="left", padx=(0, 12))
        self.w_opt.set(str(self.w_var.get()))

        ctk.CTkLabel(top, text="Altura:").pack(side="left", padx=(0, 6))
        self.h_opt = ctk.CTkOptionMenu(top, values=[str(i) for i in range(1, 9)], command=self._on_h_changed)
        self.h_opt.pack(side="left", padx=(0, 12))
        self.h_opt.set(str(self.h_var.get()))

        ctk.CTkLabel(top, text="Forma:").pack(side="left", padx=(0, 6))
        self.shape_opt = ctk.CTkOptionMenu(
            top,
            values=["Redondo", "Quadrado", "Retângulo", "Personalizado"],
            command=self._on_shape_changed,
        )
        self.shape_opt.pack(side="left")
        self.shape_opt.set(self.shape_var.get())

        mid = ctk.CTkFrame(self)
        mid.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 12))

        ctk.CTkLabel(mid, text="Clique para ligar/desligar células do pincel:").pack(side="top", anchor="w", pady=(10, 8))

        self.canvas = tk.Canvas(mid, width=8 * 48, height=8 * 48, bg="#111111", highlightthickness=0)
        self.canvas.pack(side="top", pady=(0, 10))
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        btn_row = ctk.CTkFrame(mid)
        btn_row.pack(side="top", fill="x", pady=(0, 10))

        ctk.CTkButton(btn_row, text="Preencher", command=self._fill).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Limpar", command=self._clear).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="Inverter", command=self._invert).pack(side="left", padx=6)

        bottom = ctk.CTkFrame(self)
        bottom.pack(side="bottom", fill="x", padx=12, pady=12)

        ctk.CTkButton(bottom, text="Cancelar", command=self._cancel).pack(side="right", padx=6)
        ctk.CTkButton(bottom, text="Usar este pincel", command=self._ok).pack(side="right", padx=6)

        self._apply_shape()
        self._redraw()

    def result(self) -> Optional[Brush]:
        return self._result

    def _on_w_changed(self, v: str) -> None:
        self.w_var.set(int(v))
        if self.shape_var.get() != "Personalizado":
            self._apply_shape()
        self._redraw()

    def _on_h_changed(self, v: str) -> None:
        self.h_var.set(int(v))
        if self.shape_var.get() != "Personalizado":
            self._apply_shape()
        self._redraw()

    def _on_shape_changed(self, v: str) -> None:
        self.shape_var.set(v)
        if v != "Personalizado":
            self._apply_shape()
        self._redraw()

    def _fill(self) -> None:
        w, h = self.w_var.get(), self.h_var.get()
        for y in range(h):
            for x in range(w):
                self._grid[y][x] = 1
        self.shape_var.set("Personalizado")
        self.shape_opt.set("Personalizado")
        self._redraw()

    def _clear(self) -> None:
        w, h = self.w_var.get(), self.h_var.get()
        for y in range(h):
            for x in range(w):
                self._grid[y][x] = 0
        self.shape_var.set("Personalizado")
        self.shape_opt.set("Personalizado")
        self._redraw()

    def _invert(self) -> None:
        w, h = self.w_var.get(), self.h_var.get()
        for y in range(h):
            for x in range(w):
                self._grid[y][x] = 0 if self._grid[y][x] else 1
        self.shape_var.set("Personalizado")
        self.shape_opt.set("Personalizado")
        self._redraw()

    def _apply_shape(self) -> None:
        w, h = self.w_var.get(), self.h_var.get()
        shape = self.shape_var.get()

        for yy in range(8):
            for xx in range(8):
                self._grid[yy][xx] = 0

        if shape == "Quadrado":
            s = min(w, h)
            self.w_var.set(s)
            self.h_var.set(s)
            self.w_opt.set(str(s))
            self.h_opt.set(str(s))
            w, h = s, s
            for y in range(h):
                for x in range(w):
                    self._grid[y][x] = 1
            return

        if shape == "Retângulo":
            for y in range(h):
                for x in range(w):
                    self._grid[y][x] = 1
            return

        if shape == "Redondo":
            cx = (w - 1) / 2.0
            cy = (h - 1) / 2.0
            rx = (w - 1) / 2.0 if w > 1 else 0.5
            ry = (h - 1) / 2.0 if h > 1 else 0.5
            for y in range(h):
                for x in range(w):
                    if rx <= 0 or ry <= 0:
                        inside = True
                    else:
                        nx = (x - cx) / rx
                        ny = (y - cy) / ry
                        inside = (nx * nx + ny * ny) <= 1.0 + 1e-6
                    self._grid[y][x] = 1 if inside else 0
            return

    def _on_canvas_click(self, event: tk.Event) -> None:
        cell = 48
        x = int(event.x // cell)
        y = int(event.y // cell)
        w, h = self.w_var.get(), self.h_var.get()
        if 0 <= x < w and 0 <= y < h:
            self._grid[y][x] = 0 if self._grid[y][x] else 1
            self.shape_var.set("Personalizado")
            self.shape_opt.set("Personalizado")
            self._redraw()

    def _redraw(self) -> None:
        self.canvas.delete("all")
        cell = 48
        w, h = self.w_var.get(), self.h_var.get()

        for y in range(8):
            for x in range(8):
                x0, y0 = x * cell, y * cell
                fill = "#1A1A1A"
                outline = "#2A2A2A"
                if x < w and y < h:
                    fill = "#2B6CB0" if self._grid[y][x] else "#111111"
                    outline = "#3A3A3A"
                self.canvas.create_rectangle(x0, y0, x0 + cell, y0 + cell, fill=fill, outline=outline, width=2)

        self.canvas.create_rectangle(0, 0, w * cell, h * cell, outline="#FFFFFF", width=2)

    def _to_brush(self) -> Brush:
        w, h = self.w_var.get(), self.h_var.get()
        rows: List[int] = []
        for y in range(h):
            r = 0
            for x in range(w):
                if self._grid[y][x]:
                    r |= 1 << (w - 1 - x)
            rows.append(r)
        br = Brush(id=None, name="(sem nome)", width=w, height=h, rows=rows)
        br.validate()
        return br

    def _cancel(self) -> None:
        self._result = None
        self.destroy()

    def _ok(self) -> None:
        try:
            self._result = self._to_brush()
        except Exception as e:
            messagebox.showerror("Erro", f"Pincel inválido: {e}")
            return
        self.destroy()


# ----------------------------
# UI
# ----------------------------
class SpriteEditorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("pyEdSprite - MSX1 Sprite Editor (MVP)")
        self.geometry("1280x820")
        self.minsize(1100, 740)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.db = SpriteDB("sprites.db")

        self.sprite_size = 8  # 8 or 16
        self.sprites: List[Sprite] = []
        self.selected_sprite_index: int = 0

        self.edit_mode = tk.StringVar(value="single")  # single | 2x2 | overlay
        self.overlay_active = tk.IntVar(value=0)  # which of the 4 sprites is edited in overlay (0..3)

        self.current_color_index: int = 15  # default white

        self.mirror_h_var = tk.BooleanVar(value=False)
        self.mirror_v_var = tk.BooleanVar(value=False)
        self.mirror_d1_var = tk.BooleanVar(value=False)  # y = x
        self.mirror_d2_var = tk.BooleanVar(value=False)  # y = w-1-x

        # ============================
        # Dirty tracking
        # ============================
        self.last_loaded_project_id: Optional[int] = None
        self.last_loaded_project_name: Optional[str] = None
        self._baseline_signature: Optional[int] = None

        # ============================
        # Ferramentas
        # ============================
        self.tool_mode: str = "pencil"

        self.eraser_shape = tk.StringVar(value="Quadrado")  # Quadrado | Redondo
        self.eraser_size = tk.IntVar(value=4)  # 1..4

        self._shape_start: Optional[Tuple[int, int]] = None
        self._shape_current: Optional[Tuple[int, int]] = None
        self._shape_value: int = 1

        self._is_painting: bool = False
        self._paint_value: int = 1
        self._last_paint_xy: Optional[Tuple[int, int]] = None

        # ============================
        # Deslocamento + buffers + undo
        # ============================
        self.shift_mode = tk.StringVar(value="wrap")
        self._shift_buffers: Dict[int, Dict[str, List[int]]] = {}
        self._undo_snapshot: Dict[int, Dict[str, Any]] = {}

        # ============================
        # Pincéis
        # ============================
        self.brushes: List[Brush] = []
        self.active_brush: Brush = Brush(id=None, name="1x1 (pixel)", width=1, height=1, rows=[0b1])

        self._build_layout()
        self._load_brushes()
        self._reset_project(size=8)

        self.protocol("WM_DELETE_WINDOW", self._request_exit)

    # ----------------------------
    # UI feedback (pressionado/solto) para botões de ação
    # ----------------------------
    def _flash_button_pressed(self, btn: ctk.CTkButton, *, ms: int = 140) -> None:
        try:
            orig_fg = btn.cget("fg_color")
            orig_hover = btn.cget("hover_color")
        except Exception:
            return

        pressed = "#2B6CB0"
        btn.configure(fg_color=pressed, hover_color=pressed)

        def restore() -> None:
            try:
                btn.configure(fg_color=orig_fg, hover_color=orig_hover)
            except Exception:
                pass

        self.after(int(ms), restore)

    def _run_action_button(self, btn: ctk.CTkButton, fn) -> None:
        self._flash_button_pressed(btn)
        fn()

    # ----------------------------
    # Brushes
    # ----------------------------
    def _load_brushes(self) -> None:
        try:
            self.brushes = self.db.list_brushes()
        except Exception as e:
            self.brushes = []
            self.status_label.configure(text=f"Falha ao carregar pincéis: {e}")
            return

        names = [b.name for b in self.brushes] if self.brushes else ["1x1 (pixel)"]
        self.brush_menu.configure(values=names)

        current_name = self.active_brush.name
        pick = current_name if current_name in names else names[0]
        self.brush_menu.set(pick)
        self._on_brush_selected(pick)

    def _on_brush_selected(self, name: str) -> None:
        for b in self.brushes:
            if b.name == name:
                self.active_brush = b
                self.status_label.configure(text=f"Pincel selecionado: {b.name} ({b.width}x{b.height})")
                return
        self.active_brush = Brush(id=None, name="1x1 (pixel)", width=1, height=1, rows=[0b1])

    def _open_brush_editor(self) -> None:
        dlg = BrushEditorDialog(self, initial=self.active_brush)
        self.wait_window(dlg)
        br = dlg.result()
        if br is None:
            return

        self.active_brush = br
        temp_name = f"Temp {br.width}x{br.height}"
        self.brush_menu.set(temp_name)
        self.status_label.configure(text=f"Pincel editado (não salvo): {br.width}x{br.height}")

    def _save_active_brush(self) -> None:
        br = self.active_brush
        try:
            br.validate()
        except Exception as e:
            messagebox.showerror("Erro", f"Pincel inválido: {e}")
            return

        name = simpledialog.askstring("Salvar pincel", "Nome do pincel:", initialvalue=br.name if br.name else "")
        if not name:
            return

        try:
            bid = self.db.save_brush(name=name, width=br.width, height=br.height, rows=br.rows, user_defined=True)
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Já existe um pincel com esse nome.")
            return
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar pincel: {e}")
            return

        self._load_brushes()
        self.brush_menu.set(name)
        self._on_brush_selected(name)
        self.status_label.configure(text=f"Pincel salvo: {name} (id={bid})")

    # ----------------------------
    # Borracha (helpers)
    # ----------------------------
    def _get_eraser_brush(self) -> Brush:
        size = int(self.eraser_size.get())
        size = max(1, min(4, size))
        shape = str(self.eraser_shape.get())

        if shape == "Redondo":
            return Brush.round(name=f"Borracha redonda {size}x{size}", diameter=size)
        return Brush.square(name=f"Borracha quadrada {size}x{size}", size=size)

    def _set_tool_eraser(self) -> None:
        self.tool_mode = "eraser"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Borracha (clique e arraste). Não altera a cor do sprite.")

    def _on_eraser_shape_changed(self, v: str) -> None:
        self.eraser_shape.set(v)
        if self.tool_mode == "eraser":
            s = int(self.eraser_size.get())
            self.status_label.configure(text=f"Borracha: {self.eraser_shape.get()} {s}x{s}")

    def _on_eraser_size_changed(self, v: str) -> None:
        try:
            self.eraser_size.set(int(v))
        except Exception:
            self.eraser_size.set(4)
        if self.tool_mode == "eraser":
            s = int(self.eraser_size.get())
            self.status_label.configure(text=f"Borracha: {self.eraser_shape.get()} {s}x{s}")

    # ----------------------------
    # Fill tool (balde / flood fill)
    # ----------------------------
    def _set_tool_fill(self) -> None:
        self.tool_mode = "fill"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Preencher área (balde). Clique para preencher a região conectada.")

    def _get_pixel_in_mode(self, x: int, y: int) -> int:
        mode = self._get_edit_mode()
        if mode == "single":
            sp = self.sprites[self.selected_sprite_index]
            return sp.get_pixel(x, y)

        if mode == "overlay":
            block = self._get_2x2_indices()
            if not block:
                sp = self.sprites[self.selected_sprite_index]
                return sp.get_pixel(x, y)
            active = int(self.overlay_active.get())
            active = max(0, min(3, active))
            sp = self.sprites[block[active]]
            return sp.get_pixel(x, y)

        block = self._get_2x2_indices()
        if not block:
            sp = self.sprites[self.selected_sprite_index]
            return sp.get_pixel(x, y)

        sp_col = 0 if x < self.sprite_size else 1
        sp_row = 0 if y < self.sprite_size else 1
        local_x = x if sp_col == 0 else (x - self.sprite_size)
        local_y = y if sp_row == 0 else (y - self.sprite_size)
        sp_idx = block[sp_row * 2 + sp_col]
        sp = self.sprites[sp_idx]
        return sp.get_pixel(local_x, local_y)

    def _flood_fill_from(self, start_x: int, start_y: int, new_value: int) -> int:
        w, h = self._editor_dims()
        if not (0 <= start_x < w and 0 <= start_y < h):
            return 0

        target = int(self._get_pixel_in_mode(start_x, start_y))
        new_value = 1 if int(new_value) else 0
        if target == new_value:
            return 0

        q: deque[Tuple[int, int]] = deque()
        q.append((start_x, start_y))
        visited = set()
        changed = 0

        while q:
            x, y = q.popleft()
            if (x, y) in visited:
                continue
            visited.add((x, y))

            if self._get_pixel_in_mode(x, y) != target:
                continue

            if new_value == 1:
                self._draw_mirrored_point(x, y, 1, set_color=True)
            else:
                self._draw_mirrored_point(x, y, 0, set_color=False)

            changed += 1

            if x > 0:
                q.append((x - 1, y))
            if x < w - 1:
                q.append((x + 1, y))
            if y > 0:
                q.append((x, y - 1))
            if y < h - 1:
                q.append((x, y + 1))

        return changed

    # ----------------------------
    # Dirty tracking
    # ----------------------------
    def _compute_signature(self) -> int:
        parts: List[int] = [int(self.sprite_size), len(self.sprites)]
        for sp in self.sprites:
            parts.append(int(sp.color_index))
            parts.extend(int(r) for r in sp.rows)
        return hash(tuple(parts))

    def _mark_baseline(self) -> None:
        self._baseline_signature = self._compute_signature()

    def _has_unsaved_changes_for_last_loaded(self) -> bool:
        if self.last_loaded_project_id is None:
            return False
        if self._baseline_signature is None:
            return False
        return self._compute_signature() != self._baseline_signature

    def _touch_change(self) -> None:
        if self.last_loaded_project_id is None:
            return

    # ----------------------------
    # UI layout
    # ----------------------------
    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top.grid_columnconfigure(0, weight=1)

        top_row1 = ctk.CTkFrame(top)
        top_row1.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top_row1.grid_columnconfigure(0, weight=1)

        left1 = ctk.CTkFrame(top_row1)
        left1.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left1, text="Projeto:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        ctk.CTkButton(left1, text="Novo", width=90, command=self._new_project).grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkButton(left1, text="Salvar (SQLite)", width=140, command=self._save_project).grid(row=0, column=2, padx=6, pady=6)
        ctk.CTkButton(left1, text="Carregar (SQLite)", width=150, command=self._open_load_dialog).grid(row=0, column=3, padx=6, pady=6)

        right1 = ctk.CTkFrame(top_row1)
        right1.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(
            right1, text="Sair", width=90, fg_color="#8B2C2C", hover_color="#A63A3A", command=self._request_exit
        ).grid(row=0, column=0, padx=6, pady=6)

        top_row2 = ctk.CTkFrame(top)
        top_row2.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        top_row2.grid_columnconfigure(0, weight=1)

        left2 = ctk.CTkFrame(top_row2)
        left2.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(left2, text="Tamanho:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.size_seg = ctk.CTkSegmentedButton(left2, values=["8x8", "16x16"], command=self._on_size_changed, width=180)
        self.size_seg.set("8x8")
        self.size_seg.grid(row=0, column=1, padx=(0, 14), pady=6, sticky="w")

        ctk.CTkLabel(left2, text="Modo:").grid(row=0, column=2, padx=(0, 8), pady=6, sticky="w")
        self.mode_seg = ctk.CTkSegmentedButton(left2, values=["single", "2x2", "overlay"], command=lambda _v: self._redraw_all(), width=260)
        self.mode_seg.set("single")
        self.mode_seg.grid(row=0, column=3, padx=(0, 14), pady=6, sticky="w")

        overlay_frame = ctk.CTkFrame(left2)
        overlay_frame.grid(row=0, column=4, padx=(0, 6), pady=6, sticky="w")
        ctk.CTkLabel(overlay_frame, text="Overlay:").grid(row=0, column=0, padx=(8, 6), pady=6)
        for i in range(4):
            rb = ctk.CTkRadioButton(
                overlay_frame, text=str(i + 1), variable=self.overlay_active, value=i, command=self._redraw_all
            )
            rb.grid(row=0, column=1 + i, padx=4, pady=6)

        self.overlay_hint_label = ctk.CTkLabel(top_row2, text="")
        self.overlay_hint_label.grid(row=0, column=1, sticky="e", padx=8, pady=6)

        main = ctk.CTkFrame(self)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(main)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 10), pady=10)
        left.grid_rowconfigure(1, weight=1)

        self.table_label = ctk.CTkLabel(left, text="Sprites (MSX1)")
        self.table_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        self.scroll = ctk.CTkScrollableFrame(left, width=420, height=650)
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        right = ctk.CTkFrame(main)
        right.grid(row=0, column=1, sticky="nsew", pady=10)
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=0)
        right.grid_columnconfigure(0, weight=1)

        editor_frame = ctk.CTkFrame(right)
        editor_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 8))
        editor_frame.grid_rowconfigure(0, weight=1)
        editor_frame.grid_columnconfigure(0, weight=1)

        self.editor_canvas = tk.Canvas(editor_frame, bg="#111111", highlightthickness=0)
        self.editor_canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.editor_canvas.bind("<ButtonPress-1>", lambda e: self._on_editor_press(e, value=1))
        self.editor_canvas.bind("<B1-Motion>", self._on_editor_drag)
        self.editor_canvas.bind("<ButtonRelease-1>", self._on_editor_release)

        self.editor_canvas.bind("<ButtonPress-3>", lambda e: self._on_editor_press(e, value=0))
        self.editor_canvas.bind("<B3-Motion>", self._on_editor_drag)
        self.editor_canvas.bind("<ButtonRelease-3>", self._on_editor_release)

        self.editor_canvas.bind("<Motion>", self._on_editor_motion)
        self.editor_canvas.bind("<Leave>", lambda _e: self._clear_tool_preview())

        bottom = ctk.CTkFrame(right)
        bottom.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom.grid_columnconfigure(0, weight=3)
        bottom.grid_columnconfigure(1, weight=2)

        tools = ctk.CTkFrame(bottom)
        tools.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        for c in range(8):
            tools.grid_columnconfigure(c, weight=1)

        ctk.CTkLabel(tools, text="Ferramentas (edição):").grid(
            row=0, column=0, columnspan=8, sticky="w", padx=8, pady=(8, 4)
        )

        btn_w = 52
        btn_h = 34

        self.btn_tool_pencil = ctk.CTkButton(tools, text="✎", width=btn_w, height=btn_h, command=self._set_tool_pencil)
        self.btn_tool_pencil.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

        self.btn_tool_eraser = ctk.CTkButton(tools, text="⌫", width=btn_w, height=btn_h, command=self._set_tool_eraser)
        self.btn_tool_eraser.grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        self.btn_tool_fill = ctk.CTkButton(tools, text="FILL", width=btn_w, height=btn_h, command=self._set_tool_fill)
        self.btn_tool_fill.grid(row=1, column=2, padx=4, pady=4, sticky="ew")

        self.btn_tool_line = ctk.CTkButton(tools, text="／", width=btn_w, height=btn_h, command=self._set_tool_line)
        self.btn_tool_line.grid(row=1, column=3, padx=4, pady=4, sticky="ew")

        self.btn_tool_rect = ctk.CTkButton(tools, text="▭", width=btn_w, height=btn_h, command=self._set_tool_rect)
        self.btn_tool_rect.grid(row=1, column=4, padx=4, pady=4, sticky="ew")

        self.btn_tool_rect_fill = ctk.CTkButton(tools, text="▮", width=btn_w, height=btn_h, command=self._set_tool_rect_fill)
        self.btn_tool_rect_fill.grid(row=1, column=5, padx=4, pady=4, sticky="ew")

        self.btn_tool_ellipse = ctk.CTkButton(tools, text="◯", width=btn_w, height=btn_h, command=self._set_tool_ellipse)
        self.btn_tool_ellipse.grid(row=1, column=6, padx=4, pady=4, sticky="ew")

        self.btn_tool_ellipse_fill = ctk.CTkButton(tools, text="⬤", width=btn_w, height=btn_h, command=self._set_tool_ellipse_fill)
        self.btn_tool_ellipse_fill.grid(row=1, column=7, padx=4, pady=4, sticky="ew")

        ctk.CTkLabel(tools, text="Pincel:").grid(row=2, column=0, padx=8, pady=(8, 4), sticky="w")
        self.brush_menu = ctk.CTkOptionMenu(tools, values=["1x1 (pixel)"], command=self._on_brush_selected)
        self.brush_menu.grid(row=2, column=1, columnspan=3, padx=4, pady=(8, 4), sticky="ew")

        ctk.CTkButton(tools, text="Editar", width=90, command=self._open_brush_editor).grid(row=2, column=4, padx=4, pady=(8, 4), sticky="ew")
        ctk.CTkButton(tools, text="Salvar", width=90, command=self._save_active_brush).grid(row=2, column=5, padx=4, pady=(8, 4), sticky="ew")

        ctk.CTkLabel(tools, text="Borracha:").grid(row=2, column=6, padx=8, pady=(8, 4), sticky="e")
        er_box = ctk.CTkFrame(tools)
        er_box.grid(row=2, column=7, padx=4, pady=(8, 4), sticky="ew")
        er_box.grid_columnconfigure(0, weight=1)
        er_box.grid_columnconfigure(1, weight=1)

        self.eraser_shape_menu = ctk.CTkOptionMenu(er_box, values=["Quadrado", "Redondo"], command=self._on_eraser_shape_changed, width=110)
        self.eraser_shape_menu.grid(row=0, column=0, padx=4, pady=6, sticky="ew")
        self.eraser_shape_menu.set(self.eraser_shape.get())

        self.eraser_size_menu = ctk.CTkOptionMenu(er_box, values=["1", "2", "3", "4"], command=self._on_eraser_size_changed, width=70)
        self.eraser_size_menu.grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        self.eraser_size_menu.set(str(self.eraser_size.get()))

        shift = ctk.CTkFrame(tools)
        shift.grid(row=3, column=0, columnspan=8, sticky="ew", padx=8, pady=(8, 8))
        for c in range(12):
            shift.grid_columnconfigure(c, weight=0)
        shift.grid_columnconfigure(11, weight=1)

        ctk.CTkLabel(shift, text="Deslocar:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.shift_mode_seg = ctk.CTkSegmentedButton(shift, values=["wrap", "buffer"], command=self._on_shift_mode_changed, width=170)
        self.shift_mode_seg.set("wrap")
        self.shift_mode_seg.grid(row=0, column=1, padx=(0, 10), pady=6, sticky="w")

        self.btn_shift_up = ctk.CTkButton(shift, text="↑", width=36, height=btn_h, command=lambda: self._shift("up"))
        self.btn_shift_up.grid(row=0, column=2, padx=3, pady=6)

        self.btn_shift_left = ctk.CTkButton(shift, text="←", width=36, height=btn_h, command=lambda: self._shift("left"))
        self.btn_shift_left.grid(row=0, column=3, padx=3, pady=6)

        self.btn_shift_right = ctk.CTkButton(shift, text="→", width=36, height=btn_h, command=lambda: self._shift("right"))
        self.btn_shift_right.grid(row=0, column=4, padx=3, pady=6)

        self.btn_shift_down = ctk.CTkButton(shift, text="↓", width=36, height=btn_h, command=lambda: self._shift("down"))
        self.btn_shift_down.grid(row=0, column=5, padx=3, pady=6)

        self.btn_undo = ctk.CTkButton(shift, text="Desfazer", width=120, command=self._undo)
        self.btn_undo.grid(row=0, column=6, padx=(10, 0), pady=6)

        # Ações rápidas (padrão + pressionado/solto)
        actions = ctk.CTkFrame(tools)
        actions.grid(row=4, column=0, columnspan=8, sticky="ew", padx=8, pady=(0, 8))
        for c in range(12):
            actions.grid_columnconfigure(c, weight=0)
        actions.grid_columnconfigure(11, weight=1)

        ctk.CTkLabel(actions, text="Ações:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")

        self.btn_action_flip_h = ctk.CTkButton(actions, text="⇅", width=btn_w, height=btn_h)
        self.btn_action_flip_h.grid(row=0, column=1, padx=3, pady=6)
        self.btn_action_flip_h.configure(command=lambda: self._run_action_button(self.btn_action_flip_h, self._action_flip_h))

        self.btn_action_flip_v = ctk.CTkButton(actions, text="⇆", width=btn_w, height=btn_h)
        self.btn_action_flip_v.grid(row=0, column=2, padx=3, pady=6)
        self.btn_action_flip_v.configure(command=lambda: self._run_action_button(self.btn_action_flip_v, self._action_flip_v))

        self.btn_action_invert = ctk.CTkButton(actions, text="INV", width=btn_w, height=btn_h)
        self.btn_action_invert.grid(row=0, column=3, padx=(12, 3), pady=6)
        self.btn_action_invert.configure(command=lambda: self._run_action_button(self.btn_action_invert, self._action_invert_pixels))

        self.btn_action_clear = ctk.CTkButton(actions, text="CLR", width=btn_w, height=btn_h)
        self.btn_action_clear.grid(row=0, column=4, padx=3, pady=6)
        self.btn_action_clear.configure(command=lambda: self._run_action_button(self.btn_action_clear, self._action_clear_sprite))

        self.btn_action_fill = ctk.CTkButton(actions, text="ALL", width=btn_w, height=btn_h)
        self.btn_action_fill.grid(row=0, column=5, padx=3, pady=6)
        self.btn_action_fill.configure(command=lambda: self._run_action_button(self.btn_action_fill, self._action_fill_sprite))

        self.btn_action_flip_h.bind("<Enter>", lambda _e: self.status_label.configure(text="Espelhar H (cima/baixo)"))
        self.btn_action_flip_v.bind("<Enter>", lambda _e: self.status_label.configure(text="Espelhar V (esquerda/direita)"))
        self.btn_action_invert.bind("<Enter>", lambda _e: self.status_label.configure(text="Inverter pixels (0↔1)"))
        self.btn_action_clear.bind("<Enter>", lambda _e: self.status_label.configure(text="Limpar sprite (tudo 0)"))
        self.btn_action_fill.bind("<Enter>", lambda _e: self.status_label.configure(text="Preencher sprite (tudo 1) com a cor atual"))

        mirror_frame = ctk.CTkFrame(tools)
        mirror_frame.grid(row=5, column=0, columnspan=8, sticky="ew", padx=8, pady=(4, 8))

        ctk.CTkLabel(mirror_frame, text="Espelhar:").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.btn_mirror_h = ctk.CTkCheckBox(mirror_frame, text="Horizontal (—)", variable=self.mirror_h_var, command=self._on_mirror_changed)
        self.btn_mirror_h.grid(row=0, column=1, padx=6, pady=6)
        self.btn_mirror_v = ctk.CTkCheckBox(mirror_frame, text="Vertical (|)", variable=self.mirror_v_var, command=self._on_mirror_changed)
        self.btn_mirror_v.grid(row=0, column=2, padx=6, pady=6)
        self.btn_mirror_d1 = ctk.CTkCheckBox(mirror_frame, text="Diag (\\)", variable=self.mirror_d1_var, command=self._on_mirror_changed)
        self.btn_mirror_d1.grid(row=0, column=3, padx=6, pady=6)
        self.btn_mirror_d2 = ctk.CTkCheckBox(mirror_frame, text="Diag (/)", variable=self.mirror_d2_var, command=self._on_mirror_changed)
        self.btn_mirror_d2.grid(row=0, column=4, padx=6, pady=6)

        self._tool_btn_default_fg = self.btn_tool_pencil.cget("fg_color")
        self._tool_btn_default_hover = self.btn_tool_pencil.cget("hover_color")

        right_panel = ctk.CTkFrame(bottom)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
        right_panel.grid_rowconfigure(0, weight=0)
        right_panel.grid_rowconfigure(1, weight=0)
        right_panel.grid_rowconfigure(2, weight=0)
        right_panel.grid_columnconfigure(0, weight=1)

        palette_box = ctk.CTkFrame(right_panel)
        palette_box.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        palette_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(palette_box, text="Paleta MSX1 (1 cor por sprite):").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.palette_frame = ctk.CTkFrame(palette_box)
        self.palette_frame.grid(row=1, column=0, sticky="ew")
        self._build_palette()

        preview_box = ctk.CTkFrame(right_panel)
        preview_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        preview_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(preview_box, text="Preview (2x):").grid(row=0, column=0, sticky="w", pady=(8, 6))
        self.preview_canvas = tk.Canvas(preview_box, width=220, height=220, bg="#111111", highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="w", padx=0, pady=(0, 10))

        status_box = ctk.CTkFrame(right_panel)
        status_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        status_box.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(status_box, text="Pronto.")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=8, pady=10)

        self._update_tool_buttons()

    # ----------------------------
    # Palette
    # ----------------------------
    def _build_palette(self) -> None:
        for w in self.palette_frame.winfo_children():
            w.destroy()

        cols = 8
        for i, hex_color in enumerate(MSX1_PALETTE_HEX):
            r = i // cols
            c = i % cols
            btn = ctk.CTkButton(
                self.palette_frame,
                text=f"{i:02d}",
                width=52,
                height=30,
                fg_color=hex_color,
                text_color="#000000" if i in (11, 14, 15) else "#FFFFFF",
                command=lambda idx=i: self._set_color(idx),
            )
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")

        for c in range(cols):
            self.palette_frame.grid_columnconfigure(c, weight=1)

    def _set_color(self, idx: int) -> None:
        self.current_color_index = idx
        for sp_idx in self._get_target_sprite_indices_for_color():
            self.sprites[sp_idx].color_index = idx
        self._touch_change()
        self.status_label.configure(text=f"Cor selecionada: {idx} ({MSX1_PALETTE_HEX[idx]})")
        self._redraw_all()

    # ============================
    # Ferramentas
    # ============================
    def _reset_shape_state(self) -> None:
        self._shape_start = None
        self._shape_current = None
        self._shape_value = 1
        self._clear_tool_preview()

    def _set_tool_pencil(self) -> None:
        self.tool_mode = "pencil"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Pincel (clique e arraste). Botão direito apaga.")

    def _set_tool_line(self) -> None:
        self.tool_mode = "line"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Reta (clique início, mova, clique fim). Botão direito apaga.")

    def _set_tool_rect(self) -> None:
        self.tool_mode = "rect"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Retângulo (contorno). Clique início, mova, clique fim.")

    def _set_tool_rect_fill(self) -> None:
        self.tool_mode = "rect_fill"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Retângulo preenchido. Clique início, mova, clique fim.")

    def _set_tool_ellipse(self) -> None:
        self.tool_mode = "ellipse"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Elipse/Círculo (contorno). Clique início, mova, clique fim.")

    def _set_tool_ellipse_fill(self) -> None:
        self.tool_mode = "ellipse_fill"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()
        self.status_label.configure(text="Ferramenta: Elipse/Círculo preenchido. Clique início, mova, clique fim.")

    def _update_tool_buttons(self) -> None:
        active = "#2B6CB0"
        default_fg = getattr(self, "_tool_btn_default_fg", "transparent")
        default_hover = getattr(self, "_tool_btn_default_hover", None)

        def set_btn(btn: ctk.CTkButton, is_active: bool) -> None:
            if is_active:
                btn.configure(fg_color=active)
            else:
                btn.configure(fg_color=default_fg, hover_color=default_hover)

        set_btn(self.btn_tool_pencil, self.tool_mode == "pencil")
        set_btn(self.btn_tool_eraser, self.tool_mode == "eraser")
        set_btn(self.btn_tool_fill, self.tool_mode == "fill")
        set_btn(self.btn_tool_line, self.tool_mode == "line")
        set_btn(self.btn_tool_rect, self.tool_mode == "rect")
        set_btn(self.btn_tool_rect_fill, self.tool_mode == "rect_fill")
        set_btn(self.btn_tool_ellipse, self.tool_mode == "ellipse")
        set_btn(self.btn_tool_ellipse_fill, self.tool_mode == "ellipse_fill")

    def _on_shift_mode_changed(self, v: str) -> None:
        self.shift_mode.set(v)
        label = "Rotacionar (wrap)" if v == "wrap" else "Deslocar (buffer)"
        self.status_label.configure(text=f"Modo de deslocamento: {label}")

    def _on_mirror_changed(self) -> None:
        modes = []
        if self.mirror_h_var.get():
            modes.append("H")
        if self.mirror_v_var.get():
            modes.append("V")
        if self.mirror_d1_var.get():
            modes.append("Diag \\")
        if self.mirror_d2_var.get():
            modes.append("Diag /")

        if modes:
            self.status_label.configure(text=f"Espelhamento ativado: {', '.join(modes)}")
        else:
            self.status_label.configure(text="Espelhamento desativado.")
        self._redraw_editor()

    def _draw_mirror_guides(self) -> None:
        self.editor_canvas.delete("mirror_guides")
        w, h = self._editor_dims()
        if w == 0 or h == 0:
            return

        scale = EDITOR_SCALE
        w_px, h_px = w * scale, h * scale
        color = "#FFEB3B"

        if self.mirror_h_var.get():
            mx = w_px / 2
            self.editor_canvas.create_line(mx, 0, mx, h_px, fill=color, width=1, dash=(4, 4), tags="mirror_guides")

        if self.mirror_v_var.get():
            my = h_px / 2
            self.editor_canvas.create_line(0, my, w_px, my, fill=color, width=1, dash=(4, 4), tags="mirror_guides")

        if self.mirror_d1_var.get():
            self.editor_canvas.create_line(0, 0, w_px, h_px, fill=color, width=1, dash=(4, 4), tags="mirror_guides")

        if self.mirror_d2_var.get():
            self.editor_canvas.create_line(w_px, 0, 0, h_px, fill=color, width=1, dash=(4, 4), tags="mirror_guides")

    def _draw_mirrored_point(self, x: int, y: int, value: int, *, set_color: bool = True) -> None:
        w, h = self._editor_dims()
        points = {(x, y)}

        if self.mirror_h_var.get():
            points.update([(w - 1 - px, py) for px, py in list(points)])
        if self.mirror_v_var.get():
            points.update([(px, h - 1 - py) for px, py in list(points)])
        if self.mirror_d1_var.get():
            points.update([(py, px) for px, py in list(points)])
        if self.mirror_d2_var.get():
            points.update([(h - 1 - py, w - 1 - px) for px, py in list(points)])

        for px, py in points:
            if 0 <= px < w and 0 <= py < h:
                self._apply_point_in_mode(px, py, value, set_color=set_color)

    # ============================
    # Transformações / ações
    # ============================
    def _get_target_sprite_indices_for_transform(self) -> List[int]:
        mode = self._get_edit_mode()
        if mode == "single":
            return [self.selected_sprite_index]

        if mode == "overlay":
            block = self._get_2x2_indices()
            if not block:
                return [self.selected_sprite_index]
            active = int(self.overlay_active.get())
            active = max(0, min(3, active))
            return [block[active]]

        block = self._get_2x2_indices()
        return block if block else [self.selected_sprite_index]

    def _apply_pixel_transform_in_editor_space(self, kind: str) -> bool:
        if self._get_edit_mode() == "2x2" and not self._get_2x2_indices():
            self.status_label.configure(text="2x2 indisponível na borda da grade. Selecione outro sprite.")
            return False

        w, h = self._editor_dims()
        src = [[int(self._get_pixel_in_mode(x, y)) for x in range(w)] for y in range(h)]

        def dst_value(x: int, y: int) -> int:
            if kind == "clear":
                return 0
            if kind == "fill":
                return 1
            if kind == "invert":
                return 0 if src[y][x] else 1

            # flip_h = espelhar HORIZONTAL (linha horizontal): inverte cima/baixo
            if kind == "flip_h":
                return src[h - 1 - y][x]
            # flip_v = espelhar VERTICAL (linha vertical): inverte esquerda/direita
            if kind == "flip_v":
                return src[y][w - 1 - x]

            raise ValueError("kind inválido")

        set_color = True if kind == "fill" else False
        for yy in range(h):
            for xx in range(w):
                self._apply_point_in_mode(xx, yy, dst_value(xx, yy), set_color=set_color)

        return True

    def _action_flip_h(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return
        self._push_undo_for_indices(indices)
        if self._apply_pixel_transform_in_editor_space("flip_h"):
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text="Espelhamento aplicado: horizontal (cima/baixo).")

    def _action_flip_v(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return
        self._push_undo_for_indices(indices)
        if self._apply_pixel_transform_in_editor_space("flip_v"):
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text="Espelhamento aplicado: vertical (esquerda/direita).")

    def _action_invert_pixels(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return
        self._push_undo_for_indices(indices)
        if self._apply_pixel_transform_in_editor_space("invert"):
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text="Pixels invertidos (0↔1).")

    def _action_clear_sprite(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return
        self._push_undo_for_indices(indices)
        if self._apply_pixel_transform_in_editor_space("clear"):
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text="Sprite limpo (tudo 0).")

    def _action_fill_sprite(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return
        self._push_undo_for_indices(indices)
        if self._apply_pixel_transform_in_editor_space("fill"):
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text=f"Sprite preenchido (tudo 1) com a cor atual ({self.current_color_index}).")

    # ----------------------------
    # Shift buffers + undo
    # ----------------------------
    def _ensure_buffers(self, sp_idx: int) -> Dict[str, List[int]]:
        buf = self._shift_buffers.get(sp_idx)
        if buf is None:
            buf = {"left": [], "right": [], "up": [], "down": []}
            self._shift_buffers[sp_idx] = buf
        return buf

    def _push_undo_for_indices(self, indices: List[int]) -> None:
        for sp_idx in indices:
            sp = self.sprites[sp_idx]
            buf = self._ensure_buffers(sp_idx)
            self._undo_snapshot[sp_idx] = {
                "rows": list(sp.rows),
                "color_index": int(sp.color_index),
                "buffers": {k: list(v) for k, v in buf.items()},
            }

    def _undo(self) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        did = False
        for sp_idx in indices:
            snap = self._undo_snapshot.get(sp_idx)
            if not snap:
                continue
            sp = self.sprites[sp_idx]
            sp.rows = list(snap["rows"])
            sp.color_index = int(snap["color_index"])
            self._shift_buffers[sp_idx] = {k: list(v) for k, v in snap["buffers"].items()}
            did = True

        if did:
            self._reset_shape_state()
            self._touch_change()
            self._redraw_all()
            self.status_label.configure(text="Desfazer: sprite restaurado para o estado anterior.")
        else:
            self.status_label.configure(text="Nada para desfazer (apenas 1 nível).")

    @staticmethod
    def _mask_for_size(size: int) -> int:
        return (1 << size) - 1

    def _get_column_as_int(self, sp: Sprite, x: int) -> int:
        out = 0
        for y in range(sp.size):
            if sp.get_pixel(x, y):
                out |= 1 << (sp.size - 1 - y)
        return out

    def _set_column_from_int(self, sp: Sprite, x: int, col: int) -> None:
        for y in range(sp.size):
            bit = (col >> (sp.size - 1 - y)) & 1
            sp.set_pixel(x, y, int(bit))

    def _shift_wrap_sprite(self, sp: Sprite, direction: str) -> None:
        mask = self._mask_for_size(sp.size)

        if direction == "left":
            for y in range(sp.size):
                row = sp.rows[y] & mask
                msb = (row >> (sp.size - 1)) & 1
                sp.rows[y] = ((row << 1) & mask) | msb
            return

        if direction == "right":
            for y in range(sp.size):
                row = sp.rows[y] & mask
                lsb = row & 1
                sp.rows[y] = (row >> 1) | (lsb << (sp.size - 1))
            return

        if direction == "up":
            first = sp.rows[0]
            sp.rows = sp.rows[1:] + [first]
            return

        if direction == "down":
            last = sp.rows[-1]
            sp.rows = [last] + sp.rows[:-1]
            return

    def _shift_buffer_sprite(self, sp_idx: int, direction: str) -> None:
        sp = self.sprites[sp_idx]
        buf = self._ensure_buffers(sp_idx)
        size = sp.size
        mask = self._mask_for_size(size)
        max_keep = int(size)

        def push_stack(key: str, value: int) -> None:
            stack = buf[key]
            stack.append(int(value))
            if len(stack) > max_keep:
                stack[:] = stack[-max_keep:]

        def pop_stack(key: str) -> Optional[int]:
            stack = buf[key]
            if not stack:
                return None
            return int(stack.pop())

        if direction == "left":
            removed = self._get_column_as_int(sp, 0)
            push_stack("left", removed)
            for y in range(size):
                row = sp.rows[y] & mask
                sp.rows[y] = ((row << 1) & mask)
            restored = pop_stack("right")
            if restored is not None:
                self._set_column_from_int(sp, size - 1, restored)
            return

        if direction == "right":
            removed = self._get_column_as_int(sp, size - 1)
            push_stack("right", removed)
            for y in range(size):
                row = sp.rows[y] & mask
                sp.rows[y] = (row >> 1)
            restored = pop_stack("left")
            if restored is not None:
                self._set_column_from_int(sp, 0, restored)
            return

        if direction == "up":
            removed = sp.rows[0] & mask
            push_stack("up", removed)
            sp.rows = sp.rows[1:] + [0]
            restored = pop_stack("down")
            if restored is not None:
                sp.rows[-1] = restored & mask
            return

        if direction == "down":
            removed = sp.rows[-1] & mask
            push_stack("down", removed)
            sp.rows = [0] + sp.rows[:-1]
            restored = pop_stack("up")
            if restored is not None:
                sp.rows[0] = restored & mask
            return

    def _shift(self, direction: str) -> None:
        indices = self._get_target_sprite_indices_for_transform()
        if not indices:
            return

        self._push_undo_for_indices(indices)

        mode = self.shift_mode.get()
        if mode == "wrap":
            for sp_idx in indices:
                self._shift_wrap_sprite(self.sprites[sp_idx], direction)
        else:
            for sp_idx in indices:
                self._shift_buffer_sprite(sp_idx, direction)

        self._reset_shape_state()
        self._touch_change()
        self._redraw_all()

    # ============================
    # Raster / preview helpers
    # ============================
    def _editor_dims(self) -> Tuple[int, int]:
        mode = self._get_edit_mode()
        if mode == "2x2":
            return self.sprite_size * 2, self.sprite_size * 2
        return self.sprite_size, self.sprite_size

    def _event_to_editor_xy(self, event: tk.Event) -> Optional[Tuple[int, int]]:
        w, h = self._editor_dims()
        scale = EDITOR_SCALE
        cx = self.editor_canvas.canvasx(event.x)
        cy = self.editor_canvas.canvasy(event.y)
        x = int(cx // scale)
        y = int(cy // scale)
        if 0 <= x < w and 0 <= y < h:
            return x, y
        return None

    @staticmethod
    def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
        pts: List[Tuple[int, int]] = []
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy

        x, y = x0, y0
        while True:
            pts.append((x, y))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
        return pts

    @staticmethod
    def _rect_points(x0: int, y0: int, x1: int, y1: int, *, filled: bool) -> List[Tuple[int, int]]:
        x_min, x_max = (x0, x1) if x0 <= x1 else (x1, x0)
        y_min, y_max = (y0, y1) if y0 <= y1 else (y1, y0)
        pts: List[Tuple[int, int]] = []

        if filled:
            for yy in range(y_min, y_max + 1):
                for xx in range(x_min, x_max + 1):
                    pts.append((xx, yy))
            return pts

        for xx in range(x_min, x_max + 1):
            pts.append((xx, y_min))
            pts.append((xx, y_max))
        for yy in range(y_min + 1, y_max):
            pts.append((x_min, yy))
            pts.append((x_max, yy))
        return pts

    @staticmethod
    def _ellipse_points(x0: int, y0: int, x1: int, y1: int, *, filled: bool) -> List[Tuple[int, int]]:
        x_min, x_max = (x0, x1) if x0 <= x1 else (x1, x0)
        y_min, y_max = (y0, y1) if y0 <= y1 else (y1, y0)

        w = x_max - x_min + 1
        h = y_max - y_min + 1

        cx = x_min + (w - 1) / 2.0
        cy = y_min + (h - 1) / 2.0
        rx = (w - 1) / 2.0
        ry = (h - 1) / 2.0
        if rx <= 0:
            rx = 0.5
        if ry <= 0:
            ry = 0.5

        pts: List[Tuple[int, int]] = []
        inside_map: Dict[Tuple[int, int], bool] = {}

        for yy in range(y_min, y_max + 1):
            for xx in range(x_min, x_max + 1):
                px = xx + 0.5
                py = yy + 0.5
                nx = (px - (cx + 0.5)) / (rx + 0.000001)
                ny = (py - (cy + 0.5)) / (ry + 0.000001)
                inside = (nx * nx + ny * ny) <= 1.0 + 1e-9
                inside_map[(xx, yy)] = inside
                if filled and inside:
                    pts.append((xx, yy))

        if filled:
            return pts

        for yy in range(y_min, y_max + 1):
            for xx in range(x_min, x_max + 1):
                if not inside_map.get((xx, yy), False):
                    continue
                n_out = False
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    xxx, yyy = xx + dx, yy + dy
                    if xxx < x_min or xxx > x_max or yyy < y_min or yyy > y_max:
                        n_out = True
                        break
                    if not inside_map.get((xxx, yyy), False):
                        n_out = True
                        break
                if n_out:
                    pts.append((xx, yy))
        return pts

    def _apply_point_in_mode(self, x: int, y: int, value: int, *, set_color: bool = True) -> None:
        mode = self._get_edit_mode()
        if mode == "single":
            self._edit_single(self.selected_sprite_index, x, y, value, set_color=set_color)
        elif mode == "2x2":
            self._edit_2x2(x, y, value, set_color=set_color)
        elif mode == "overlay":
            self._edit_overlay(x, y, value, set_color=set_color)

    def _apply_brush_in_mode(self, x: int, y: int, value: int) -> None:
        w, h = self._editor_dims()
        pts = self.active_brush.points_centered()
        for dx, dy in pts:
            xx = x + dx
            yy = y + dy
            if 0 <= xx < w and 0 <= yy < h:
                self._draw_mirrored_point(xx, yy, value, set_color=True)

    def _apply_eraser_in_mode(self, x: int, y: int) -> None:
        w, h = self._editor_dims()
        er = self._get_eraser_brush()
        pts = er.points_centered()
        for dx, dy in pts:
            xx = x + dx
            yy = y + dy
            if 0 <= xx < w and 0 <= yy < h:
                self._draw_mirrored_point(xx, yy, 0, set_color=False)

    def _commit_tool_shape(self, start: Tuple[int, int], end: Tuple[int, int], value: int) -> None:
        w, h = self._editor_dims()

        def in_bounds(p: Tuple[int, int]) -> bool:
            return 0 <= p[0] < w and 0 <= p[1] < h

        if not in_bounds(start) or not in_bounds(end):
            return

        if self.tool_mode == "line":
            pts = self._bresenham_line(start[0], start[1], end[0], end[1])
        elif self.tool_mode == "rect":
            pts = self._rect_points(start[0], start[1], end[0], end[1], filled=False)
        elif self.tool_mode == "rect_fill":
            pts = self._rect_points(start[0], start[1], end[0], end[1], filled=True)
        elif self.tool_mode == "ellipse":
            pts = self._ellipse_points(start[0], start[1], end[0], end[1], filled=False)
        elif self.tool_mode == "ellipse_fill":
            pts = self._ellipse_points(start[0], start[1], end[0], end[1], filled=True)
        else:
            return

        for xx, yy in pts:
            if 0 <= xx < w and 0 <= yy < h:
                self._draw_mirrored_point(xx, yy, value, set_color=True)

    def _clear_tool_preview(self) -> None:
        self.editor_canvas.delete("tool_preview")

    def _draw_points_preview(self, pts: List[Tuple[int, int]]) -> None:
        self._clear_tool_preview()
        scale = EDITOR_SCALE
        for x, y in pts:
            x0 = x * scale
            y0 = y * scale
            self.editor_canvas.create_rectangle(
                x0 + 2, y0 + 2, x0 + scale - 2, y0 + scale - 2,
                outline="#FFFFFF",
                width=2,
                tags=("tool_preview",),
            )

    def _draw_tool_preview(self, start: Tuple[int, int], end: Tuple[int, int]) -> None:
        w, h = self._editor_dims()
        if not (0 <= start[0] < w and 0 <= start[1] < h and 0 <= end[0] < w and 0 <= end[1] < h):
            self._clear_tool_preview()
            return

        if self.tool_mode == "line":
            pts = self._bresenham_line(start[0], start[1], end[0], end[1])
        elif self.tool_mode == "rect":
            pts = self._rect_points(start[0], start[1], end[0], end[1], filled=False)
        elif self.tool_mode == "rect_fill":
            pts = self._rect_points(start[0], start[1], end[0], end[1], filled=True)
        elif self.tool_mode == "ellipse":
            pts = self._ellipse_points(start[0], start[1], end[0], end[1], filled=False)
        elif self.tool_mode == "ellipse_fill":
            pts = self._ellipse_points(start[0], start[1], end[0], end[1], filled=True)
        else:
            self._clear_tool_preview()
            return

        self._draw_points_preview(pts)

    # ============================
    # Pintura / eventos do editor
    # ============================
    def _on_editor_press(self, event: tk.Event, value: int) -> None:
        pos = self._event_to_editor_xy(event)
        if pos is None:
            return

        if self._get_edit_mode() == "2x2" and not self._get_2x2_indices():
            self.status_label.configure(text="2x2 indisponível na borda da grade. Selecione outro sprite.")
            return

        if self.tool_mode in ("line", "rect", "rect_fill", "ellipse", "ellipse_fill"):
            if self._shape_start is None:
                self._shape_start = pos
                self._shape_current = pos
                self._shape_value = value
                self._draw_tool_preview(self._shape_start, self._shape_current)
                return

            self._push_undo_for_indices(self._get_target_sprite_indices_for_transform())

            end = pos
            self._commit_tool_shape(self._shape_start, end, self._shape_value)
            self._shape_start = None
            self._shape_current = None
            self._clear_tool_preview()
            self._touch_change()
            self._redraw_all()
            return

        if self.tool_mode == "fill":
            self._push_undo_for_indices(self._get_target_sprite_indices_for_transform())
            x, y = pos
            changed = self._flood_fill_from(x, y, new_value=value)
            if changed > 0:
                self._touch_change()
                self._redraw_all()
                self.status_label.configure(text=f"Preenchimento: {changed} px alterados.")
            else:
                self.status_label.configure(text="Preenchimento: nada a fazer (região já está no valor desejado).")
            return

        if self.tool_mode == "pencil":
            self._push_undo_for_indices(self._get_target_sprite_indices_for_transform())
            self._is_painting = True
            self._paint_value = value
            self._last_paint_xy = pos
            x, y = pos
            self._apply_brush_in_mode(x, y, value)
            self._touch_change()
            self._redraw_all()
            return

        if self.tool_mode == "eraser":
            self._push_undo_for_indices(self._get_target_sprite_indices_for_transform())
            self._is_painting = True
            self._paint_value = 0
            self._last_paint_xy = pos
            x, y = pos
            self._apply_eraser_in_mode(x, y)
            self._touch_change()
            self._redraw_all()
            return

    def _on_editor_drag(self, event: tk.Event) -> None:
        if self.tool_mode not in ("pencil", "eraser"):
            return
        if not self._is_painting:
            return

        pos = self._event_to_editor_xy(event)
        if pos is None:
            return
        if pos == self._last_paint_xy:
            return

        if self._last_paint_xy is not None:
            x0, y0 = self._last_paint_xy
            x1, y1 = pos
            for x, y in self._bresenham_line(x0, y0, x1, y1):
                if self.tool_mode == "eraser":
                    self._apply_eraser_in_mode(x, y)
                else:
                    self._apply_brush_in_mode(x, y, self._paint_value)
        else:
            x, y = pos
            if self.tool_mode == "eraser":
                self._apply_eraser_in_mode(x, y)
            else:
                self._apply_brush_in_mode(x, y, self._paint_value)

        self._last_paint_xy = pos
        self._touch_change()
        self._redraw_all()

    def _on_editor_release(self, _event: tk.Event) -> None:
        if self.tool_mode in ("pencil", "eraser"):
            self._is_painting = False
            self._last_paint_xy = None

    def _on_editor_motion(self, event: tk.Event) -> None:
        if self.tool_mode not in ("line", "rect", "rect_fill", "ellipse", "ellipse_fill"):
            return
        if self._shape_start is None:
            return
        pos = self._event_to_editor_xy(event)
        if pos is None:
            self._clear_tool_preview()
            return
        if pos == self._shape_current:
            return
        self._shape_current = pos
        self._draw_tool_preview(self._shape_start, self._shape_current)

    # ============================
    # Projeto / tamanho
    # ============================
    def _on_size_changed(self, value: str) -> None:
        new_size = 8 if value == "8x8" else 16
        if new_size != self.sprite_size:
            if messagebox.askyesno("Trocar tamanho", "Trocar o tamanho reinicia o projeto atual. Continuar?"):
                self._reset_project(size=new_size)
            else:
                self.size_seg.set("8x8" if self.sprite_size == 8 else "16x16")

    def _new_project(self) -> None:
        if messagebox.askyesno("Novo projeto", "Isso vai limpar todos os sprites atuais. Continuar?"):
            self._reset_project(size=self.sprite_size)

    def _reset_project(self, size: int) -> None:
        self.sprite_size = size
        self.selected_sprite_index = 0
        self.current_color_index = 15

        count = 256 if size == 8 else 64
        self.sprites = [Sprite.empty(size=size, color_index=15) for _ in range(count)]

        self.last_loaded_project_id = None
        self.last_loaded_project_name = None
        self._baseline_signature = None

        self._shift_buffers = {}
        self._undo_snapshot = {}

        self.tool_mode = "pencil"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()

        self.table_label.configure(text=f"Sprites ({count}) - miniaturas 2x - grade {'16x16' if size == 8 else '8x8'}")
        self._rebuild_sprite_table()
        self._redraw_all()

    # ============================
    # Grid / seleção
    # ============================
    def _grid_dims(self) -> Tuple[int, int]:
        if self.sprite_size == 8:
            return 16, 16
        return 8, 8

    def _rebuild_sprite_table(self) -> None:
        for w in self.scroll.winfo_children():
            w.destroy()

        cols, _rows = self._grid_dims()
        thumb_scale = THUMB_SCALE
        cell = self.sprite_size * thumb_scale

        self.thumb_canvases: List[tk.Canvas] = []

        for idx in range(len(self.sprites)):
            r = idx // cols
            c = idx % cols
            cv = tk.Canvas(self.scroll, width=cell + 2, height=cell + 2, bg="#202020", highlightthickness=0)
            cv.grid(row=r, column=c, padx=3, pady=3)
            cv.bind("<Button-1>", lambda _e, i=idx: self._select_sprite(i))
            self.thumb_canvases.append(cv)

        for c in range(cols):
            self.scroll.grid_columnconfigure(c, weight=1)

        self._redraw_thumbnails()

    def _select_sprite(self, idx: int) -> None:
        self.selected_sprite_index = idx
        self.status_label.configure(text=f"Sprite selecionado: #{idx}")
        self._redraw_all()

    def _row_stride(self) -> int:
        cols, _ = self._grid_dims()
        return cols

    def _get_2x2_indices(self) -> Optional[List[int]]:
        stride = self._row_stride()
        cols, rows = self._grid_dims()
        idx = self.selected_sprite_index
        r = idx // cols
        c = idx % cols
        if r >= rows - 1 or c >= cols - 1:
            return None
        return [idx, idx + 1, idx + stride, idx + stride + 1]

    def _get_edit_mode(self) -> str:
        return self.mode_seg.get()

    def _get_target_sprite_indices_for_color(self) -> List[int]:
        mode = self._get_edit_mode()
        if mode in ("2x2", "overlay"):
            block = self._get_2x2_indices()
            return block if block else [self.selected_sprite_index]
        return [self.selected_sprite_index]

    # ============================
    # Edição de pixel (modos)
    # ============================
    def _edit_single(self, sp_idx: int, x: int, y: int, value: int, *, set_color: bool = True) -> None:
        sp = self.sprites[sp_idx]
        if set_color:
            sp.color_index = self.current_color_index
        sp.set_pixel(x, y, value)

    def _edit_2x2(self, x: int, y: int, value: int, *, set_color: bool = True) -> None:
        block = self._get_2x2_indices()
        if not block:
            return
        sp_col = 0 if x < self.sprite_size else 1
        sp_row = 0 if y < self.sprite_size else 1
        local_x = x if sp_col == 0 else (x - self.sprite_size)
        local_y = y if sp_row == 0 else (y - self.sprite_size)
        sp_idx = block[sp_row * 2 + sp_col]
        self._edit_single(sp_idx, local_x, local_y, value, set_color=set_color)

    def _edit_overlay(self, x: int, y: int, value: int, *, set_color: bool = True) -> None:
        block = self._get_2x2_indices()
        if not block:
            self._edit_single(self.selected_sprite_index, x, y, value, set_color=set_color)
            return
        active = int(self.overlay_active.get())
        active = max(0, min(3, active))
        sp_idx = block[active]
        self._edit_single(sp_idx, x, y, value, set_color=set_color)

    # ============================
    # Redraw
    # ============================
    def _redraw_all(self) -> None:
        self._redraw_editor()
        self._redraw_preview()
        self._redraw_thumbnails()

    def _draw_sprite_on_canvas(self, canvas: tk.Canvas, sp: Sprite, scale: int, bg: str = "#111111") -> None:
        canvas.delete("all")
        w = sp.size * scale
        h = sp.size * scale
        canvas.configure(width=w, height=h, bg=bg)
        on_color = MSX1_PALETTE_HEX[sp.color_index]

        for y in range(sp.size):
            row = sp.rows[y]
            for x in range(sp.size):
                mask = 1 << (sp.size - 1 - x)
                if row & mask:
                    x0 = x * scale
                    y0 = y * scale
                    canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color)

    def _update_overlay_hint(self) -> None:
        if self._get_edit_mode() == "overlay":
            active = int(self.overlay_active.get())
            self.overlay_hint_label.configure(text=f"Overlay: editando camada {active + 1}/4")
        else:
            self.overlay_hint_label.configure(text="")

    def _redraw_editor(self) -> None:
        mode = self._get_edit_mode()
        scale = EDITOR_SCALE

        if mode == "2x2":
            block = self._get_2x2_indices()
            if not block:
                self.editor_canvas.delete("all")
                wpx = self.sprite_size * 2 * scale
                hpx = self.sprite_size * 2 * scale
                self.editor_canvas.configure(scrollregion=(0, 0, wpx, hpx))
                self.editor_canvas.create_text(
                    10, 10, anchor="nw",
                    fill="#FFFFFF",
                    text="2x2 indisponível na borda.\nSelecione um sprite que permita bloco 2x2."
                )
                self._clear_tool_preview()
                self._update_overlay_hint()
                return

            w = self.sprite_size * 2
            h = self.sprite_size * 2
            self.editor_canvas.delete("all")
            self.editor_canvas.configure(bg="#111111")
            self.editor_canvas.configure(scrollregion=(0, 0, w * scale, h * scale))

            for by in range(2):
                for bx in range(2):
                    sp = self.sprites[block[by * 2 + bx]]
                    on_color = MSX1_PALETTE_HEX[sp.color_index]
                    for y in range(self.sprite_size):
                        row = sp.rows[y]
                        for x in range(self.sprite_size):
                            if row & (1 << (self.sprite_size - 1 - x)):
                                gx = bx * self.sprite_size + x
                                gy = by * self.sprite_size + y
                                x0, y0 = gx * scale, gy * scale
                                self.editor_canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color)

            self._draw_grid(self.editor_canvas, w, h, scale, major_every=self.sprite_size)
        else:
            sp = self.sprites[self.selected_sprite_index]
            self._draw_sprite_on_canvas(self.editor_canvas, sp, scale=scale, bg="#111111")
            self.editor_canvas.configure(scrollregion=(0, 0, sp.size * scale, sp.size * scale))
            self._draw_grid(self.editor_canvas, sp.size, sp.size, scale, major_every=sp.size)

        if self.tool_mode in ("line", "rect", "rect_fill", "ellipse", "ellipse_fill"):
            if self._shape_start is not None and self._shape_current is not None:
                self._draw_tool_preview(self._shape_start, self._shape_current)
            else:
                self._clear_tool_preview()
        else:
            self._clear_tool_preview()

        self._draw_mirror_guides()
        self._update_overlay_hint()

    def _draw_grid(self, canvas: tk.Canvas, w: int, h: int, scale: int, major_every: int) -> None:
        for x in range(w + 1):
            x0 = x * scale
            canvas.create_line(x0, 0, x0, h * scale, fill="#2A2A2A")
        for y in range(h + 1):
            y0 = y * scale
            canvas.create_line(0, y0, w * scale, y0, fill="#2A2A2A")

        if major_every > 0 and (w > major_every or h > major_every):
            major_color = "#4A4A4A"
            for x in range(0, w + 1, major_every):
                x0 = x * scale
                canvas.create_line(x0, 0, x0, h * scale, fill=major_color, width=2)
            for y in range(0, h + 1, major_every):
                y0 = y * scale
                canvas.create_line(0, y0, w * scale, y0, fill=major_color, width=2)

    def _redraw_preview(self) -> None:
        mode = self._get_edit_mode()
        scale = PREVIEW_SCALE

        if mode == "single":
            sp = self.sprites[self.selected_sprite_index]
            self._draw_sprite_on_canvas(self.preview_canvas, sp, scale=scale, bg="#111111")
            return

        if mode == "2x2":
            block = self._get_2x2_indices()
            if not block:
                self.preview_canvas.delete("all")
                self.preview_canvas.configure(width=220, height=220, bg="#111111")
                self.preview_canvas.create_text(10, 10, anchor="nw", fill="#FFFFFF", text="Preview 2x2 indisponível.")
                return

            w = self.sprite_size * 2
            h = self.sprite_size * 2
            self.preview_canvas.configure(width=w * scale, height=h * scale, bg="#111111")
            self.preview_canvas.delete("all")

            for by in range(2):
                for bx in range(2):
                    sp = self.sprites[block[by * 2 + bx]]
                    on_color = MSX1_PALETTE_HEX[sp.color_index]
                    for y in range(self.sprite_size):
                        row = sp.rows[y]
                        for x in range(self.sprite_size):
                            if row & (1 << (self.sprite_size - 1 - x)):
                                gx = bx * self.sprite_size + x
                                gy = by * self.sprite_size + y
                                x0, y0 = gx * scale, gy * scale
                                self.preview_canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color)
            return

        if mode == "overlay":
            block = self._get_2x2_indices()
            if not block:
                sp = self.sprites[self.selected_sprite_index]
                self._draw_sprite_on_canvas(self.preview_canvas, sp, scale=scale, bg="#111111")
                return

            w = self.sprite_size
            h = self.sprite_size
            self.preview_canvas.configure(width=w * scale, height=h * scale, bg="#111111")
            self.preview_canvas.delete("all")

            for layer in range(4):
                sp = self.sprites[block[layer]]
                on_color = MSX1_PALETTE_HEX[sp.color_index]
                for y in range(self.sprite_size):
                    row = sp.rows[y]
                    for x in range(self.sprite_size):
                        if row & (1 << (self.sprite_size - 1 - x)):
                            x0, y0 = x * scale, y * scale
                            self.preview_canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color)
            return

    def _redraw_thumbnails(self) -> None:
        thumb_scale = THUMB_SCALE
        cell = self.sprite_size * thumb_scale

        for idx, cv in enumerate(self.thumb_canvases):
            cv.delete("all")
            sp = self.sprites[idx]
            bg = "#2C2C2C" if idx != self.selected_sprite_index else "#3A3A5A"
            cv.configure(bg=bg, width=cell + 2, height=cell + 2)
            cv.create_rectangle(0, 0, cell + 1, cell + 1, outline="#555555")

            on_color = MSX1_PALETTE_HEX[sp.color_index]
            for y in range(sp.size):
                row = sp.rows[y]
                for x in range(sp.size):
                    if row & (1 << (sp.size - 1 - x)):
                        x0 = 1 + x * thumb_scale
                        y0 = 1 + y * thumb_scale
                        cv.create_rectangle(x0, y0, x0 + thumb_scale, y0 + thumb_scale, outline="", fill=on_color)

    # ============================
    # Salvamento
    # ============================
    def _save_project_with_name(self, name: str, *, update_last_loaded: bool) -> bool:
        try:
            self.db.save_project(name=name, sprite_size=self.sprite_size, sprites=self.sprites)
            if update_last_loaded:
                self.last_loaded_project_name = name
                self.last_loaded_project_id = self.db.get_project_id_by_name(name)
            self._mark_baseline()
            self.status_label.configure(text=f"Projeto salvo: {name}")
            return True
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Nome de projeto já existe e não pôde ser sobrescrito.")
            return False
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")
            return False

    def _save_project(self) -> None:
        default_name = self.last_loaded_project_name or f"projeto_{int(time.time())}"
        name = simpledialog.askstring("Salvar projeto", "Nome do projeto:", initialvalue=default_name)
        if not name:
            return
        ok = self._save_project_with_name(name, update_last_loaded=True)
        if ok:
            messagebox.showinfo("Salvo", f"Projeto '{name}' salvo em sprites.db")

    def _save_last_loaded_project(self) -> bool:
        if not self.last_loaded_project_name:
            return False
        return self._save_project_with_name(self.last_loaded_project_name, update_last_loaded=True)

    # ============================
    # Carregar projeto
    # ============================
    @staticmethod
    def _format_dt(ts: int) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        except Exception:
            return str(ts)

    def _apply_loaded_project(self, project_id: int, name: str, sprite_size: int, sprites: List[Sprite]) -> None:
        self.sprite_size = sprite_size
        self.size_seg.set("8x8" if sprite_size == 8 else "16x16")

        self.sprites = sprites
        self.selected_sprite_index = 0
        self.current_color_index = 15

        self.last_loaded_project_id = project_id
        self.last_loaded_project_name = name
        self._mark_baseline()

        self._shift_buffers = {}
        self._undo_snapshot = {}

        self.tool_mode = "pencil"
        self._reset_shape_state()
        self._is_painting = False
        self._last_paint_xy = None
        self._update_tool_buttons()

        count = 256 if sprite_size == 8 else 64
        self.table_label.configure(text=f"Sprites ({count}) - miniaturas 2x - grade {'16x16' if sprite_size == 8 else '8x8'}")

        self.status_label.configure(text=f"Projeto carregado: {name}")
        self._rebuild_sprite_table()
        self._redraw_all()

    def _open_load_dialog(self) -> None:
        try:
            projects = self.db.list_projects()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao listar projetos: {e}")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title("Carregar projeto (SQLite)")
        dlg.geometry("820x620")
        dlg.transient(self)
        dlg.grab_set()

        header = ctk.CTkFrame(dlg)
        header.pack(side="top", fill="x", padx=12, pady=12)

        ctk.CTkLabel(header, text="Projetos salvos", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        body = ctk.CTkFrame(dlg)
        body.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 12))

        if not projects:
            ctk.CTkLabel(body, text="Nenhum projeto encontrado em sprites.db").pack(side="top", pady=20)
            ctk.CTkButton(body, text="Fechar", command=dlg.destroy).pack(side="top", pady=10)
            return

        list_frame = ctk.CTkScrollableFrame(body)
        list_frame.pack(side="top", fill="both", expand=True)

        preview_scale = 10

        def add_project_row(p: Dict[str, Any]) -> None:
            row = ctk.CTkFrame(list_frame)
            row.pack(side="top", fill="x", padx=10, pady=8)

            left = ctk.CTkFrame(row)
            left.pack(side="left", padx=10, pady=10)

            spr = None
            try:
                spr = self.db.load_first_sprite(p["id"])
            except Exception:
                spr = None

            cv = tk.Canvas(left, width=8 * preview_scale, height=8 * preview_scale, bg="#111111", highlightthickness=0)
            cv.pack(side="top")

            if spr is not None:
                self._draw_sprite_on_canvas(cv, spr, scale=preview_scale, bg="#111111")

            info = ctk.CTkFrame(row)
            info.pack(side="left", fill="both", expand=True, padx=10, pady=10)

            ctk.CTkLabel(info, text=p["name"], font=ctk.CTkFont(size=16, weight="bold")).pack(side="top", anchor="w")
            ctk.CTkLabel(info, text=f"Criado em: {self._format_dt(int(p['created_at']))}").pack(side="top", anchor="w", pady=(4, 0))
            ctk.CTkLabel(info, text=f"Tamanho: {p['sprite_size']}x{p['sprite_size']}").pack(side="top", anchor="w", pady=(2, 0))

            actions = ctk.CTkFrame(row)
            actions.pack(side="right", padx=10, pady=10)

            def do_load() -> None:
                try:
                    name2, sprite_size2, _created_at, sprites2 = self.db.load_project(int(p["id"]))
                    self._apply_loaded_project(project_id=int(p["id"]), name=name2, sprite_size=sprite_size2, sprites=sprites2)
                    dlg.destroy()
                except Exception as e:
                    messagebox.showerror("Erro", f"Falha ao carregar projeto: {e}")

            ctk.CTkButton(actions, text="Carregar", command=do_load, width=120).pack(side="top")
            ctk.CTkButton(actions, text="Fechar", command=dlg.destroy, width=120).pack(side="top", pady=(8, 0))

        for p in projects:
            add_project_row(p)

    # ============================
    # Saída
    # ============================
    def _request_exit(self) -> None:
        if self._has_unsaved_changes_for_last_loaded():
            proj_name = self.last_loaded_project_name or "(sem nome)"
            resp = messagebox.askyesnocancel(
                "Sair",
                f"O projeto '{proj_name}' foi alterado desde o último carregamento/salvamento.\n\n"
                f"Deseja salvar antes de sair?"
            )
            if resp is None:
                return
            if resp is True:
                ok = self._save_last_loaded_project()
                if not ok:
                    return
                self.destroy()
                return
            self.destroy()
            return

        self.destroy()


if __name__ == "__main__":
    run_app_with_splash()