# -*- coding: utf-8 -*-
"""Reto.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1d0f4LAI-MwrjgPfyw4cBjk-gaLIWV4IO

### Situación Problema - Equipo 2 - Sistemas Multiagentes y Gráficos Computacionales
28 de noviembre de 2021, Tecnológico de Monterrey

<br>

Se simula a través de un sistema multiagentes un cruce con 4 semáforos, una unidad básica de la problemática presente en la movilidad urbana moderna. A través de conexiones locales o por una URL pública usando ngrok, se envían estos datos a Unity donde la información es modelada en 3D

<br><i>

Ana Fernanda Hernández Tovar A01411484 <br>
Martín Palomares García A01066569 <br>
Brian Alberto Salomón Sevilla A00828826 <br>
Carlos G. del Rosal A01566719

</i>
"""

# Commented out IPython magic to ensure Python compatibility.
#@title Imports e Instalaciones

# Instalación de paquetes externos a las librerías estándar
# %pip install mesa pyngrok --quiet

# Paquete esencial que ayuda a modelar sistemas multiagentes
from mesa import Agent, Model
from mesa.space import MultiGrid
from mesa.time import SimultaneousActivation
from mesa.datacollection import DataCollector

# Paquete matemático utilizado para matrices de declaración sencilla
import numpy as np

# Paquetes útiles para trabajar y graficar la animación de la simulación
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation

import pandas as pd

# Nativo de Python para aleatorizar la aparición de los carros
import random

# Nativos de Python para medir la duración de las simulaciones
import time
import datetime

# Paquetes para la transferencia de datos por HTTP
# from pyngrok import ngrok
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import json
import os

# Configuración inicial para ignorar el certificado inválido de SSL
# import ssl

# try: _create_unverified_https_context = ssl._create_unverified_context
# Legacy Python that doesn't verify HTTPS certificates by default
# except AttributeError: pass
# Handle target environment that doesn't support HTTPS verification 
# else: ssl._create_default_https_context = _create_unverified_https_context

# Configuración adicional que se instala de ngrok
# ngrok.install_ngrok()
# ngrok.kill()

#@title Recolector del modelo

# Función auxiliar para capturar el modelo en un instante
def get_grid(model):
  # Itera el modelo llenando una cuadrilla que inicia vacía
  grid = np.zeros((model.grid.width, model.grid.height), dtype="int")
  # Codifica según los índices de colores elegidos en la animación debajo
  for (cell_content, x, y) in model.grid.coord_iter():
    if len(cell_content) == 1:
      # Un agente. Solamente puede ser un terreno, cambiando el tipo
      if cell_content[0].terrain_type == "crossroad": grid[x][y] = 2
      elif cell_content[0].terrain_type == "crosswalk": grid[x][y] = 3
      elif cell_content[0].terrain_type == "curb": grid[x][y] = 4
      elif cell_content[0].terrain_type == "street": grid[x][y] = 5
      elif cell_content[0].terrain_type == "garden": grid[x][y] = 9    
    elif len(cell_content) == 2:
      # Dos agentes. Un carro en la calle o un semáforo en la banqueta
      relevant_cell = 1 if isinstance(cell_content[0], Terrain) else 0
      if isinstance(cell_content[relevant_cell], Car): grid[x][y] = 0
      elif cell_content[relevant_cell].state == "green": grid[x][y] = 6
      elif cell_content[relevant_cell].state == "yellow": grid[x][y] = 7
      elif cell_content[relevant_cell].state == "red": grid[x][y] = 8
    else:
      # Único caso con más de un agente, choque
      grid[x][y] = 1
  # Transposición para que (x,y) queden como cartesianas y se anime Width*Height
  return np.transpose(grid)

#@title Clase Terreno

# Clase para el ambiente "debajo" de los agentes móviles
class Terrain(Agent):
  # Constructor
  def __init__(self, id, model, terrain_type):
    # Construcción de la clase padre Agent
    super().__init__(id, model)
    self.id = id

    # Tipo de terreno: "garden", "curb", "street", "crossroad", "crosswalk"
    self.terrain_type = terrain_type

#@title Clase Carro

