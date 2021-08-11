import sys
from PyQt5 import QtCore, QtGui, QtWidgets
import time
import h264decoder
import socket
import paramiko
import numpy as np

# To preview the camera, run this script on a remote computer
# It will run video to stdout on the camera pi, 
# and connect to tcp socket to read the data
# then the data will be decoded and displayed
# Requires https://github.com/DaWelter/h264decoder

class StreamingThread(QtCore.QThread):
    frame_received = QtCore.pyqtSignal(np.ndarray)
    
    def __init__(self):
        super(StreamingThread, self).__init__()
        self.running = True
        self.server = '129.105.21.69'
        self.port = 5000
        self.BUFFER_SIZE = 1024
        self.decoder = h264decoder.H264Decoder()
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()

    def run(self):
        t = time.time()

        print("Establishing connection. . .")
        self.ssh.connect(self.server, username="pi")
        self.ssh_cmd = "~/RPi_CameraServers/MIPI_Camera/RPI/video2stdout | nc -l -p %d"%self.port
        ssh_stdin, ssh_stdout, ssh_stderr = self.ssh.exec_command(self.ssh_cmd)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.server,self.port))
        print("Connection Established. Starting Preview. . .")
        i = 0
        t = time.time()

        while self.running:
            data = self.sock.recv(self.BUFFER_SIZE)
            framedatas = self.decoder.decode(data)

            if len(framedatas)>0:
                for framedata in framedatas:
                    (frame, w, h, ls) = framedata
                    # print('frame size %i bytes, w %i, h %i, linesize %i' % (len(frame), w, h, ls))
                    frame = np.frombuffer(frame, dtype=np.ubyte, count=len(frame))
                    frame = frame.reshape((h, ls//3,3))
                    frame = frame[:,:w,:]
                    self.frame_received.emit(frame)
                    i+=1
                
                if (time.time()-t)>1:
                    print("FPS: %2.3f"%(i/(time.time()-t)), end="\r")
                    t = time.time()
                    i = 0

        self.sock.close()

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        super(MainWindow, self).__init__()

        self.setWindowTitle("Preview")

        frame = np.zeros([1280,800])
        img = QtGui.QImage(frame, 1280, 800, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(img)

        # set up the label widget to display the pic
        self.label = QtWidgets.QLabel(self)
        self.label.setPixmap(pix)
        self.label.setGeometry(QtCore.QRect(0, 0, pix.width(), pix.height()))

        self.button = QtWidgets.QPushButton("Quit", self)
        self.button.clicked.connect(self.quitStreaming)
        self.button.setGeometry(30, 30, 30, 30)

        # embiggen the window to correctly fit the pic
        self.resize(pix.width(), pix.height())
        self.show()

        self.streamingThread = StreamingThread()
        self.streamingThread.frame_received.connect(self.update)
        self.streamingThread.start()

    @QtCore.pyqtSlot(np.ndarray)
    def update(self, frame):
        # self.picture = QPixmap(f)
        img = QtGui.QImage(frame, 1280, 800, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(img)
        self.label.setPixmap(pix)

    def quitStreaming(self):
        self.streamingThread.running = False
        self.streamingThread.wait()
        self.streamingThread.exit()
        print("Successfully exited thread.")
        app.quit()

app = QtWidgets.QApplication(sys.argv)
w = MainWindow()
w.show()
app.exec_()
