from tkinter.constants import CENTER, DISABLED, FLAT, SOLID, GROOVE, RAISED, RIDGE, SUNKEN
from tkinter import filedialog as fd
from tkinter import ttk
from typing import Text
import RPi.GPIO as GPIO
import tkinter as tk
from datetime import datetime
from PIL import ImageTk, Image
from pathlib import Path
import time
import os
import json

# export DISPLAY=localhost:10.0

# GPIO Setup
SimOut        = [11, 13, 15] # Output signal to RPis
InPins        = [18, 36, 40]
TriggerEnable = [16, 32, 38]
TriggerReset  = 22
TriggerLatch  = 29
EndEvent      = 31
Error_LED     = 38
Trig_0_LED    = 37

GPIO.setmode(GPIO.BOARD) # use Physical GPIO Numbering
GPIO.setup(InPins, GPIO.IN)
GPIO.setup(TriggerEnable, GPIO.OUT)
GPIO.output(TriggerEnable, GPIO.LOW)
GPIO.setup(SimOut, GPIO.OUT)
GPIO.output(SimOut, GPIO.LOW)
GPIO.setup(Error_LED, GPIO.OUT)
GPIO.output(Error_LED, GPIO.LOW)
GPIO.setup(Trig_0_LED, GPIO.OUT)
GPIO.output(Trig_0_LED, GPIO.LOW)
GPIO.setup(TriggerReset, GPIO.OUT)
GPIO.output(TriggerReset, GPIO.LOW)
GPIO.setup(TriggerLatch, GPIO.IN)
GPIO.setup(EndEvent, GPIO.OUT)
GPIO.output(EndEvent, GPIO.LOW)


# Tkinter setup
tk_root = tk.Tk()
tk_root.title('Event Builder')
tabControl = ttk.Notebook(tk_root)
tab1 = ttk.Frame(tabControl)
tab2 = ttk.Frame(tabControl)
tab3 = ttk.Frame(tabControl)
tabControl.add(tab1, text='Event run')
tabControl.add(tab2, text='Camera Settings')
tabControl.add(tab3, text='Image Viewer')
tabControl.pack(expand=1, fill='both')
padx = 4
pady = 4

