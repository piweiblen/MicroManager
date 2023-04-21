from pygrabber.dshow_graph import FilterGraph
import serial.tools.list_ports as list_ports
from PIL import Image, ImageTk
from tkinter import filedialog
import tkinter.font as font
import tkinter as tk
import numpy as np
import subprocess
import threading
import serial
import time
import math
import cv2
import os


HEADER = """# Define the number of dimensions we are working on
dim = 2

# Define the image coordinates
"""


def normalize(arr):
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr
    return arr / norm


def get_new_file_name(path):
    n = 1
    time_stamp = time.strftime("%Y%m%d_%H%M%S")
    file_name = time_stamp + ".png"
    while os.path.exists(os.path.join(path, file_name)):
        n += 1
        file_name = time_stamp + "%s.png" % n
    return os.path.join(path, file_name)


def enable_grid_resize(frame, uniform=False):
    columns, rows = frame.grid_size()
    if uniform:
        frame.columnconfigure(tuple(range(columns)), weight=1, uniform="column")
        frame.rowconfigure(tuple(range(rows)), weight=1, uniform="row")
    else:
        frame.columnconfigure(tuple(range(columns)), weight=1)
        frame.rowconfigure(tuple(range(rows)), weight=1)


class ClampedEntry(tk.Entry):

    def __init__(self, *args, init_val=None, min_val=None, max_val=None, type_val=None, command=None, **kwargs):
        self.text = tk.StringVar()
        super().__init__(*args, textvariable=self.text, **kwargs)
        self.init_val = init_val
        self.min_val = min_val
        self.max_val = max_val
        self.type_val = type_val
        self.command = command
        if self.init_val is not None:
            self.text.set(str(self.init_val))
        self.last_val = self.text.get()
        self.bind('<FocusOut>', self.clamp)

    def clamp(self, event):
        if self.type_val is not None:
            try:
                self.type_val(self.text.get())
                if self.min_val is not None:
                    if self.type_val(self.text.get()) < self.min_val:
                        self.text.set(str(self.min_val))
                if self.max_val is not None:
                    if self.type_val(self.text.get()) > self.max_val:
                        self.text.set(str(self.max_val))
                if self.command is not None:
                    self.command()
            except ValueError:
                self.text.set(self.last_val)
        self.last_val = self.text.get()

    def set(self, value):
        self.text.set(str(value))
        self.clamp(None)

    def get(self):
        if self.type_val is not None:
            try:
                return self.type_val(self.text.get())
            except ValueError:
                return self.text.get()