class Car(Agent):
  # Constructor
  def __init__(self, id, model, state, origin, destination, start_pos):
    # Construcción de la clase padre Agent
    super().__init__(id, model)
    self.id = id

    # Estado del vehículo {-1: Por destruir, 0: Detenido, 1: Avanzando}
    self.state = state
    self.action = "spawned"

    # Datos de ubicación y dirección del movimiento del vehículo
    self.origin = origin
    self.destination = destination
    self.last_pos = start_pos
    self.pos = start_pos
    self.next_pos = None

    # Giro que se lleva a cabo ("right", "left", "straight")
    self.turn = self.model.directions[origin][destination]

    # Desplazamiento inicial
    self.dx = -1 if self.origin == "West" else 1 if self.origin == "East" else 0
    self.dy = 1 if self.origin == "North" else -1 if self.origin == "South" else 0

  # Instante de acción, definición de cambios del agente en una nueva iteración
  def step(self):
    if self.state == -1:
      # Una vez retrasada la destrucción (Para que Unity la note), se lleva a cabo
      self.state = -2
      return

    # Almacena a pos actual en una variable para Unity
    self.last_pos = self.pos
    
    # Sistema de vueltas
    if self.pos in self.model.cross_points: self.check_turn()
    
    # Siguiente posición posible, puede que por detenerse no se mueva ahí
    future_pos = (self.pos[0] + self.dx, self.pos[1] + self.dy)

    # Si la nueva posición saca al carro del modelo, prepara su destrucción
    if self.model.grid.out_of_bounds(future_pos):
      self.state = -1
      self.action = "destroyed"
      return

    # Máquina de estados del carro
    if self.state == 0 and not(self.see_red_light()) and self.see_free_road(future_pos):
      # Para cambiar al carro detenido, checa el semáforo y por carros delante
      self.state = 1
    elif self.state == 1 and (self.see_red_light() or not(self.see_free_road(future_pos))):
      # Para cambiar al carro avanzando, checa el semáforo y por carros delante
      self.state = 0

    # Solo guarda el desplazamiento si la máquina anterior así lo dice
    self.next_pos = future_pos if self.state == 1 else self.next_pos

  # Instante de acción, aplicación de cambios del agente en una nueva iteración
  def advance(self):
    # Solamente avanza si el estado lo marca, no mueve un carro detenido
    if self.state == 1:
      # Actualiza los valores y mueve al agente
      self.model.grid.move_agent(self, self.next_pos)
      if (self.pos in self.model.cross_points or self.pos in self.model.continue_points):
        self.action = "turning"
      else:
        self.action = "moving"
      self.pos = self.next_pos
    elif self.state == 0:
      self.action = "stopped"
    elif self.state == -2:
      # Destruye al agente desde el modelo mismo
      self.model.destroy_car(self)
  
  # Devuelve true ante un semáforo rojo, false en verde, amarillo o no semáforo
  def see_red_light(self):
    if self.origin == "North":
      light_pos = self.model.stoplight_pos["South"]
    elif self.origin == "West":
      light_pos = self.model.stoplight_pos["East"]
    elif self.origin == "South":
      light_pos = self.model.stoplight_pos["North"]
    elif self.origin == "East":
      light_pos = self.model.stoplight_pos["West"]
    
    # No importa el semáforo si el carro no ha llegado a una línea de pararse
    if self.pos not in self.model.stop_points: return False
    
    # Busca al semáforo y devuelve la respuesta según su color
    for agent in self.model.grid.get_cell_list_contents(light_pos):
      if isinstance(agent, Stoplight):
        # True si el semáforo está en rojo, false por lo contrario
        return agent.state != "green"

  # Función de visión del espacio delante, true si se puede avanzar sin chocar
  def see_free_road(self, future_pos):
    for agent in self.model.grid.get_cell_list_contents(future_pos):
      # Solo regresa false para un carro parado, bien pueden avanzar juntos
      if isinstance(agent, Car) and agent.state == 0:
        return False
    return True

  # Modifica los desplazamientos según la posición y la dirección de destino
  def check_turn(self):
    # Casos donde nunca se da vuelta
    if self.model.directions[self.origin][self.destination] == "straight": return
    
    # Vuelta al norte
    if self.destination == "North" and self.pos[0] == self.model.v_road[1]:
      self.dx, self.dy = [0, -1]
    # Vuelta al oeste
    elif self.destination == "West" and self.pos[1] == self.model.h_road[1]:
      self.dx, self.dy = [1, 0]
    # Vuelta al sur
    elif self.destination == "South" and self.pos[0] == self.model.v_road[0]:
      self.dx, self.dy = [0, 1]
    # Vuelta al este
    elif self.destination == "East" and self.pos[1] == self.model.h_road[0]:
      self.dx, self.dy = [-1, 0]

