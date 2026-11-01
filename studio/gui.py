"""Net Studio window (tkinter, no extra packages): pick a preset, change it, preview, generate, export to Unity.

  python -m studio.gui      (or double-click start_studio.bat)
"""
import copy
import os
import queue
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from . import config, runner, unity_export

# (group, key, label, kind, options). kind: float (lo, hi, step), int, choice [..], bool, colour.
FIELDS = {
    "Head": [
        ("head", "arm_length_in", "Arm length (inches, each arm: pivot to corner)", "float", (30, 60, 1)),
        ("head", "opening_angle_deg", "Opening angle between the arms (deg)", "float", (60, 120, 1)),
        ("head", "arm_bow_m", "Arm bow (m, outward at mid-arm)", "float", (0, 0.06, 0.002)),
        ("head", "arm_base_diameter_mm", "Arm diameter at the spreader (mm)", "float", (6, 20, 0.5)),
        ("head", "arm_tip_diameter_mm", "Arm diameter at the tip (mm)", "float", (4, 16, 0.5)),
        ("head", "cord_diameter_mm", "Rim cord diameter (mm)", "float", (2, 10, 0.5)),
    ],
    "Handle": [
        ("handle", "length_m", "Handle length (m, butt end to the thread)", "float", (1.0, 2.5, 0.05)),
        ("handle", "sections", "Sections", "choice", [1, 2]),
        ("handle", "joint_from_butt_m", "Joint from the butt (m, two-piece; empty = middle)", "optfloat", None),
        ("handle", "spigot_overlap_m", "Spigot overlap (m)", "float", (0.06, 0.25, 0.01)),
        ("handle", "butt_diameter_mm", "Butt diameter (mm)", "float", (18, 36, 0.5)),
        ("handle", "top_diameter_mm", "Top diameter (mm)", "float", (14, 32, 0.5)),
        ("handle", "grip_length_m", "Rear grip length (m)", "float", (0.1, 0.6, 0.01)),
        ("handle", "front_grip_from_butt_m", "Front hand position (m from the butt)", "float", (0.5, 2.3, 0.05)),
        ("handle", "grip_pattern", "Grip pattern", "choice", ["diamond", "ribbed"]),
    ],
    "Bag": [
        ("bag", "depth_m", "Bag depth (m below the mouth)", "float", (0.4, 1.4, 0.01)),
        ("bag", "bulge", "Bulge", "float", (0, 0.3, 0.01)),
        ("bag", "fold_m", "Soft folds (m)", "float", (0, 0.04, 0.001)),
        ("bag", "round_end", "Rounding depth (0-1)", "float", (0.2, 1.0, 0.05)),
        ("bag", "hole_mm", "Hole size (mm, clear opening)", "float", (3, 25, 0.5)),
        ("bag", "strand_mm", "Twine thickness (mm)", "float", (0.5, 3, 0.1)),
        ("bag", "hole_orientation", "Hole orientation", "choice", ["diamond", "square"]),
        ("bag", "knot", "Knots", "choice", ["knotless", "knotted"]),
        ("bag", "seams", "Seam tape", "bool", None),
        ("bag", "arm_sleeve", "Netting wrapped over the arms", "bool", None),
    ],
    "Material": [
        ("material", "net_hex", "Netting", "colour", None),
        ("material", "carbon_hex", "Carbon", "colour", None),
        ("material", "grip_hex", "Grip and cap", "colour", None),
        ("material", "cord_hex", "Rim cord", "colour", None),
        ("material", "fitting_hex", "Fittings and spreader", "colour", None),
        ("material", "binding_hex", "Seam tape", "colour", None),
        ("material", "wetness", "Wetness (0 dry - 1 soaked)", "float", (0, 1, 0.05)),
        ("material", "carbon_roughness", "Carbon roughness", "float", (0.2, 0.9, 0.05)),
        ("material", "net_roughness", "Netting roughness", "float", (0.4, 1.0, 0.02)),
    ],
    "Quality": [
        ("quality", "texture_resolution", "Texture size", "choice", [1024, 2048]),
        ("", "seed", "Seed (folds, texture variation)", "int", None),
        ("export", "glb", "Also export a GLB (LOD0)", "bool", None),
        ("export", "pickup_proxy", "Pickup capsule (off by default)", "bool", None),
    ],
}