##############################################
############# Tab 1: event logic #############
##############################################
class EB:
    def __init__(self, master):
        self.master = master

        self.trig_enable_time_entry = ttk.Spinbox(master=self.master, width=10, from_=0, to=float('inf'), increment=1, format='%10.4f')
        self.trig_enable_time_entry.insert(0, 5) # setting default trig_enable_time to 5 seconds
        self.trig_enable_time_entry.grid(row=0, column=1, padx=padx, pady=pady)
        ttk.Label(self.master, text='Trigger Enable Time: ').grid(row=0, column=0)

        self.max_time_entry = ttk.Spinbox(master=self.master, width=10, from_=0, to=float('inf'), increment=1, format='%10.4f')
        self.max_time_entry.insert(0, 10) # setting default max_time to 10 seconds
        self.max_time_entry.grid(row=1, column=1, padx=padx, pady=pady)
        ttk.Label(self.master, text='Maxium Event Time: ').grid(row=1, column=0)

        self.show_time = tk.StringVar()
        self.show_time.set('Event Time: ' +str(0))
        self.display_time = ttk.Label(self.master, textvariable=self.show_time, relief=SUNKEN, width=16, padding=pady)
        self.display_time.grid(row=11, column=0, padx=padx, pady=pady)

        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)

        self.buttonmantrig = ttk.Button(self.master, text='Stop Event', state=DISABLED)
        self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)
        
        self.buttonquit = ttk.Button(self.master, text='Quit', command=self.leave)
        self.buttonquit.grid(row=14, column=0, padx=padx, pady=pady)

        status_label = ttk.Label(self.master, text='RPi Status', relief=RIDGE, width=12, padding=pady, justify=CENTER)
        status_label.grid(row=11, column=1, padx=4*padx, pady=pady)
        for i in range(len(InPins)):
            self.set_status_neutral(i+1)

        self.error = ttk.Label(self.master, text='  ')
        self.error.grid(row=25, column=0, padx=padx, pady=pady)

        self.trig_0_state = False
        self.event_time = 0
        
    def set_status_neutral(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='gray')
        status.grid(row=cam+11, column=1, padx=padx, pady=pady)

    def set_status_on(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='green')
        status.grid(row=cam+11, column=1, padx=padx, pady=pady)

    def set_status_off(self, cam):
        status = ttk.Label(self.master, text='Cam_'+str(cam), relief=SUNKEN, padding=pady, background='red')
        status.grid(row=cam+11, column=1, padx=padx, pady=pady)

    # Helper for fifo_signal and iterate: returns false if all InPins are not recieving a high signal
    def check_in_pins(self):
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                return False
        return True
    
    # Returns true when all in pins are inactive
    def check_all_in_pins(self):
        for i in range(len(InPins)):
            if GPIO.input(InPins[i]):
                return False
        return True

    def send_trig_enable(self):
        for i in range(len(TriggerEnable)):
            GPIO.output(TriggerEnable[i], GPIO.HIGH)

    def disable_trig_enable(self):
        for i in range(len(TriggerEnable)):
            GPIO.output(TriggerEnable[i], GPIO.LOW)

    # # Check if trigger latch is enabled
    # def check_latch(self):
    #     if GPIO.input(TriggerLatch): return True
    #     else: return False

    # Send 10 millisecond trigger_reset signal
    def send_trig_reset(self):
        GPIO.output(TriggerReset, GPIO.HIGH)
        time.sleep(0.01)
        GPIO.output(TriggerReset, GPIO.LOW)

    # Checks evry 10 ms (for a total of 1 second) if all RPis respond and are ready. 
    # Sets trig_0_state false if all RPis are ready (event can keep running)
    def fifo_signal(self):
        for i in range(100):
            if (self.check_in_pins()): # input signals from RPis
                # need to add (?): send output signal to arduino once all RPi_State == Active
                for i in range(len(InPins)):
                    self.set_status_on(i+1)
                self.buttonstart.grid_forget()
                self.buttonstart = ttk.Button(self.master, text='Start Event', state=DISABLED)
                self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)
                make_folder()
                self.trig_0_state = False
                return False
            else:
                time.sleep(0.01)
        self.trig_0_state = True
        return True

    # Recursively calls itself (keeps the event running) until timer exceeds max time,
    # Man_Trigger button is pressed, Trigger_latch is enabled, or one of the RPi pins becomes inactive
    def iterate(self):
        self.event_time = time.perf_counter() - self.tic
        self.latch_status = GPIO.input(TriggerLatch)
        if self.latch_status:
            print('trigger latched')
            self.end_event()
        elif (self.event_time > self.max_time or self.trig_0_state or (not self.check_in_pins())):
            GPIO.output(EndEvent, GPIO.HIGH)
            time.sleep(0.01)
            GPIO.output(EndEvent, GPIO.LOW)
            self.master.after(10, self.iterate)
        else: 
            self.show_time.set('Event Time: '+str(round(self.event_time, 4)))
            self.master.after(10, self.iterate)

    # If Man_Trigger button is pressed, sets trig_0_state to true and ends the event
    # before timer passes max time.
    def set_trig(self):
        self.trig_0_state = True

    def run_event(self):
        self.error.grid_forget()
        self.error = ttk.Label(self.master, text='  ')
        self.error.grid(row=25, column=0, padx=padx, pady=pady)
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.HIGH)
        self.latch_status = GPIO.input(TriggerLatch)
        if not self.latch_status:
            fifo_status = self.fifo_signal()
        else: fifo_status = True
        if (not self.latch_status) and (not fifo_status):
            try:
                self.max_time = float(self.max_time_entry.get())
                self.send_trig_reset()
                # for i in range(len(SimOut)):
                #     GPIO.output(SimOut[i], GPIO.HIGH)
                self.buttonmantrig.grid_forget()
                self.buttonmantrig = ttk.Button(self.master, text='Stop Event', command=self.set_trig)
                self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)
                # self.trig_0_state = self.fifo_signal()
                self.tic = time.perf_counter()
                self.master.after(int(float(self.trig_enable_time_entry.get())*1000), self.send_trig_enable)
                self.iterate()
            except ValueError:
                self.error = ttk.Label(self.master, text='Error: Invalid input!')
                self.error.grid(row=25, column=0, padx=padx, pady=pady)
                for i in range(len(SimOut)):
                    GPIO.output(SimOut[i], GPIO.LOW)
        else:
            self.error.grid_forget()
            self.error = ttk.Label(self.master, text='')
            self.error.grid(row=25, column=0, padx=padx, pady=pady)
            if self.latch_status:
                label = self.error.cget('text')
                label = label + 'Trigger Latch enabled,\nTrigger Reset signal sent.\nPlease try again.\n'
                self.error.configure(text=label)
                self.send_trig_reset()
            if fifo_status:
                label = self.error.cget('text')
                label = label + 'Error: Inactive RPi!\n'
                self.error.configure(text=label)
                for i in range(len(InPins)):
                    if not GPIO.input(InPins[i]):
                        self.set_status_off(i+1)
                    else: self.set_status_neutral(i+1)
            self.cleanup()


    def end_event(self):
        # Saving information
        f = open(curr_directory+'/info.txt', 'x+')
        f.write('Max Time: '+str(self.max_time)+'\n')
        f.write(self.show_time.get()+'\n')
        f.write('End condition: ')
        if self.event_time > self.max_time:
            f.write('Exceeded max time; ')
        if self.trig_0_state:
            f.write('Man_Trigger button pressed; ')
        if not self.check_in_pins():
            f.write('Camera(s) ')
            for i in range(len(InPins)):
                if not GPIO.input(InPins[i]):
                    f.write(str(i+1)+' ')
            f.write('were inactive; ')
        if self.latch_status:
            f.write('Trigger_latch was enabled')
        f.close()
        print('Saved!')
        self.cleanup()

    # called by end_event and leave
    def cleanup(self):
        for i in range(len(InPins)):
            if not GPIO.input(InPins[i]):
                self.set_status_off(i+1)
            else: self.set_status_neutral(i+1)
        for i in range(len(SimOut)):
            GPIO.output(SimOut[i], GPIO.LOW)
        self.disable_trig_enable()
        self.send_trig_reset()
        self.wait_for_end()

    def wait_for_end(self):
        if not self.check_all_in_pins():
            self.master.after(5, self.wait_for_end)
            print(self.check_all_in_pins())
        else: self.reset_buttons()

    def reset_buttons(self):
        self.buttonstart.grid_forget()
        self.buttonstart = ttk.Button(self.master, text='Start Event', command=self.run_event)
        self.buttonstart.grid(row=12, column=0, padx=padx, pady=pady)
        self.buttonmantrig.grid_forget()
        self.buttonmantrig = ttk.Button(self.master, text='Stop Event', state=DISABLED)
        self.buttonmantrig.grid(row=13, column=0, padx=padx, pady=pady)


    def leave(self):
        self.cleanup()
        GPIO.cleanup()
        tk_root.quit()
        exit()