#@title Clase Semáforo

class Stoplight(Agent):
  # Constructor
  def __init__(self, id, model, state, max_ticks, smart):
    # Construcción de la clase padre Agent
    super().__init__(id, model)
    self.id = id

    # Estado del semáforo: "red", "yellow", "green"
    self.state = state
    self.next_state = None
    self.pos = self.model.stoplight_pos[id]

    # Distancia de observación del semáforo, se desactiva si no hay carro ahí
    self.preview_distance = 3
    self.previewed_cells = self.get_previewed_cells()

    # Contadores de steps que se puede estar en verde continuamente
    self.max_ticks = max_ticks
    self.ticks_on = 0
    self.smart = smart

  # Instante de acción, definición de los cambios del agente
  def step(self):
    # Booleano sabiendo si carros requieren pasar con este semáforo
    cars_waiting = sum(self.model.cars_there(cell) for cell in self.previewed_cells)

    # Máquina de estados del semáforo, iniciando por cambiar la inactividad
    # Agrega a la fila al semáforo rojo que quiere activación
    if self.state == "red" and (not(self.smart) or cars_waiting):
      permission = self.model.ask_activation(self.id)
      self.next_state = "green" if permission else self.next_state
    # Termina el plazo de dos ticks en amarillo
    elif self.state == "yellow" and self.ticks_on == self.max_ticks:
      self.model.activation_queue.pop(0)
      self.next_state = "red"
      self.ticks_on = 0
    # Termina un semáforo en verde por un máximo de ticks o por ser inteligente
    elif self.state == "green" and (self.ticks_on == self.max_ticks - 2 or 
        (self.smart and not(cars_waiting))):
      # Pasa a amarillo dejando al contador de ticks con solo dos restantes
      self.next_state = "yellow"
      self.ticks_on = self.max_ticks - 2

  # Actualización de estados según la máquina en step()
  def advance(self):
    # Incrementa el contador de ticks para limitar el tiempo en verde/amarillo
    if self.state != "red": self.ticks_on += 1

    # Actualiza el estado según lo necesario a menos de que no exista uno nuevo
    if self.next_state is not None:
      self.state = self.next_state
  
  # Devuelve la lista de celdas que el semáforo observa según la distancia eleginda
  def get_previewed_cells(self):
    previewed_cells = []
    for i in range(self.preview_distance):
      if self.id == "North":
        previewed_cells.append((self.pos[0] - 1, self.pos[1] + 3 + i))
      elif self.id == "West":
        previewed_cells.append((self.pos[0] - 3 - i, self.pos[1] - 1))
      elif self.id == "South":
        previewed_cells.append((self.pos[0] + 1, self.pos[1] - 3 - i))
      elif self.id == "East":
        previewed_cells.append((self.pos[0] + 3 + i, self.pos[1] + 1))
    return previewed_cells

#@title Clase Modelo