VIEWS = [("3/4", "three_quarter"), ("Side", "side"), ("Top", "top"), ("Front", "front"), ("Head", "head"),
         ("Spreader", "spreader"), ("Bag detail", "bag_detail"), ("Underside", "under"), ("Hands", "hand_scale"),
         ("Scooping", "scooping"), ("Poses", "pose_transition"), ("Wet/dry", "wet_dry"), ("Apart", "disassembled"),
         ("LODs", "lod_compare"), ("Distances", "distance_sheet"), ("All", "contact_sheet")]


class App:
    def __init__(self, root):
        self.root = root
        root.title("Carp Landing Net Studio")
        root.geometry("1500x900")
        self.vars = {}
        self.preset = None
        self.busy = False
        self.lines = queue.Queue()
        self.image = None
        self.view = "three_quarter"
        self._build()
        names = config.list_presets()
        self.preset_box["values"] = names
        if names:
            self.preset_box.set(names[0])
            self.load(names[0])
        root.after(100, self._drain)

    # ------------------------------------------------------------ layout

    def _build(self):
        left = ttk.Frame(self.root, padding=6)
        left.pack(side="left", fill="y")
        right = ttk.Frame(self.root, padding=6)
        right.pack(side="left", fill="both", expand=True)

        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Preset").pack(side="left")
        self.preset_box = ttk.Combobox(top, state="readonly", width=26)
        self.preset_box.pack(side="left", padx=4)
        self.preset_box.bind("<<ComboboxSelected>>", lambda e: self.load(self.preset_box.get()))
        ttk.Button(top, text="Save preset as...", command=self.save_as).pack(side="left")
        name = ttk.Frame(left)
        name.pack(fill="x", pady=(4, 0))
        ttk.Label(name, text="Name").pack(side="left")
        self.name_var = tk.StringVar()
        ttk.Entry(name, textvariable=self.name_var, width=46).pack(side="left", padx=4)

        tabs = ttk.Notebook(left, width=470)
        tabs.pack(fill="both", expand=True, pady=6)
        for title, fields in FIELDS.items():
            page = ttk.Frame(tabs, padding=6)
            tabs.add(page, text=title)
            for row, (group, key, label, kind, opt) in enumerate(fields):
                ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", pady=2)
                self.vars[(group, key)] = self._widget(page, row, kind, opt)

        self.derived = tk.StringVar()
        ttk.Label(left, textvariable=self.derived, justify="left", font=("Consolas", 9)).pack(fill="x")
        self.problem = tk.StringVar()
        ttk.Label(left, textvariable=self.problem, foreground="#a02020", wraplength=460, justify="left").pack(fill="x")

        act = ttk.Frame(left)
        act.pack(fill="x", pady=4)
        ttk.Label(act, text="Quick state").pack(side="left")
        self.state_box = ttk.Combobox(act, state="readonly", width=12, values=["deployed", "scooping", "lying", "wet", "disassembled"])
        self.state_box.set("deployed")
        self.state_box.pack(side="left", padx=4)
        ttk.Button(act, text="Quick preview", command=lambda: self.run(True)).pack(side="left", padx=2)
        ttk.Button(act, text="Generate (full)", command=lambda: self.run(False)).pack(side="left", padx=2)
        act2 = ttk.Frame(left)
        act2.pack(fill="x")
        ttk.Button(act2, text="Open output folder", command=self.open_output).pack(side="left", padx=2)
        ttk.Button(act2, text="Export to Unity...", command=self.export_unity).pack(side="left", padx=2)
        self.progress = ttk.Progressbar(left, mode="indeterminate")
        self.progress.pack(fill="x", pady=4)
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.status, wraplength=460).pack(fill="x")

        bar = ttk.Frame(right)
        bar.pack(fill="x")
        for label, key in VIEWS:
            ttk.Button(bar, text=label, width=9, command=lambda k=key: self.show(k)).pack(side="left", padx=1)
        self.canvas = tk.Label(right, background="#202020")
        self.canvas.pack(fill="both", expand=True, pady=4)
        self.canvas.bind("<Configure>", lambda e: self.show(self.view))
        self.log = tk.Text(right, height=12, font=("Consolas", 9), background="#111", foreground="#ddd")
        self.log.pack(fill="x")

    def _widget(self, page, row, kind, opt):
        if kind == "float":
            var = tk.DoubleVar()
            lo, hi, step = opt
            ttk.Scale(page, from_=lo, to=hi, variable=var, length=150,
                      command=lambda v, var=var, step=step: var.set(round(round(float(v) / step) * step, 4))).grid(row=row, column=1)
            ttk.Entry(page, textvariable=var, width=8).grid(row=row, column=2, padx=4)
        elif kind in ("int", "optfloat"):
            var = tk.StringVar()
            ttk.Entry(page, textvariable=var, width=10).grid(row=row, column=1, sticky="w")
        elif kind == "choice":
            var = tk.StringVar()
            ttk.Combobox(page, textvariable=var, values=[str(o) for o in opt], state="readonly", width=12).grid(row=row, column=1, sticky="w")
        elif kind == "bool":
            var = tk.BooleanVar()
            ttk.Checkbutton(page, variable=var).grid(row=row, column=1, sticky="w")
        else:
            var = tk.StringVar()
            swatch = tk.Label(page, width=4, relief="solid")
            swatch.grid(row=row, column=1, sticky="w")

            def pick(var=var):
                got = colorchooser.askcolor(color=var.get())[1]
                if got:
                    var.set(got)

            ttk.Button(page, text="Pick...", command=pick).grid(row=row, column=2)
            var.trace_add("write", lambda *a, var=var, s=swatch: self._swatch(s, var))
        var.trace_add("write", lambda *a: self.refresh())
        var.kind = kind
        return var

    @staticmethod
    def _swatch(label, var):
        try:
            label.configure(background=var.get())
        except tk.TclError:
            pass

    # ------------------------------------------------------------ data

    def load(self, name):
        try:
            self.preset = config.load_preset(name)
            cfg, notes = config.resolve(self.preset)
        except config.ConfigError as exc:
            messagebox.showerror("Net Studio", str(exc))
            return
        self._loading = True
        self.name_var.set(cfg["name"])
        for (group, key), var in self.vars.items():
            value = cfg[group][key] if group else cfg[key]
            var.set("" if value is None else value)
        self._loading = False
        self.refresh()
        self.show(self.view)
        for n in notes:
            self.say("note: " + n)

    def current(self):
        """The preset as edited in the window (raises ConfigError on a value that isn't a number)."""
        p = copy.deepcopy(self.preset or {})
        p["name"] = self.name_var.get() or p.get("name", "net")
        for (group, key), var in self.vars.items():
            raw = var.get()
            kind = var.kind
            try:
                if kind == "choice":
                    value = int(raw) if str(raw).isdigit() else raw
                elif kind == "int":
                    value = int(raw)
                elif kind == "optfloat":
                    value = None if str(raw).strip() == "" else float(raw)
                elif kind == "float":
                    value = float(raw)
                else:
                    value = raw
            except (ValueError, tk.TclError):
                raise config.ConfigError(f"{group}.{key}: {raw!r} is not a number") from None
            if group:
                p.setdefault(group, {})[key] = value
            else:
                p[key] = value
        return p

    def refresh(self):
        if getattr(self, "_loading", False) or self.preset is None:
            return
        try:
            cfg, notes = config.resolve(self.current())
        except (config.ConfigError, tk.TclError) as exc:
            self.problem.set(str(exc))
            return
        d = config.describe(cfg)
        s, r = d["source"], d["derived"]
        self.derived.set(
            f"arm {s['arm_length_in']:g} in = {s['arm_length_m']:.4f} m (each arm, pivot to corner)\n"
            f"mouth {r['mouth_width_m']:.3f} m wide x {r['mouth_depth_m']:.3f} m deep, {r['mouth_area_m2']:.3f} m2\n"
            f"sockets {r['socket_angle_deg']:.1f} deg apart, overall {r['overall_length_m']:.3f} m, "
            f"bag {cfg['bag']['depth_m']:.2f} m deep")
        self.problem.set("\n".join(notes))

    def save_as(self):
        try:
            cfg, _ = config.resolve(self.current())
        except config.ConfigError as exc:
            messagebox.showerror("Net Studio", str(exc))
            return
        name = simpledialog.askstring("Save preset", "Preset name (letters, digits, _):", initialvalue=cfg["id"])
        if not name:
            return
        try:
            path = config.save_preset(name, cfg)
        except config.ConfigError as exc:
            messagebox.showerror("Net Studio", str(exc))
            return
        names = config.list_presets()
        self.preset_box["values"] = names
        self.preset_box.set(path.stem)
        self.load(path.stem)
        self.say(f"saved {path}")

    # ------------------------------------------------------------ running

    def run(self, quick):
        if self.busy:
            return
        try:
            cfg, notes = config.resolve(self.current())
        except config.ConfigError as exc:
            messagebox.showerror("Net Studio", str(exc))
            return
        for n in notes:
            self.say("note: " + n)
        self.busy = True
        self.cfg = cfg
        state = self.state_box.get()
        self.progress.start(12)
        self.status.set(("Quick preview (" + state + ")" if quick else "Generating (full)") + " ...")

        def work():
            try:
                code, out = runner.run(cfg, quick=quick, state=state, on_line=self.lines.put)
                self.lines.put(("done", quick, code, str(out), state))
            except Exception as exc:  # noqa: BLE001 - shown in the window
                self.lines.put(("done", quick, 2, str(exc), state))

        threading.Thread(target=work, daemon=True).start()

    def _drain(self):
        try:
            while True:
                item = self.lines.get_nowait()
                if isinstance(item, tuple):
                    self._finished(*item[1:])
                else:
                    self.say(item)
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _finished(self, quick, code, out, state):
        self.busy = False
        self.progress.stop()
        if quick:
            self.status.set("Quick preview done." if code == 0 else f"Quick preview failed (exit {code}): {out}")
            self.show("quick_" + state)
            return
        report = os.path.join(out, "validation_report.json")
        if os.path.exists(report):
            data = config.load_json(report)
            tri = ", ".join(f"LOD{k} {data['stats'].get(f'LOD{k}_triangles', '?')}" for k in range(3))
            fails = [c for c in data["checks"] if c["status"] == "fail"]
            self.status.set(("PASSED" if data["passed"] else f"FAILED ({len(fails)} checks)") + f" - {tri} triangles")
        else:
            self.status.set(f"Generate failed (exit {code}): see the log")
        self.show("three_quarter")

    def say(self, line):
        self.log.insert("end", line + "\n")
        self.log.see("end")

    # ------------------------------------------------------------ preview and files

    def out_dir(self):
        try:
            cfg, _ = config.resolve(self.current())
        except config.ConfigError:
            return None
        return runner.OUTPUT / cfg["id"]

    def show(self, view):
        self.view = view
        out = self.out_dir()
        path = out / "previews" / f"{view}.png" if out else None
        if not path or not path.exists():
            self.canvas.configure(image="", text="No preview yet: press Quick preview or Generate (full).", foreground="#aaa")
            return
        img = tk.PhotoImage(file=str(path))
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        factor = max(1, -(-img.width() // w), -(-img.height() // h))
        self.image = img.subsample(factor) if factor > 1 else img
        self.canvas.configure(image=self.image, text="")

    def open_output(self):
        out = self.out_dir()
        if out and out.exists():
            os.startfile(out)  # noqa: S606 - opens Explorer on Windows
        else:
            messagebox.showinfo("Net Studio", "Nothing generated for this preset yet.")

    def export_unity(self):
        out = self.out_dir()
        if not out or not (out / "export" / "net_manifest.json").exists():
            messagebox.showinfo("Net Studio", "Generate (full) first.")
            return
        guess = unity_export.guess_unity_project()
        project = filedialog.askdirectory(title="Unity project folder (has Assets and ProjectSettings)",
                                          initialdir=str(guess) if guess else None)
        if not project:
            return
        try:
            dest, files = unity_export.plan(out / "export", project, out.name)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Net Studio", str(exc))
            return
        listing = "\n".join(str(d.relative_to(dest)) for _, d in files[:30])
        more = f"\n... and {len(files) - 30} more" if len(files) > 30 else ""
        if not messagebox.askyesno("Export to Unity", f"Copy {len(files)} files into\n{dest}\n\nNothing outside it is touched:\n\n"
                                   f"{listing}{more}\n\nThen in Unity: Tools > Net Studio > Rebuild All Net Prefabs."):
            return
        n = unity_export.copy(files)
        self.say(f"copied {n} files into {dest}")
        self.status.set(f"Exported to {dest}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