# Makes new folder for current event and sets softlink to the created folder
curr_directory = 'temp'
def make_folder():
    global curr_directory
    now = datetime.now()
    today = now.strftime('%Y') + now.strftime('%m') + now.strftime('%d')

    try:
        os.mkdir('/home/pi/camera-data/'+ today)
    except FileExistsError:
        print('Directory for today already exists')

    # Determine how many folders events are already in the folder to 
    # make a new folder with updated index
    index = 0
    for root, dirs, files in os.walk('/home/pi/camera-data/' + today):
        for d in dirs:
            index += 1
    try:
        os.mkdir('/home/pi/camera-data/'+ today + '/' + str(index))
    except Exception as e:
        print(e)

    curr_directory = '/home/pi/camera-data/'+ today +'/'+str(index)

    os.symlink(curr_directory, 'temp')
    os.rename('temp', '/home/pi/camera-data/Images')

    print('Made directory: ', curr_directory)


##############################################
######### Tab 2: Camera Settings #############
##############################################

### Makes a new tab with several entry boxes to adjust the camera configX.json files. 
### Makes three config files, one for each camera.

ttk.Label(tab2, text='Exposure: ').grid(row=10, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Buffer Length: ').grid(row=11, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Frames After: ').grid(row=12, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='ADC Threshold: ').grid(row=13, column=0, padx=padx, pady=pady)
ttk.Label(tab2, text='Pixel Threshold: ').grid(row=14, column=0, padx=padx, pady=pady)