class CrossroadModel(Model):
  # Constructor
  def __init__(self, M, N, SPAWN_RATE, LIGHT_TICK, SMART, MAX_DURATION):
    # Inicialización de atributos para almacenar los datos recibidos
    self.m = M
    self.n = N
    self.spawn_rate = SPAWN_RATE
    self.smart = SMART
    self.max_duration = MAX_DURATION
    self.cars_spawned = 0
    
    # Creacíon de un Multigrid() para poder tener más de un agente por celda
    self.grid = MultiGrid(self.m, self.n, False)

    # Permite activar al mismo tiempo todos los componentes del modelo
    self.schedule = SimultaneousActivation(self)

    # Recolector de datos para futura representación gráfica
    self.grid_collector = DataCollector(model_reporters = {"Grid": get_grid})

    # Obtención de los puntos importantes del modelo, que se almacenen
    self.define_points()
    self.define_directions()

    # Colocación de los terrenos en toda la cuadrícula
    for (content, x, y) in self.grid.coord_iter():
      if (x,y) in self.cross_points:
        new_terrain = Terrain((x,y), self, "crossroad")
      elif (x,y) in self.stop_points or (x,y) in self.continue_points:
        new_terrain = Terrain((x,y), self, "crosswalk")
      elif x in self.v_road or y in self.h_road:
        new_terrain = Terrain((x,y), self, "street")
      elif (x in [self.v_road[0] - 1, self.v_road[1] + 1] or
            y in [self.h_road[0] - 1, self.h_road[1] + 1]):
        new_terrain = Terrain((x,y), self, "curb")
      else:
        new_terrain = Terrain((x,y), self, "garden")
      self.grid.place_agent(new_terrain, (x, y))
    
    # Definición y colocación de los semáforos
    self.stoplights = [
      Stoplight("North", self, "red", LIGHT_TICK, SMART),
      Stoplight("West", self, "red", LIGHT_TICK, SMART),
      Stoplight("South", self, "red", LIGHT_TICK, SMART),
      Stoplight("East", self, "red", LIGHT_TICK, SMART)
    ]
    for stoplight in self.stoplights:
      self.grid.place_agent(stoplight, stoplight.pos)
      self.schedule.add(stoplight)
    self.activation_queue = []

  # Unidad de cambio del modelo. También se llama a actuar a los agentes
  def step(self):
    self.grid_collector.collect(self)
    self.schedule.step()
    self.spawn_cars()
  
  # Define las calles, puntos de cruce, de detención, de salida del cruce, de
  # colocación de los carros y de colocación de los semáforos
  def define_points(self):
    # Calle sobre el eje de "x" (en dos valores céntricos de "y")
    self.h_road = [self.n // 2 - 1, self.n // 2]

    # Calle sobre el eje de "y" (en dos valores céntricos de "x")
    self.v_road = [self.m // 2 - 1, self.m // 2]

    # Puntos críticos donde cruzan todos los carros
    self.cross_points = {(v,h) for v in self.v_road for h in self.h_road}

    # Definición de los puntos para pararse por un semáforo
    self.stop_points = {
        (self.v_road[0], self.h_road[0] - 1), # North
        (self.v_road[1] + 1, self.h_road[0]), # West
        (self.v_road[1], self.h_road[1] + 1), # South
        (self.v_road[0] - 1, self.h_road[1]) # East
    }

    # Puntos donde se sale del cruce
    self.continue_points = {
        (self.v_road[1], self.h_road[0] - 1), # North
        (self.v_road[1] + 1, self.h_road[1]), # West
        (self.v_road[0], self.h_road[1] + 1), # South
        (self.v_road[0] - 1, self.h_road[0])  # East
    }

    # Puntos de aparición de los carros
    self.spawns = {
        "North": (self.v_road[0], 0),
        "West": (self.m - 1, self.h_road[0]),
        "South": (self.v_road[1], self.n - 1),
        "East": (0, self.h_road[1])
    }
    
    # Puntos para colocar los semáforos
    self.stoplight_pos = {
        "North": (self.v_road[1] + 1, self.h_road[0] - 1),
        "West": (self.v_road[1] + 1, self.h_road[1] + 1), 
        "South": (self.v_road[0] - 1, self.h_road[1] + 1),
        "East": (self.v_road[0] - 1, self.h_road[0] - 1)
    }
  
  # Almacena en un diccionario la relación entre direcciones
  def define_directions(self):
    self.directions = {
        "North": {"South": "straight", "East": "right", "West": "left"},
        "West": {"East": "straight", "North": "right", "South": "left"},
        "South": {"North": "straight", "West": "right", "East": "left"},
        "East": {"West": "straight", "South": "right", "North": "left"}
    }


  # Genera carros en los límites de la cuadrícula con un destino
  def spawn_cars(self):
    for dir in self.spawns:
      # Considera también que no haya ya un carro ahí
      if (random.random() < self.spawn_rate and
          not(self.cars_there(self.spawns[dir]))):
        # Se elige una dirección de fin que no sea la misma
        other_dir = dir
        while other_dir == dir: other_dir = random.choice([key for key in self.spawns])
        
        # Se coloca el agente creado con un id que se mantiene único
        new_car = Car(self.cars_spawned, self, 1, dir, other_dir, self.spawns[dir])
        self.grid.place_agent(new_car, new_car.pos)
        self.schedule.add(new_car)
        self.cars_spawned += 1
  
  # Función que elimina carros que hayan cumplido el recorrido
  def destroy_car(self, car_instance):
    self.grid.remove_agent(car_instance)
    self.schedule.remove(car_instance)

  # Devuelve un entero indicando cuantos carros hay en la posición elegida
  def cars_there(self, pos):
    # Obtiene los agentes en la celda deseada y checa si son de tipo carro
    car_counter = 0
    agents_there = self.grid.get_cell_list_contents(pos)
    for agent in agents_there:
      if isinstance(agent, Car): car_counter += 1
    return car_counter

  # Función para registrar que un semáforo quiere activarse, aún si debe esperar
  def ask_activation(self, light_id):
    # Casos de activación directa, no hay otro semáforo activo o ya es turno de este
    if len(self.activation_queue) == 0:
      self.activation_queue.append(light_id)
      return True
    elif self.activation_queue[0] == light_id:
      return True
    # Dado que es probable que este semáforo ya estuviera en fila, se verifica
    elif light_id not in self.activation_queue:
      self.activation_queue.append(light_id)
    return False

  def report_actions(self):
    cars = [{"id": c.id, "x1": c.last_pos[0], "y1": c.last_pos[1],
      "x2": c.pos[0], "y2": c.pos[1], "origin": c.origin, "action": c.action,
      "turn": c.turn} for c in self.schedule.agents if isinstance(c, Car)]   
    lights = [{"id": s.id, "state": s.state} for s in self.stoplights]
    return {"Items": cars}, {"Items": lights}

#@title Clase Servidor de la simulación

# Clase que maneja las requests al servidor: envía y recibe datos
# Controla la simulación según lo vaya pidiendo Unity
class SimulationServer(BaseHTTPRequestHandler):
  # Modelo de MESA que se simulará, activación del logging
  model = None
  log_active = False
  start_time = None
  initialized = False

  # Manejo de un método GET enviado al servidor
  def do_GET(self):
    self.log("GET")
    self._set_response()
    self.wfile.write(f"GET request for {self.path}".encode('utf-8'))


  # Manejo de un método POST enviado al servidor
  def do_POST(self):
    # Lectura del método POST que ha llegado con un request
    content_length = int(self.headers['Content-Length'])
    post_data = json.loads(self.rfile.read(content_length))
    self.log("POST", post_data)
    
    # Selección de la respuesta según la petición. Envío codificado
    response = self.choose_response(post_data["request"])
    self._set_response()
    self.wfile.write(response.encode('utf-8'))
    if response == "{\"order\": \"stop\"}":
      raise KeyboardInterrupt()


  def choose_response(self, request):
    # Variables de trabajo. Se devuelve la transposición de get_grid
    response = {"data": ""}

    # Árbol de respuestas de Python para Unity según el request
    # Da prioridad a enviar un stop si se alcanza el tiempo máximo
    if time.time() - self.start_time > self.model.max_duration:
      response = {"order" : "stop"}
    elif request == "board-init":
      response = {"m": self.model.m, "n": self.model.n}
    elif request == "lights-init":
      response = {"Items" : [{"id": s.id, "state": s.state,
        "x": self.model.stoplight_pos[s.id][0],
        "y": self.model.stoplight_pos[s.id][1]}
        for s in self.model.stoplights]}
      SimulationServer.initialized = True
    elif request == "step" and SimulationServer.initialized:
      self.model.step()
      cars, lights = self.model.report_actions()
      response = {"carsJson": json.dumps(cars),
                  "lightsJson": json.dumps(lights)}
    else:
      response = {"order" : "wait"}
    return json.dumps(response)
        
  # Configura una respuesta HTTP de éxito con encabezado
  def _set_response(self):
    self.send_response(200)
    self.send_header('Content-type', 'text/html')
    self.end_headers()

  # Logging de la clase padre sobrescrito para poder desactivar logs
  def log_message(self, format, *args):
    if (self.log_active):
      super().log_message(format, *args)

  # Log de métodos HTTP por logging
  def log(self, method, data = None):
    # Requiere activación
    if not(self.log_active): return
    if method == "GET":
      logging.info("GET request,\nPath: %s\nHeaders:\n%s\n",
      str(self.path), str(self.headers))
    elif method == "POST":
      logging.info("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n",
      str(self.path),str(self.headers), json.dumps(data))

#@title Asignación del modelo

# Dado que el servidor recibe una clase y no un objeto, se tiene
# que atar al modelo multi-agentes como una variable estática
def attach_model(simulation_server, model_params):
  new_model = CrossroadModel(*model_params)
  simulation_server.model = new_model

#@title Run del servidor

# Run para el servidor, habiendo creado el servidor que conoce al modelo
def run(server_class, handler_class, port, log):
    # Asegura solo tener un servidor a la vez, matando a los demás
    # ngrok.kill()
    
    # Crea el servidor y lo conecta al túnel en el puerto abierto
    httpd = server_class(('', port), handler_class)
    # public_url = ngrok.connect(port, proto="http", options={"bind_tls": True}).public_url
    # ngrok.connect(port)

    # Impresión para monitorización y guía al usuario final
    if log:
      logging.basicConfig(level = logging.INFO)
      logging.info("Iniciando httpd...\n")
    print("\nServidor corriendo. Ctrl+C para detener conexión y continuar")
    # print(f"Túnel público: {public_url}")
    print(f"Túnel local: http://127.0.0.1:{port}")

    # Corre el servidor hasta cualquier excepción, de teclado o de fin
    handler_class.start_time = time.time()
    try: httpd.serve_forever()
    except: pass
    handler_class.end_time = time.time()

    # Cierre del servidor
    httpd.server_close()
    if log: logging.info("Deteniendo httpd...\n")
    print("Servidor detenido. Continúa la animación en Colab")

#@title Estadísticas de ejecución

# Impresión de los datos relevantes para MAS
def show_statistics(simulation_server):
  # Extracción de los tiempos de ejecución
  print("\nEstadísticas de la ejecución")
  max_duration = simulation_server.model.max_duration
  duration = simulation_server.end_time - simulation_server.start_time

  # Formateo y restricción a un valor máximo del tiempo de ejecución
  if (duration >= max_duration):
    print(f"Tiempo de ejecución: {max_duration}s (Duración máxima permitida)")
  else:
    print(f"Tiempo de ejecución: {round(duration, 3)}s (Tarea terminada antes de tiempo)")

#@title Animación

# Genera una animación de un modelo que recolecta sus cuadrículas
def animate_simulation(model):
  # Recopila los datos del recolector por ser animados
  grids = model.grid_collector.get_model_vars_dataframe()
  if grids.size == 0: return
  
  # Colores por mostrar, con una lista paralela para recordar lo que representan
  crossroad_colors = ["#003264", "#E66414", "#191919", "#F8DE7E", "#646464",
                      "#323232", "#00FF00", "#FFFF00", "#FF0000", "#60AA46"]
  crossroad_labels = ["car", "crash", "crossroad", "crosswalk", "curb", "street",
                      "green light", "yellow light", "red light", "garden"]
  
  # Genera el mapa de color con matplotlib
  crossroad_cmap = matplotlib.colors.ListedColormap(crossroad_colors)
  
  # Modificación de parámetros de matplotlib para una impresión mejor
  plt.rcParams["animation.html"] = "jshtml"
  plt.rcParams["axes.titlesize"] = 28
  matplotlib.rcParams['animation.embed_limit'] = 2 ** 128

  # Construcción y personalización de la gráfica animada
  fig, axs = plt.subplots(figsize=(7, 7))
  axs.set_title("Crossroad Simulation")
  axs.set_xticks([])
  axs.set_yticks([])
  patch = plt.imshow(grids.iloc[0][0], vmin = 0,
    vmax = len(crossroad_colors), cmap = crossroad_cmap)

  # Creación y ejecución del objeto animación
  crossroad_simulation = animation.FuncAnimation(fig,
    lambda i: patch.set_data(grids.iloc[i][0]) , frames = grids.size)
  plt.show()

#@title Flujo principal del programa

# Parámetros de la simulación
M, N = [16, 16]
SPAWN_RATE = 0.15
LIGHT_TICK = 8
MAX_DURATION = 3600

# Smart regula si los semáforos funcionan con la detección de carros,
# además de los ticks. Con smart en false, los semáforos siempre se
# quedarán en verde el número de ticks indicado, aún sin carros ahí
SMART = True

# Ejecución de un modelo desde un servidor, animación final
model_params = [M, N, SPAWN_RATE, LIGHT_TICK, SMART, MAX_DURATION]
attach_model(SimulationServer, model_params)
run(HTTPServer, SimulationServer, port = 8585, log = False)
show_statistics(SimulationServer)
animate_simulation(SimulationServer.model)