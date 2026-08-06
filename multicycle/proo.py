import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading

REGISTER_NAMES = [
    "zero","at","v0","v1","a0","a1","a2","a3",
    "t0","t1","t2","t3","t4","t5","t6","t7",
    "s0","s1","s2","s3","s4","s5","s6","s7",
    "t8","t9","gp","sp","fp","ra"
]

class CPUState:
    def __init__(self):
        self.regs = {r:0 for r in REGISTER_NAMES}
        self.regs['sp'] = 1024
        self.regs['zero'] = 0
        self.memory = [0]*4096
        self.PC = 0
        self.IR = None
        self.A = 0
        self.B = 0
        self.ALUOut = 0
        self.MDR = 0
        self.control = {}
        self.cycle_step = 0
        self.halted = False

    def reset(self):
        self.__init__()

    def load_program(self, inst_list, start_addr=0):
        self.program = {}
        addr = start_addr
        for line in inst_list:
            t = line.strip()
            if not t or t.startswith('#'):
                continue
            self.program[addr] = t
            addr += 4
        self.PC = start_addr

# -------------------- Parser --------------------

def parse_instruction(text: str):
    parts = text.replace(',', ' ').split()
    if not parts:
        return None
    op = parts[0].lower()
    try:
        if op == 'add' and len(parts) >= 4:
            rd, rs, rt = parts[1], parts[2], parts[3]
            return ('r','add', rd, rs, rt)
        if op == 'addi' and len(parts) >= 4:
            rt, rs, imm = parts[1], parts[2], int(parts[3])
            return ('i','addi', rt, rs, imm)
        # fallback: store as raw
        return ('raw', text)
    except Exception:
        return ('raw', text)

# -------------------- Visual Simulator --------------------