exposure_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
exposure_spinbox.insert(0, 300)
exposure_spinbox.grid(row=10, column=1)

buffer_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
buffer_spinbox.insert(0, 100)
buffer_spinbox.grid(row=11, column=1)

fafter_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
fafter_spinbox.insert(0, 50)
fafter_spinbox.grid(row=12, column=1)

adc_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
adc_spinbox.insert(0, 10)
adc_spinbox.grid(row=13, column=1)

pix_spinbox = ttk.Spinbox(master=tab2, width=10, from_=0, to=10000, increment=10, format='%5.0f')
pix_spinbox.insert(0, 300)
pix_spinbox.grid(row=14, column=1)

# Some values are set as their defaults and cannot be changed (yet) by the event builder
config = {}
def make_config(cam):
    config['exposure'] = exposure_spinbox.get()
    config["resolution"] = [1280,800]
    config["frame_sync"] = True
    config["mode"] = 11 #5
    config["buffer_len"] = buffer_spinbox.get()
    config["frames_after"] = fafter_spinbox.get()
    config["adc_threshold"] = adc_spinbox.get()
    config["pix_threshold"] = pix_spinbox.get()
    config["save_path"] = "/mnt/event-builder/Images/"
    config["cam_name"] = 'cam'+str(cam)
    config["image_format"] = ".bmp"
    config["date_format"] = "%Y-%m-%d_%H:%M:%S"
    config["input_pins"] = {"state_com": 5,
                            "trig_en": 6,
                            "trig_latch": 13}
    config["output_pins"] = {"state": 23,
                            "trig": 24}

def save_config():
    for i in range(3):
        config_path = '/home/pi/camera-data/config'+str(i)+'.json'
        make_config(i)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    save_label = ttk.Label(tab2, text='Saved!')
    save_label.grid(row=101, column=1, padx=padx, pady=pady)
    save_label.after(1000, save_label.destroy)

### When you hit the 'Save' button, overwrites the pre-existing config.json files or creates new ones
save_button = ttk.Button(tab2, text='Save', command=save_config)
save_button.grid(row=100, column=1, padx=padx, pady=pady)

##############################################
########### Tab 3: Image viewer ##############
##############################################
baseheight = 200

# returns a list of all the images (png, jpg) in a directory resized to height = baseheight pixels
def image_walk(directory, camera):
    image_list = []
    os.chdir(directory)
    for root, dirs, files in os.walk(directory):
        for file in files:
            filename, extension = os.path.splitext(file)
            if extension == '.png' or '.jpg' or '.bmp':
                if filename[3] == str(camera):
                    # rescaling images to height = baseheight pixels
                    img = Image.open(file)
                    hpercent = (baseheight / float(img.size[1]))
                    wsize = int((float(img.size[0]) * float(hpercent)))
                    img = img.resize((wsize, baseheight), Image.ANTIALIAS)
                    image = ImageTk.PhotoImage(img)
                    image_list.append(image)
    return image_list

# Initialize image lists
image_list0 = []
image_list1 = []
image_list2 = []
img_0 = None
img_1 = None
img_2 = None