class ResizableImage(tk.Label):

    def __init__(self, frame, *args, image=None, maintain_aspect=False,
                 width_func=None, height_func=None, resample=None, **kwargs):
        super().__init__(frame, *args, borderwidth=0, **kwargs)
        self.master = frame
        if image is None:
            image = Image.new('RGB', (1, 1), color=(255, 255, 255))
        self.image_copy = image
        self.image = image
        self.maintain_aspect = maintain_aspect
        self.width_func = width_func
        self.height_func = height_func
        self.resample = resample
        if self.maintain_aspect is True:
            self.maintain_aspect = 'min'
        self.bg_image = ImageTk.PhotoImage(self.image)
        self.configure(image=self.bg_image)
        self.last_size = self.image.size
        self.bind('<Configure>', self.on_resize)

    def on_resize(self, event=None):
        """Fit image inside widget on resize."""
        if event is not None and event.widget is self:
            self.resize(event.width, event.height)

    def resize(self, width, height):
        init_width = width
        init_height = height
        if self.width_func is not None:
            init_width = self.width_func()
        if self.height_func is not None:
            init_height = self.height_func()
        width = init_width
        height = init_height
        if self.maintain_aspect:
            if self.maintain_aspect == 'min':
                width = min(init_width, init_height * self.image_copy.width // self.image_copy.height)
                height = min(init_height, init_width * self.image_copy.height // self.image_copy.width)
            elif self.maintain_aspect == 'max':
                width = max(init_width, init_height * self.image_copy.width // self.image_copy.height)
                height = max(init_height, init_width * self.image_copy.height // self.image_copy.width)
            elif self.maintain_aspect == 'width':
                width = init_width
                height = init_width * self.image_copy.height // self.image_copy.width
            elif self.maintain_aspect == 'height':
                width = init_height * self.image_copy.width // self.image_copy.height
                height = init_height
        if width <= 0 or height <= 0:
            return None
        if self.last_size[0] != width or self.last_size[1] != height:
            # size changed, update image
            self.last_size = (width, height)
            self.render()

    def get_size(self):
        return self.last_size

    def get_image(self):
        return self.image_copy

    def set_image(self, image):
        prev_aspect = self.image_copy.size
        self.image_copy = image
        if self.image_copy.size != prev_aspect:
            self.resize(self.winfo_width(), self.winfo_height())
        self.render()

    def render(self):
        # update the label to reflect current image and size
        if self.resample is None:
            self.image = self.image_copy.resize(self.last_size)
        else:
            self.image = self.image_copy.resize(self.last_size, resample=self.resample)
        new_bg_image = ImageTk.PhotoImage(self.image)  # extra assignment to prevent flickering
        self.configure(image=new_bg_image)
        self.bg_image = new_bg_image


class CapGui:

    def __init__(self):
        # create root
        self.root = tk.Tk()
        self.root.title("capture gui")
        self.root.geometry("1200x600")
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        # initialize camera
        self.graph = FilterGraph()
        cams = self.graph.get_input_devices()
        index = 0
        for f in range(len(cams)):
            if "GENERAL - UVC" in cams[f]:
                index = f
                break
        else:
            print("No camera found")
        self.graph.add_video_input_device(index)
        self.graph.add_sample_grabber(lambda image: self.update_image(image))
        self.graph.add_null_render()
        self.graph.prepare_preview_graph()
        self.graph.run()
        self.rotation = 2
        self.transposed = False

        # initialize microcontroller
        self.listening = False
        self.comms = None
        self.s_lock = False
        self.cont_lock = []
        self.pos_x = 0
        self.pos_y = 0
        self.root.after(0, self.start_serial)

        # set up imageJ
        file = open(r"data\cwd.txt", "r")
        self.cwd = file.read()
        file.close()
        if not self.cwd:
            self.cwd = os.path.join(os.getenv("HOMEPATH"), "Downloads")

        # create menu bars
        self.menu_bar = tk.Menu(self.root)

        # file menu
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(label="Choose Working Directory", command=self.set_cwd)
        file_menu.add_command(label="Save Picture", command=self.take_pic)
        file_menu.add_command(label="Exit", command=self.quit)

        # preview menu
        view_menu = tk.Menu(self.menu_bar, tearoff=0)
        # preview_menu.add_command(label="Rotate Clockwise", command=lambda: self.rotate_image(-1, 0))
        # preview_menu.add_command(label="Rotate Counter-Clockwise", command=lambda: self.rotate_image(1, 0))
        view_menu.add_command(label="Rotate 180", command=lambda: self.rotate_image(2, 0))
        view_menu.add_command(label="Flip Vertically", command=lambda: self.rotate_image(-1, 1))
        view_menu.add_command(label="Flip Horizontally", command=lambda: self.rotate_image(1, 1))

        # movement menu
        movement_menu = tk.Menu(self.menu_bar, tearoff=0)
        movement_menu.add_command(label="Home", command=lambda: self.send_serial("home"))
        movement_menu.add_command(label="Calibrate", command=self.calibrate)

        # build menu bar structure
        self.menu_bar.add_cascade(label="File", menu=file_menu)
        self.menu_bar.add_cascade(label="View", menu=view_menu)
        self.menu_bar.add_cascade(label="Movement", menu=movement_menu)
        self.root.config(menu=self.menu_bar)

        # set up preview and calibration
        self.preview = ResizableImage(self.root, maintain_aspect='min')
        self.preview.grid(row=0, column=0, rowspan=2, sticky='news')
        self.cal_dist = 50000
        self.bounds = ((0, 648000), (0, 500000))
        self.last_cal = None
        self.in_cal = False
        file = open(r"data\calibration.txt", "r")
        self.cal = np.array(eval(file.read()))
        file.close()
        self.preview.bind("<ButtonPress>", self.cal_press)

        # movement buttons
        self.mov_frame = tk.Frame(self.root)
        self.mov_frame.grid(row=1, column=1)
        big_font = font.Font(size=30)
        self.pixel = tk.PhotoImage(width=1, height=1)
        kwargs = {"font": big_font, "image": self.pixel, "width": 30, "height": 30, "compound": "center"}
        gwargs = {"padx": 5, "pady": 5}
        self.inv = tk.IntVar()
        self.inv.set(1)
        self.iv = self.inv.get()
        # inner
        sp = 10000
        button = tk.Button(self.mov_frame, text="⏵", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((-1, 0), sp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=2, column=3, **gwargs)
        button = tk.Button(self.mov_frame, text="⏴", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((1, 0), sp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=2, column=1, **gwargs)
        button = tk.Button(self.mov_frame, text="⏶", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((0, -1), sp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=1, column=2, **gwargs)
        button = tk.Button(self.mov_frame, text="⏷", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((0, 1), sp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=3, column=2, **gwargs)
        # outer
        fp = 50000
        button = tk.Button(self.mov_frame, text="⏵", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((-1, 0), fp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=2, column=4, **gwargs)
        button = tk.Button(self.mov_frame, text="⏴", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((1, 0), fp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=2, column=0, **gwargs)
        button = tk.Button(self.mov_frame, text="⏶", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((0, -1), fp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=0, column=2, **gwargs)
        button = tk.Button(self.mov_frame, text="⏷", **kwargs)
        button.bind("<ButtonPress>", lambda x: self.cont_press((0, 1), fp))
        button.bind("<ButtonRelease>", self.cont_release)
        button.grid(row=4, column=2, **gwargs)
        # dots
        button = tk.Button(self.mov_frame, text="·",
                           command=lambda: self.move_abs(1, 1), **kwargs)
        button.grid(row=4, column=0, **gwargs)
        button = tk.Button(self.mov_frame, text="·",
                           command=lambda: self.move_abs(0, 1), **kwargs)
        button.grid(row=4, column=4, **gwargs)
        button = tk.Button(self.mov_frame, text="·",
                           command=lambda: self.move_abs(1, 0), **kwargs)
        button.grid(row=0, column=0, **gwargs)
        button = tk.Button(self.mov_frame, text="·",
                           command=lambda: self.move_abs(0, 0), **kwargs)
        button.grid(row=0, column=4, **gwargs)
        button = tk.Button(self.mov_frame, text="·", command=lambda: self.move_abs(0.5, 0.5), **kwargs)
        button.grid(row=2, column=2, **gwargs)
        button = tk.Checkbutton(self.root, text='Invert', variable=self.inv, onvalue=-1, offvalue=1,
                                command=self.update_grid_size)
        button.grid(row=1, column=1, sticky="se", **gwargs)


        # set up stitch frame
        self.stitch_frame = tk.Frame(self.root)
        self.stitch_frame.grid(row=0, column=1, sticky="news")
        # labels
        kwargs = {"padx": (5, 0), "pady": 5, "sticky": "ne"}
        label = tk.Label(self.stitch_frame, text="Overlap %")
        label.grid(row=1, column=0, **kwargs)
        label = tk.Label(self.stitch_frame, text="X size:")
        label.grid(row=1, column=2, **kwargs)
        label = tk.Label(self.stitch_frame, text="Y size:")
        label.grid(row=1, column=4, **kwargs)
        # entries
        kwargs = {"padx": (0, 5), "pady": 5, "sticky": "nw"}
        self.p_entry = ClampedEntry(self.stitch_frame, init_val=15, min_val=5, max_val=95, type_val=int,
                                    command=self.update_grid_size)
        self.p_entry.grid(row=1, column=1, **kwargs)
        self.x_entry = ClampedEntry(self.stitch_frame, init_val=3, min_val=1, max_val=9, type_val=int,
                                    command=self.update_grid_size)
        self.x_entry.grid(row=1, column=3, **kwargs)
        self.y_entry = ClampedEntry(self.stitch_frame, init_val=3, min_val=1, max_val=9, type_val=int,
                                    command=self.update_grid_size)
        self.y_entry.grid(row=1, column=5, **kwargs)
        # go button
        normal_font = font.Font(size=12)
        button = tk.Button(self.stitch_frame, text="Take Macro Image",
                           command=self.zig_zag, font=normal_font, compound="center")
        button.grid(row=2, column=0, columnspan=6, pady=(5, 30), sticky="n")
        # set up grid view
        self.keys_down = set()
        self.ctrls = {"Control_L", "Control_R"}
        self.root.bind("<KeyPress>", self.key_pressed)
        self.root.bind("<KeyRelease>", self.key_released)
        self.gridlock = False
        self.grid_p = None
        self.grid_size = None
        self.r_cell = (0, 0)
        self.y_cell = None
        self.done_cells = []
        self.grid_view = ResizableImage(self.stitch_frame, maintain_aspect='min', resample=0)
        self.update_grid_size()
        self.grid_view.grid(row=0, column=0,  columnspan=6, sticky="news")
        self.grid_view.bind("<ButtonPress>", self.grid_press_thread)

        # configure grid weights
        enable_grid_resize(self.stitch_frame)
        enable_grid_resize(self.root)
        self.root.columnconfigure(1, weight=0)

        # get indices
        self.send_serial("move x, 0")
        self.send_serial("move y, 0")

    def set_cwd(self):
        new_cwd = filedialog.askdirectory(title="Select directory to save files to")
        if new_cwd:
            self.cwd = new_cwd
            file = open(r"data\cwd.txt", "w")
            self.cwd = file.write(self.cwd)
            file.close()

    def grid_gen(self):
        gx, gy = self.grid_size
        cell_sz = (16, 9)
        cell = Image.new('RGB', cell_sz, color=(255, 255, 255))
        bg = Image.new('RGB', (gx * (cell_sz[0] + 1) - 1,
                               gy * (cell_sz[1] + 1) - 1), color=(0, 0, 0))
        for x in range(gx):
            for y in range(gy):
                bg.paste(cell, (x * (cell_sz[0] + 1), y * (cell_sz[1] + 1)))
        grey_cell = Image.new('RGB', cell_sz, color=(127, 127, 127))
        for d_cell in self.done_cells:
            bg.paste(grey_cell, (d_cell[0] * (cell_sz[0] + 1), (gy - 1 - d_cell[1]) * (cell_sz[1] + 1)))
        if self.r_cell is not None:
            r_border = Image.new('RGB', cell_sz, color=(255, 0, 0))
            interior = Image.new('RGB', (cell_sz[0] - 2, cell_sz[1] - 2), color=(255, 255, 255))
            r_border.paste(interior, (1, 1))
            bg.paste(r_border, (self.r_cell[0] * (cell_sz[0] + 1), (gy - 1 - self.r_cell[1]) * (cell_sz[1] + 1)))
        if self.y_cell is not None:
            y_border = Image.new('RGB', cell_sz, color=(255, 201, 14))
            interior = Image.new('RGB', (cell_sz[0] - 2, cell_sz[1] - 2), color=(255, 255, 255))
            y_border.paste(interior, (1, 1))
            bg.paste(y_border, (self.y_cell[0] * (cell_sz[0] + 1), (gy - 1 - self.y_cell[1]) * (cell_sz[1] + 1)))
        self.grid_view.set_image(bg)

    def update_grid_size(self):
        newt = threading.Thread(target=self.refresh_grid_size)
        newt.start()

    def refresh_grid_size(self):
        if self.iv != self.inv.get():
            while self.gridlock:
                time.sleep(0.1)
            self.iv = self.inv.get()
        if self.grid_p != self.p_entry.get():
            while self.gridlock:
                time.sleep(0.1)
            self.grid_p = self.p_entry.get()
        if self.grid_size != (self.x_entry.get(), self.y_entry.get()):
            while self.gridlock:
                time.sleep(0.1)
            self.grid_size = (self.x_entry.get(), self.y_entry.get())
            if self.r_cell[0] >= self.x_entry.get():
                self.r_cell = (self.x_entry.get() - 1, self.r_cell[1])
            if self.r_cell[1] >= self.y_entry.get():
                self.r_cell = (self.r_cell[0], self.y_entry.get() - 1)
            self.grid_gen()

    def grid_press_thread(self, *args):
        newt = threading.Thread(target=self.grid_press, args=args)
        newt.start()

    def grid_press(self, event):
        if self.gridlock:
            return
        width, height = self.grid_view.get_size()
        wgt_h = self.grid_view.winfo_height()
        wgt_w = self.grid_view.winfo_width()
        rel_pos = (event.x - wgt_w//2 + width//2,
                   event.y - wgt_h//2 + height//2)
        rel_pos = (rel_pos[0] / width, (height - rel_pos[1] - 1) / height)
        if rel_pos[0] < 0 or 1 <= rel_pos[0]:
            return
        if rel_pos[1] < 0 or 1 <= rel_pos[1]:
            return
        x_ind = int(self.grid_size[0] * rel_pos[0])
        y_ind = int(self.grid_size[1] * rel_pos[1])
        if self.ctrls.intersection(self.keys_down):
            self.gridlock = True
            self.move_on_grid((x_ind, y_ind))
            self.gridlock = False
        else:
            if (x_ind, y_ind) != self.r_cell:
                self.r_cell = (x_ind, y_ind)
                self.grid_gen()
        self.last_cal = (event.x/width, event.y/height)

    def move_on_grid(self, new_ind):
        self.y_cell = new_ind
        self.grid_gen()
        self.move((self.r_cell[0] - new_ind[0], 9 * (self.r_cell[1] - new_ind[1]) / 16),
                  (1 - self.grid_p/100) * self.cal_dist / np.linalg.norm(self.cal), wait=True)
        self.y_cell = None
        self.r_cell = new_ind
        self.grid_gen()

    def key_pressed(self, event):
        self.keys_down.add(event.keysym)

    def key_released(self, event):
        if event.keysym in self.keys_down:
            self.keys_down.remove(event.keysym)

    def calibrate(self):
        if self.in_cal:
            return
        self.in_cal = True
        newt = threading.Thread(target=self.cal_thread)
        newt.start()

    def cal_thread(self):
        wait_cal = self.last_cal
        while wait_cal == self.last_cal:
            time.sleep(0.1)
        cal_1 = self.last_cal
        self.send_serial_wait("move x, %s" % self.cal_dist)
        wait_cal = self.last_cal
        while wait_cal == self.last_cal:
            time.sleep(0.1)
        cal_2 = self.last_cal
        self.cal = np.array(cal_2) - np.array(cal_1)
        file = open(r"data\calibration.txt", "w")
        file.write(repr(list(self.cal)))
        file.close()
        self.in_cal = False

    def cal_press(self, event):
        width = self.preview.get_size()[0]
        self.last_cal = (event.x/width, event.y/width)

    def move(self, direction, distance, wait=False):
        norm = normalize(self.cal)
        transform = np.array((norm, norm[::-1])) * np.array(((1, -1), (1, 1)))
        moves = distance * np.matmul(transform, self.iv * np.array(direction))
        moves = [int(f) for f in moves]
        send = [self.send_serial, self.send_serial_wait][wait]
        for f in range(2):
            pos = [self.pos_x, self.pos_y][f]
            if self.bounds[f][1] < moves[f] + pos or moves[f] + pos < self.bounds[f][0]:
                break
            if moves[f]:
                send("move %s, %s" % ("xy"[f], moves[f]))

    def move_abs(self, x, y):
        if x < 0 or 1 < x:
            return
        if y < 0 or 1 < y:
            return
        if self.iv != 1:
            x = 1 - x
            y = 1 - y
        go_x = x * (self.bounds[0][1] - self.bounds[0][0]) + self.bounds[0][0]
        go_y = y * (self.bounds[1][1] - self.bounds[1][0]) + self.bounds[1][0]
        go_x -= self.pos_x
        go_y -= self.pos_y
        self.send_serial("move x, %s" % go_x)
        self.send_serial("move y, %s" % go_y)

    def move_cont(self, *args):
        while args in self.cont_lock:
            self.move(*args, wait=True)

    def cont_press(self, *args):
        self.cont_lock.append(args)
        newt = threading.Thread(target=self.move_cont, args=args)
        newt.start()

    def cont_release(self, *args):
        self.cont_lock = []

    def rotate_image(self, rotation, transpose):
        if self.transposed:
            rotation = -rotation
        self.rotation = (self.rotation + rotation) % 4
        if transpose:
            self.transposed = not self.transposed
        self.preview.render()

    def update_image(self, image):
        image = np.flip(image, 2)
        image = np.rot90(image, k=self.rotation, axes=(0, 1))
        if self.transposed:
            image = np.transpose(image, axes=[1, 0, 2])
        self.preview.set_image(Image.fromarray(image))
        # update preview
        self.root.after(0, self.graph.grab_frame)

    def start_serial(self):
        name = "USB"
        ports = list_ports.comports()
        for port, desc, hwid in ports:
            if name in desc:
                try:
                    self.comms = serial.Serial(port, 9600)
                    break
                except:
                    continue
        else:
            print("No microcontroller found")

    def send_serial(self, data):
        newt = threading.Thread(target=self.send_serial_wait, args=(data,))
        newt.start()

    def send_serial_wait(self, data):
        while self.s_lock:
            # don't let two instance of this function run simultaneously
            time.sleep(0.1)
        self.s_lock = True
        while self.comms is None:
            time.sleep(0.1)
        self.comms.read(self.comms.inWaiting())
        self.comms.write(bytearray(data+'\n', encoding='utf8'))
        if "home" in data:
            self.comms.readline()
        if "move x" in data:
            read = self.comms.readline().decode().strip('\n')
            index = int(read.split(' ')[1])
            self.pos_x = index
        if "move y" in data:
            read = self.comms.readline().decode().strip('\n')
            index = int(read.split(' ')[1])
            self.pos_y = index
        self.s_lock = False

    def take_pic(self):
        image = np.flip(np.array(self.preview.get_image()), 2)
        cv2.imwrite(os.path.join(self.cwd, time.strftime("image %Y%m%d_%H%M%S.png")), image)

    def zig_zag(self):
        if self.gridlock:
            return
        newt = threading.Thread(target=self.zig_zag_wait)
        newt.start()

    def zig_zag_wait(self):
        self.gridlock = True
        new_dir = os.path.join(self.cwd, time.strftime("macro_%Y%m%d_%H%M%S"))
        os.makedirs(new_dir)
        script = HEADER
        script_lines = []
        num_len = len(str(self.grid_size[0] * self.grid_size[1]))
        coords = (0, 0)
        direction = (1, 0)
        for f in range(self.grid_size[0] * self.grid_size[1]):
            self.move_on_grid(coords)
            time.sleep(0.2)
            image = np.flip(np.array(self.preview.get_image()), 2)
            name = "tile_%s.png" % str(f).zfill(num_len)
            cv2.imwrite(os.path.join(new_dir, name), image)
            script_lines.append((name, 1280 * coords[0] * (100 - self.grid_p) // 100,
                                       720 * (self.grid_size[1] - coords[1] - 1) * (100 - self.grid_p) // 100))
            if direction[1]:
                if coords[0]:
                    direction = (-1, 0)
                else:
                    direction = (1, 0)
            elif coords[0] + direction[0] < 0 or self.grid_size[0] <= coords[0] + direction[0]:
                direction = (0, 1)
            self.done_cells.append(coords)
            coords = (coords[0] + direction[0], coords[1] + direction[1])
        script_lines.sort(key=lambda x: x[::-1])
        script += '\n'.join("%s; ; (%s.0, %s.0)" % f for f in script_lines)
        file = open(os.path.join(new_dir, "TileConfiguration.txt"), 'w')
        file.write(script)
        file.close()
        subprocess.call("imagej\\ImageJ-win32.exe --headless --console --run \"imagej/macros/stage_stitching.ijm\" \"inDir='%s',outDir='%s'\"" % (new_dir, new_dir))
        subprocess.call("start %s" % os.path.join(new_dir, "output.png"))
        self.done_cells = []
        self.gridlock = False

    def show(self):
        # begin update loop
        self.graph.grab_frame()
        # run the tkinter window
        self.root.mainloop()

    def quit(self):
        # execute on window close
        # leaves all relays in their current state on close
        self.root.destroy()


if __name__ == "__main__":
    gui = CapGui()
    gui.show()
