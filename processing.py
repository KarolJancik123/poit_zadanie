import serial
import threading
import time
import MySQLdb
import configparser as ConfigParser
import os
from flask_socketio import SocketIO
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

config = ConfigParser.ConfigParser()
config.read('config.cfg')
myhost = config.get('mysqlDB', 'host')
myuser = config.get('mysqlDB', 'user')
mypasswd = config.get('mysqlDB', 'passwd')
mydb = config.get('mysqlDB', 'db')


serial_port = '/dev/ttyACM0'  


baud_rate = 9600 

ser = None
monitoring = False
data_file = 'monitoring_data.txt'

#Pripojenie k databaze
def connect_to_db():
    try:
        conn = MySQLdb.connect(
            host=myhost,
            user=myuser,
            passwd=mypasswd,
            db=mydb
        )
        return conn
    except MySQLdb.Error as e:
        print(f"Error connecting to MariaDB: {e}")
        return None

# Inicializacia databázi
def init_db():
    conn = connect_to_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS data (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            ambient INT,
                            red INT,
                            green INT,
                            blue INT
                          )''')
        conn.commit()
        conn.close()

# Uloženie dat do databázi
def save_to_db(timestamp, ambient, red, green, blue):
    conn = connect_to_db()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO data (timestamp, ambient, red, green, blue) VALUES (%s, %s, %s, %s, %s)",
                           (timestamp, ambient, red, green, blue))
            conn.commit()
        except MySQLdb.Error as e:
            print(f"Error inserting data into MariaDB: {e}")
        finally:
            conn.close()

# Uloženie dat do suboru
def save_to_file(timestamp, ambient, red, green, blue):
    with open(data_file, 'a') as file:
        file.write(f"{timestamp}, {ambient}, {red}, {green}, {blue}\n")

# Inicializacia sériového portu
def open_serial():
    global ser
    try:
        ser = serial.Serial(serial_port, baud_rate)
        return True
    except serial.SerialException as e:
        ser = None
        print(f"Error opening serial port {serial_port}: {e}")
        return False

@app.route('/')
def index():
    return render_template('processingVisual.html')

@socketio.on('connect', namespace='/test')
def test_connect():
    print('Client connected')

@socketio.on('open', namespace='/test')
def handle_open():
    if open_serial():
        print('Serial connection opened')
        socketio.emit('status', {'data': 'Connection opened'}, namespace='/test')
    else:
        socketio.emit('status', {'data': 'Failed to open connection'}, namespace='/test')

@socketio.on('start', namespace='/test')
def handle_start():
    global monitoring
    if ser is not None and not monitoring:
        monitoring = True
        socketio.start_background_task(target=background_thread)
        socketio.emit('status', {'data': 'Monitoring started'}, namespace='/test')
    else:
        socketio.emit('status', {'data': 'Failed to start monitoring'}, namespace='/test')

@socketio.on('stop', namespace='/test')
def handle_stop():
    global monitoring
    monitoring = False
    socketio.emit('status', {'data': 'Monitoring stopped'}, namespace='/test')

@socketio.on('close', namespace='/test')
def handle_close():
    global ser, monitoring
    monitoring = False
    if ser is not None:
        ser.close()
        ser = None
        socketio.emit('status', {'data': 'Connection closed'}, namespace='/test')

def background_thread():
    global monitoring
    while monitoring:
        if ser is not None:
            try:
                line = ser.readline().decode().strip()
                if line:
                    print(f"Read line: {line}")
                    parts = line.split()
                    if len(parts) == 8:  
                        ambient = int(parts[1])
                        red = int(parts[3])
                        green = int(parts[5])
                        blue = int(parts[7])
                        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                        save_to_db(timestamp, ambient, red, green, blue)
                        save_to_file(timestamp, ambient, red, green, blue)
                        socketio.emit('serial_data', {'data': line}, namespace='/test')
            except serial.SerialException as e:
                print(f"Error reading serial data: {e}")
                break

if __name__ == '__main__':
    init_db()
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
