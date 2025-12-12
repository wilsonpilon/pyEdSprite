import sqlite3
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

import tkinter as tk
from tkinter import messagebox, simpledialog

import customtkinter as ctk


# ----------------------------
# MSX1 palette (TMS9918A-ish)
# 16 colors, index 0..15.
# Nota: a cor 0 costuma ser "transparente" em sprites; aqui usamos preto como visualização.
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
EDITOR_SCALE = 16   # metade de 32 (ainda grande, mas bem mais controlável)
THUMB_SCALE = 2
PREVIEW_SCALE = 2


# ----------------------------
# Data model
# ----------------------------
@dataclass
class Sprite:
    size: int                 # 8 or 16
    color_index: int          # 0..15 (MSX1 sprite color)
    rows: List[int]           # bitmask per row; width bits used

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

    @staticmethod
    def _pack_rows(size: int, rows: List[int]) -> bytes:
        # 8x8: 8 bytes (1 byte per row)
        # 16x16: 32 bytes (2 bytes per row, big-endian)
        if size == 8:
            return bytes((r & 0xFF) for r in rows)
        if size == 16:
            out = bytearray()
            for r in rows:
                out.append((r >> 8) & 0xFF)
                out.append(r & 0xFF)
            return bytes(out)
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


# ----------------------------
# UI
# ----------------------------
class SpriteEditorApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("pyEdSprite - MSX1 Sprite Editor (MVP)")
        self.geometry("1250x780")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.db = SpriteDB("sprites.db")

        self.sprite_size = 8  # 8 or 16
        self.sprites: List[Sprite] = []
        self.selected_sprite_index: int = 0

        self.edit_mode = tk.StringVar(value="single")  # single | 2x2 | overlay
        self.overlay_active = tk.IntVar(value=0)        # which of the 4 sprites is edited in overlay (0..3)

        self.current_color_index: int = 15  # default white

        self._build_layout()
        self._reset_project(size=8)

    def _build_layout(self) -> None:
        # Top bar
        top = ctk.CTkFrame(self)
        top.pack(side="top", fill="x", padx=10, pady=10)

        self.size_seg = ctk.CTkSegmentedButton(
            top,
            values=["8x8", "16x16"],
            command=self._on_size_changed
        )
        self.size_seg.set("8x8")
        self.size_seg.pack(side="left", padx=8)

        self.mode_seg = ctk.CTkSegmentedButton(
            top,
            values=["single", "2x2", "overlay"],
            command=lambda _: self._redraw_all()
        )
        self.mode_seg.set("single")
        self.mode_seg.pack(side="left", padx=8)

        overlay_frame = ctk.CTkFrame(top)
        overlay_frame.pack(side="left", padx=8)
        ctk.CTkLabel(overlay_frame, text="Overlay: editar sprite").pack(side="left", padx=(8, 6))
        for i in range(4):
            rb = ctk.CTkRadioButton(
                overlay_frame, text=str(i + 1), variable=self.overlay_active, value=i,
                command=self._redraw_all
            )
            rb.pack(side="left", padx=4)

        ctk.CTkButton(top, text="Novo Projeto", command=self._new_project).pack(side="left", padx=8)
        ctk.CTkButton(top, text="Salvar Projeto (SQLite)", command=self._save_project).pack(side="left", padx=8)

        # Main split
        main = ctk.CTkFrame(self)
        main.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

        # Left: sprite table (thumbnails)
        left = ctk.CTkFrame(main)
        left.pack(side="left", fill="y", padx=(0, 10), pady=10)

        self.table_label = ctk.CTkLabel(left, text="Sprites (MSX1)")
        self.table_label.pack(side="top", pady=(10, 6))

        self.scroll = ctk.CTkScrollableFrame(left, width=420, height=650)
        self.scroll.pack(side="top", fill="y", padx=10, pady=(0, 10))

        # Right: editor + palette + preview
        right = ctk.CTkFrame(main)
        right.pack(side="left", fill="both", expand=True, pady=10)

        editor_row = ctk.CTkFrame(right)
        editor_row.pack(side="top", fill="x", padx=10, pady=10)

        # ============================
        # Editor canvas with scrollbars
        # ============================
        editor_container = ctk.CTkFrame(editor_row)
        editor_container.pack(side="left", padx=(0, 10), pady=0)

        self.editor_canvas = tk.Canvas(
            editor_container,
            width=820,
            height=650,
            bg="#111111",
            highlightthickness=0
        )
        self.editor_canvas.grid(row=0, column=0, sticky="nsew")

        self.editor_vscroll = tk.Scrollbar(editor_container, orient="vertical", command=self.editor_canvas.yview)
        self.editor_hscroll = tk.Scrollbar(editor_container, orient="horizontal", command=self.editor_canvas.xview)
        self.editor_vscroll.grid(row=0, column=1, sticky="ns")
        self.editor_hscroll.grid(row=1, column=0, sticky="ew")

        self.editor_canvas.configure(yscrollcommand=self.editor_vscroll.set, xscrollcommand=self.editor_hscroll.set)
        editor_container.grid_rowconfigure(0, weight=1)
        editor_container.grid_columnconfigure(0, weight=1)

        self.editor_canvas.bind("<Button-1>", lambda e: self._on_editor_click(e, value=1))
        self.editor_canvas.bind("<Button-3>", lambda e: self._on_editor_click(e, value=0))

        # Side panel: palette + preview
        side = ctk.CTkFrame(editor_row)
        side.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(side, text="Paleta MSX1 (1 cor por sprite)").pack(side="top", pady=(10, 6))
        self.palette_frame = ctk.CTkFrame(side)
        self.palette_frame.pack(side="top", padx=10, pady=(0, 10))

        self._build_palette()

        ctk.CTkLabel(side, text="Preview (2x)").pack(side="top", pady=(6, 6))
        self.preview_canvas = tk.Canvas(side, width=220, height=220, bg="#111111", highlightthickness=0)
        self.preview_canvas.pack(side="top", padx=10, pady=(0, 10))

        self.status_label = ctk.CTkLabel(side, text="Pronto.")
        self.status_label.pack(side="top", padx=10, pady=(6, 10))

    def _build_palette(self) -> None:
        for w in self.palette_frame.winfo_children():
            w.destroy()

        cols = 4
        for i, hex_color in enumerate(MSX1_PALETTE_HEX):
            r = i // cols
            c = i % cols
            btn = ctk.CTkButton(
                self.palette_frame,
                text=f"{i:02d}",
                width=70,
                height=34,
                fg_color=hex_color,
                text_color="#000000" if i in (11, 14, 15) else "#FFFFFF",
                command=lambda idx=i: self._set_color(idx),
            )
            btn.grid(row=r, column=c, padx=6, pady=6)

    def _set_color(self, idx: int) -> None:
        self.current_color_index = idx
        for sp_idx in self._get_target_sprite_indices_for_color():
            self.sprites[sp_idx].color_index = idx
        self.status_label.configure(text=f"Cor selecionada: {idx} ({MSX1_PALETTE_HEX[idx]})")
        self._redraw_all()

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

        self.table_label.configure(
            text=f"Sprites ({count}) - miniaturas 2x - grade {'16x16' if size == 8 else '8x8'}"
        )

        self._rebuild_sprite_table()
        self._redraw_all()

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
            cv.bind("<Button-1>", lambda e, i=idx: self._select_sprite(i))
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

    def _on_editor_click(self, event: tk.Event, value: int) -> None:
        mode = self._get_edit_mode()

        if mode == "2x2":
            if not self._get_2x2_indices():
                self.status_label.configure(text="2x2 indisponível na borda da grade. Selecione outro sprite.")
                return
            w = self.sprite_size * 2
            h = self.sprite_size * 2
        else:
            w = self.sprite_size
            h = self.sprite_size

        scale = EDITOR_SCALE

        cx = self.editor_canvas.canvasx(event.x)
        cy = self.editor_canvas.canvasy(event.y)

        x = int(cx // scale)
        y = int(cy // scale)
        if not (0 <= x < w and 0 <= y < h):
            return

        if mode == "single":
            self._edit_single(self.selected_sprite_index, x, y, value)
        elif mode == "2x2":
            self._edit_2x2(x, y, value)
        elif mode == "overlay":
            self._edit_overlay(x, y, value)
        else:
            return

        self._redraw_all()

    def _edit_single(self, sp_idx: int, x: int, y: int, value: int) -> None:
        sp = self.sprites[sp_idx]
        sp.color_index = self.current_color_index
        sp.set_pixel(x, y, value)

    def _edit_2x2(self, x: int, y: int, value: int) -> None:
        block = self._get_2x2_indices()
        if not block:
            return

        sp_col = 0 if x < self.sprite_size else 1
        sp_row = 0 if y < self.sprite_size else 1
        local_x = x if sp_col == 0 else (x - self.sprite_size)
        local_y = y if sp_row == 0 else (y - self.sprite_size)

        sp_idx = block[sp_row * 2 + sp_col]
        self._edit_single(sp_idx, local_x, local_y, value)

    def _edit_overlay(self, x: int, y: int, value: int) -> None:
        block = self._get_2x2_indices()
        if not block:
            self._edit_single(self.selected_sprite_index, x, y, value)
            return

        active = int(self.overlay_active.get())
        active = max(0, min(3, active))
        sp_idx = block[active]
        self._edit_single(sp_idx, x, y, value)

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
                                self.editor_canvas.create_rectangle(
                                    x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color
                                )

            self._draw_grid(self.editor_canvas, w, h, scale, major_every=self.sprite_size)

        else:
            sp = self.sprites[self.selected_sprite_index]
            self._draw_sprite_on_canvas(self.editor_canvas, sp, scale=scale, bg="#111111")
            self.editor_canvas.configure(scrollregion=(0, 0, sp.size * scale, sp.size * scale))
            self._draw_grid(self.editor_canvas, sp.size, sp.size, scale, major_every=sp.size)

            if mode == "overlay":
                block = self._get_2x2_indices()
                if block:
                    active = int(self.overlay_active.get())
                    self.editor_canvas.create_text(
                        6, 6, anchor="nw", fill="#FFFFFF",
                        text=f"Overlay: editando camada {active + 1}/4"
                    )

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
                                self.preview_canvas.create_rectangle(
                                    x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color
                                )
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
                            self.preview_canvas.create_rectangle(
                                x0, y0, x0 + scale, y0 + scale, outline="", fill=on_color
                            )

            active = int(self.overlay_active.get())
            self.preview_canvas.create_text(
                4, 4, anchor="nw", fill="#FFFFFF",
                text=f"Overlay (edit: {active + 1}/4)"
            )

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
                        cv.create_rectangle(
                            x0, y0, x0 + thumb_scale, y0 + thumb_scale,
                            outline="", fill=on_color
                        )

    def _save_project(self) -> None:
        default_name = f"projeto_{int(time.time())}"
        name = simpledialog.askstring("Salvar projeto", "Nome do projeto:", initialvalue=default_name)
        if not name:
            return

        try:
            self.db.save_project(name=name, sprite_size=self.sprite_size, sprites=self.sprites)
            messagebox.showinfo("Salvo", f"Projeto '{name}' salvo em sprites.db")
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Nome de projeto já existe e não pôde ser sobrescrito.")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")


if __name__ == "__main__":
    app = SpriteEditorApp()
    app.mainloop()