class VisualSimulator(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack(fill='both', expand=True)
        self.cpu = CPUState()
        self.running = False
        self.run_delay = 0.7

        self._build_ui()
        self.draw_datapath()
        #self._update_inspectors()

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self)
        top.pack(side='top', fill='x')

        ttk.Button(top, text='Load Sample', command=self._load_sample).pack(side='left', padx=4)
        ttk.Button(top, text='Simulate', command=lambda: threading.Thread(target=self.simulate_add, daemon=True).start()).pack(side='left', padx=4)
        ttk.Button(top, text='Reset', command=self._reset).pack(side='left', padx=4)

        ttk.Label(top, text='Speed:').pack(side='left', padx=6)
        self.speed_var = tk.DoubleVar(value=self.run_delay)
        ttk.Spinbox(top, from_=0.1, to=2.0, increment=0.1, textvariable=self.speed_var, width=4, command=self._change_speed).pack(side='left')

        main = ttk.Frame(self)
        main.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(main, width=1100, height=560, bg='white')
        self.canvas.pack(side='left', padx=6, pady=6)

        bottom = ttk.Frame(self)
        bottom.pack(fill='x', pady=4)
        ttk.Label(bottom, text='Program Editor:').pack(anchor='w')
        self.program_text = tk.Text(bottom, height=6)
        self.program_text.pack(fill='x')
        ttk.Button(bottom, text='Load Program', command=self._load_from_editor).pack(pady=4)

    def _load_sample(self):
        sample = [
            '# sample',
            'add s1 s1 s2',
        ]
        self.program_text.delete('1.0','end')
        self.program_text.insert('end', ''.join(sample))
        self._load_from_editor()

    def _load_from_editor(self):
        text = self.program_text.get('1.0','end').splitlines()
        try:
            self.cpu.load_program(text, start_addr=0)
            self._reset_runtime()
            messagebox.showinfo('Loaded', 'Program loaded')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _reset(self):
        self.cpu.reset()
        self._reset_runtime()

    def _reset_runtime(self):
        self.cpu.cycle_step = 0
        self.cpu.IR = None
        self.cpu.A = 0
        self.cpu.B = 0
        self.cpu.ALUOut = 0
        self.cpu.MDR = 0
        self.cpu.control = {}
        self.running = False
        self.canvas.itemconfig(self.cycle_info, text='Ready')

    def _change_speed(self):
        self.run_delay = float(self.speed_var.get())

    # ---------- Datapath drawing helpers ----------
    def make_box(self,c, x, y, w, h, text, color):
        rect = c.create_rectangle(x, y, x + w, y + h, fill=color)
        c.create_text(x + w / 2, y + h / 2, text=text)
        return rect

    def make_triangle(self, c, x, y, w, h, text, color):
        points = [
            x, y,  # top point
            x + w, y + h / 2,  # right middle point
            x, y + h  # bottom point
        ]
        tri = c.create_polygon(points, fill=color, outline='black')
        c.create_text(x + w / 2.5, y + h / 2, text=text)
        return tri

    def make_mux_oval(self, c, x, y, w, h, text='', color='#D5F5E3'):
        oval = c.create_oval(x, y, x + w, y + h, fill=color, outline='black')
        if text:
            c.create_text(x + w / 2, y + h / 2, text=text, font=('Arial', 5,'bold' ))
        return oval

    # ---------- Datapath ----------
    def draw_datapath(self):
        c = self.canvas
        c.delete('all')
        self.boxes = {}
        self.labels = {}

        # boxes (positions chosen to match earlier coordinates)
        self.boxes['PC'] = self.make_box(c, 30, 80, 40, 50, 'PC', '#D6EAF8')
        self.boxes['Memory'] = self.make_box(c, 130, 160, 120, 200, 'Memory', '#FEF9E7')
        self.boxes['IR'] = self.make_box(c, 300, 170, 50, 70, 'IR', '#FADBD8')
        self.boxes['RegFile'] = self.make_box(c, 450, 160, 120, 200, 'Register File', '#E8F8F5')
        self.boxes['ALU'] = self.make_triangle(c, 740, 223, 80, 90, 'ALU', '#FFF2E6')
        self.boxes['MDR'] = self.make_box(c, 300, 270, 50, 70, 'MDR', '#FDEDEC')
        self.boxes['A'] = self.make_box(c, 600, 215, 30, 40, 'A', '#D6EAF8')
        self.boxes['B'] = self.make_box(c, 600, 280, 30, 40, 'B', '#D6EAF8')
        self.boxes['ALUOUT'] = self.make_box(c, 845, 255, 50, 20, 'ALUOUT', '#D6EAF8')
        self.boxes['IorD'] = self.make_mux_oval(c, 85, 165, 20, 50, '  0\n\nMUX\n\n  1')
        self.boxes['RegDst'] = self.make_mux_oval(c, 390, 190, 20, 50, '  0\n\nMUX\n\n  1')
        self.boxes['MemToReg'] = self.make_mux_oval(c, 390, 290, 20, 50, '  0\n\nMUX\n\n  1')
        self.boxes['ALUSrcA'] = self.make_mux_oval(c, 680, 195, 20, 50, '  0\n\nMUX\n\n  1')
        self.boxes['ALUSrcB'] = self.make_mux_oval(c, 680, 285, 20, 90, '\n0\n\n1\n\n2\n\n3\n\n4\n')
        self.boxes['PCSrc'] = self.make_mux_oval(c, 930, 235, 20, 70, '0\n\n2\n\n1')

        # dynamic labels
        self.labels['PCval'] = c.create_text(50, 145, text='PC=0')
        self.labels['IRval'] = c.create_text(330, 250, text='IR=---')
        self.labels['A'] = c.create_text(615, 265, text='A=')
        self.labels['B'] = c.create_text(615, 330, text='B=')
        self.labels['ALUout'] = c.create_text(870, 290, text='ALUOut=')
        self.labels['MDRval'] = c.create_text(325, 350, text='MDR=')

        # static lines
        lines = [
            [50, 155, 50, 175, 85, 175],# PC -> IorD
            [105, 190, 130, 190],# IorD -> Memory
            [250, 205, 300, 205],# Memory -> IR
            [260, 205, 260, 300, 300, 300],# Memory -> MDR
            [570, 235, 600, 235],# RegFile -> A
            [570, 300, 600, 300],# RegFile -> B
            [630, 235, 680, 235],# A -> ALUSrcA
            [630, 300, 680, 300],# B -> ALUSrcB
            [820, 268, 845, 268],# ALU -> ALUOUT
            [895, 268, 930, 268],# ALUOUT -> PCSrc
            [350, 230, 390, 230],# IR -> RegDst
            [350, 210, 370, 210,370,185,450,185],# ReadReg2
            [350, 190, 365, 190,365,170,450,170],# ReadReg1
            [370, 200, 390, 200],# WriteReg
            [350, 300, 390, 300],# MDR -> MemToReg
            [410, 215, 450, 215],# RegDst -> RegFile
            [410, 315, 450, 315],# MemToReg -> RegFile
            [700, 235, 740, 235],# ALUSrcA -> ALU
            [700, 300, 740, 300],# ALUSrcB -> ALU
            [950, 268, 980, 268,980,100,70,100],# PCSrs -> PC
        ]
        self.static_lines = [c.create_line(*ln, arrow=tk.LAST) for ln in lines]

        self.dynamic_items = []
        self.cycle_info = c.create_text(760, 40, text='Ready', font=('Arial', 12, 'bold'))

    # ---------- Helpers for animation & display ----------
    def _center_of(self, item_id):
        coords = self.canvas.coords(item_id)
        if not coords:
            return (0,0)
        # rectangle: [x1,y1,x2,y2]
        if len(coords) >= 4:
            x1,y1,x2,y2 = coords[0],coords[1],coords[-2],coords[-1]
            return ((x1+x2)/2, (y1+y2)/2)
        return (coords[0], coords[1])

    def _flash(self, box_name, color='yellow', t=0.4):
        item = self.boxes.get(box_name)
        if not item:
            return
        orig = self.canvas.itemcget(item, 'fill')
        self.canvas.itemconfig(item, fill=color)
        self.canvas.update()
        time.sleep(t)
        self.canvas.itemconfig(item, fill=orig)
        self.canvas.update()

    def _animate_value(self, start, end, text, duration=0.5):
        c = self.canvas
        dx = end[0]-start[0]
        dy = end[1]-start[1]
        steps = max(4, int(12*duration))
        xstep = dx/steps
        ystep = dy/steps
        item = c.create_text(start[0], start[1], text=text, fill='red', font=('Arial',10,'bold'))
        for _ in range(steps):
            c.move(item, xstep, ystep)
            c.update()
            time.sleep(duration/steps)
        time.sleep(0.06)
        c.delete(item)


    # ---------- Core: simulate ADD (visual-only) ----------
    def simulate_add(self, inst_text=None, animate_time=None):
        """
        Full visual simulation for ADD/ADDI instruction.
        This function DOES NOT mutate register file values — visual only.
        """
        if animate_time is None:
            animate_time = self.run_delay
        if inst_text is None:
            # try to read current instruction at PC (if any)
            inst_text = self.cpu.program.get(self.cpu.PC, 'add s1 s1 s2')

        parsed = parse_instruction(inst_text)

        # prepare display
        self.cpu.IR = inst_text
        self.canvas.itemconfig(self.labels['IRval'], text=f'IR={inst_text}')
        self.canvas.itemconfig(self.cycle_info, text='Stage: FETCH')
        #self._update_inspectors()
        time.sleep(0.15)

        # ---- FETCH: PC -> IorD -> Memory -> IR ; PC = PC + 4 ----
        pc_c = self._center_of(self.boxes['PC'])
        iord_c = self._center_of(self.boxes['IorD'])
        mem_c = self._center_of(self.boxes['Memory'])
        ir_c = self._center_of(self.boxes['IR'])

        self._flash('PC', t=0.25)
        self._animate_value(pc_c, iord_c, f'PC={self.cpu.PC}', duration=animate_time)
        self._animate_value(iord_c, mem_c, 'FetchInst', duration=animate_time*0.6)
        self._animate_value(mem_c, ir_c, 'IR<-inst', duration=animate_time*0.6)

        # update PC visually
        self.cpu.PC += 4
        self.canvas.itemconfig(self.labels['PCval'], text=f'PC={self.cpu.PC}')
        #self._update_inspectors()
        time.sleep(0.12)

        # ---- DECODE: read RS->A and RT/imm->B ----
        self.canvas.itemconfig(self.cycle_info, text='Stage: DECODE')
        reg_c = self._center_of(self.boxes['RegFile'])
        A_c = self._center_of(self.boxes['A'])
        B_c = self._center_of(self.boxes['B'])

        rs = rt = dst = None
        imm = None
        if parsed and parsed[0] in ('r','i'):
            if parsed[0]=='r':
                _,op,dst,rs,rt = parsed
            else:
                _,op,dst,rs,imm = parsed
                rt = None

        # RS -> A
        self._flash('RegFile', t=0.2)
        if rs:
            v = self.cpu.regs.get(rs, 0)
            self._animate_value(reg_c, A_c, f'{rs}={v}', duration=animate_time)
            self.cpu.A = v
        else:
            self._animate_value(reg_c, A_c, 'RS', duration=animate_time*0.6)
            self.cpu.A = 0

        # RT or imm -> B
        if rt:
            v = self.cpu.regs.get(rt, 0)
            self._animate_value(reg_c, B_c, f'{rt}={v}', duration=animate_time)
            self.cpu.B = v
        elif imm is not None:
            self._animate_value(self._center_of(self.boxes['IR']), B_c, f'imm={imm}', duration=animate_time*0.6)
            self.cpu.B = imm
        else:
            self._animate_value(reg_c, B_c, 'RT', duration=animate_time*0.6)
            self.cpu.B = 0

        #self._update_inspectors()
        time.sleep(0.12)

        # ---- EXECUTE: ALU computes A+B ----
        self.canvas.itemconfig(self.cycle_info, text='Stage: EXECUTE')
        alu_c = self._center_of(self.boxes['ALU'])
        aluout_c = self._center_of(self.boxes['ALUOUT'])

        self._animate_value(A_c, alu_c, f'A={self.cpu.A}', duration=animate_time*0.6)
        self._animate_value(B_c, alu_c, f'B={self.cpu.B}', duration=animate_time*0.6)
        self._flash('ALU', t=0.25)

        # compute
        try:
            result = int(self.cpu.A) + int(self.cpu.B)
        except Exception:
            result = 0
        self.cpu.ALUOut = result
        self.canvas.itemconfig(self.labels['ALUout'], text=f'ALUOut={result}')
        self._animate_value(alu_c, aluout_c, f'ALU={result}', duration=animate_time*0.6)
        #self._update_inspectors()
        time.sleep(0.12)

        # ---- WRITEBACK (visual only): ALUOut -> MemToReg -> RegFile ----
        self.canvas.itemconfig(self.cycle_info, text='Stage: WRITEBACK')
        mem2_c = self._center_of(self.boxes['MemToReg'])
        reg_c = self._center_of(self.boxes['RegFile'])

        self._animate_value(aluout_c, mem2_c, f'{result}', duration=animate_time*0.6)
        self._animate_value(mem2_c, reg_c, f'WB:{result}', duration=animate_time*0.6)
        self._flash('RegFile', t=0.25)

        # temporary floating label to indicate destination if known
        if parsed and parsed[0] in ('r','i'):
            if parsed[0]=='r':
                dst = parsed[2]
            else:
                dst = parsed[2]
            t = self.canvas.create_text(reg_c[0], reg_c[1]-30, text=f'{dst} <= {result}', fill='green', font=('Arial',10,'bold'))
            self.canvas.update()
            time.sleep(0.7)
            self.canvas.delete(t)

        self.canvas.itemconfig(self.cycle_info, text='ADD simulation complete')
        #self._update_inspectors()

# -------------------- Main --------------------

def main():
    root = tk.Tk()
    root.title('Clean ADD Visual Simulator')
    app = VisualSimulator(root)
    root.geometry('1200x720')
    root.mainloop()

if __name__ == '__main__':
    main()