def check():
    global img_0
    global img_1
    global img_2
    if len(image_list0) > 0 and len(image_list1) > 0 and len(image_list2) > 0:
        img_0 = ttk.Label(tab3, image=image_list0[0])
        img_0.grid(row=0, column=0, columnspan=3, padx=padx, pady=pady)
        img_1 = ttk.Label(tab3, image=image_list1[0])
        img_1.grid(row=0, column=3, columnspan=3, padx=padx, pady=pady)
        img_2 = ttk.Label(tab3, image=image_list2[0])
        img_2.grid(row=0, column=6, columnspan=3, padx=padx, pady=pady)
        return True
    else: return False

images_present = check()

# Loads a new directory with images seperated into three lists based off ending character.
def load_dir():
    global image_list0
    global image_list1
    global image_list2
    global images_present
    directory = fd.askdirectory(parent=tk_root, initialdir=curr_directory)
    image_list0 = image_walk(directory, 0)
    image_list1 = image_walk(directory, 1)
    image_list2 = image_walk(directory, 2)
    images_present = check()
    image_buttons()
    back()

button_select_dir = ttk.Button(tab3, text='Choose directory', command=load_dir)
button_select_dir.grid(row=1, column=4, padx=padx, pady=pady)

image_number = 0

# updates forward and backward buttons depending on which image number is being displayed 
# (the code is the same for forward and backward, just use diff parts!)
def image_buttons():
    global img_0
    global img_1
    global img_2
    global image_number

    if images_present:
        img_0.grid_forget()
        img_0 = ttk.Label(tab3, image=image_list0[image_number])
        img_1.grid_forget()
        img_1 = ttk.Label(tab3, image=image_list1[image_number])
        img_2.grid_forget()
        img_2 = ttk.Label(tab3, image=image_list2[image_number])

    button_forward = ttk.Button(tab3, text='>>', command=forward)
    button_back = ttk.Button(tab3, text='<<', command=back)

    img_0.grid(row=0, column=0, columnspan=3, padx=padx, pady=pady)
    img_1.grid(row=0, column=3, columnspan=3, padx=padx, pady=pady)
    img_2.grid(row=0, column=6, columnspan=3, padx=padx, pady=pady)
    button_back.grid(row=1, column=3, padx=padx, pady=pady)
    button_forward.grid(row=1, column=5, padx=padx, pady=pady)


def back(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_back
    if image_number > 0:
        image_number -= 1
        image_buttons()
    else:
        button_back = ttk.Button(tab3, text='<<', state=DISABLED)
        button_back.grid(row=1, column=3, padx=padx, pady=pady)

def forward(event=None): # place 'event=None' in parens for arrow keys
    global image_number
    global button_forward
    image_number += 1
    if (image_number < len(image_list0) and image_number < len(image_list1) and image_number < len(image_list2)):
        image_buttons()
    else:
        button_forward = ttk.Button(tab3, text='>>', state=DISABLED)
        button_forward.grid(row=1, column=5, padx=padx, pady=pady)

def leave():
    GPIO.cleanup()
    tk_root.quit()
    exit()

# Initialize buttons 
def initialize_buttons():
    global images_present
    global button_back
    global button_forward
    button_back = ttk.Button(tab3, text='<<', command=back, state=DISABLED)
    button_quit = ttk.Button(tab3, text='Quit', command=leave)
    if images_present:
        button_forward = ttk.Button(tab3, text='>>', command=forward)
    else:
        button_forward = ttk.Button(tab3, text='>>', state=DISABLED)
    button_back.grid(row=1, column=3, padx=padx, pady=pady)
    button_quit.grid(row=2, column=4, padx=padx, pady=pady)
    button_forward.grid(row=1, column=5, padx=padx, pady=pady)

initialize_buttons()

tk_root.bind('<Left>', back)
tk_root.bind('<Right>', forward)

#####################

event = EB(tab1)
tk_root.mainloop()
