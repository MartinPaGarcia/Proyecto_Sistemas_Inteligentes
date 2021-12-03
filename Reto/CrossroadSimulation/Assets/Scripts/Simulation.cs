/*
Simulación de un sistema multiagentes conectado con Python
TC2008B. Sistemas Multiagentes y Gráficas Computacionales. Tecnológico de Monterrey

El equipo de trabajo genera en su mayoría código independiente, pero acude a
implementaciones de profesores del Tecnológico de Monterrey para las conexiones
con HTTP y el manejo de los datos que se envían y reciben.


- Versión para la solución del reto del equipo 2, Carlos G. del Rosal, 1/12/2021
- Adapted by [Jorge Cruz](https://jcrvz.co) on November 2021
- Original implementation: C# client to interact with Unity, Sergio Ruiz, July 2021
*/

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.UI;

public class Simulation : MonoBehaviour {
    // Componentes del tablero modelado
    private Board boardSize;
    private Mesh boardMesh;
    private GameObject indicators;
    
    // Conexión con Python
    public string url;

    // Colecciones de los objetos instanciados
    private Dictionary<string, GameObject> stopLights = new Dictionary<string, GameObject>();
    private Dictionary<int, GameObject> cars = new Dictionary<int, GameObject>();
    private List<LightStep> lightSteps = new List<LightStep>();
    private List<Move> ongoingMoves = new List<Move>();
    private List<Turn> ongoingTurns = new List<Turn>();

    // Controles de duración y activación de la simulación
    [Range(0.2f, 10.0f)]
    public float stepDuration = 2.0f;
    private float timer, parametrizedT;
    private bool active = false;

    // Prefabs por ser colocados
    public GameObject stopLightPrefab, streetLightPrefab, carPrefab;

    // Configuración inicial de la simulación - Se llama una sola vez
    void Start() {
        // Colocación de los modelos con posiciones definidas en tiempo de ejecución
        StartCoroutine(RequestToPython("board-init"));

        // Inicialización del cronometro
        timer = stepDuration;
    }

    // Actualización de la simulación - Se llama cada frame
    void Update()
    {
        // Permite tener la simulación inactiva sin tener que dejar/destruir la escena
        if (active) {
            // Cuenta el tiempo hacia 0 restando el tiempo por frame
            timer -= Time.deltaTime;
            parametrizedT = 1.0f - (timer / stepDuration);
            if (timer < 0) {
                // Acciones por realizar cada stepDuration
                correctCars();
                ongoingMoves.Clear();
                ongoingTurns.Clear();
                StartCoroutine(RequestToPython("step"));

                // Reinicia el timer al cumplirse la duración
                timer = stepDuration;
            }

            // Realiza las actualizaciones de los semáforos
            if (lightSteps.Count > 0) {
                foreach (LightStep lightStep in lightSteps) changeStopLight(lightStep.id, lightStep.state);
                lightSteps.Clear();
            }

            // Realiza los movimientos en línea recta
            if (ongoingMoves.Count > 0) {
                foreach (Move carMove in ongoingMoves) {
                    // Utiliza una interpolación linear para coordinar el movimiento con el tiempo de step
                    cars[carMove.id].transform.position = Vector3.Lerp(
                        carMove.origin, carMove.destination, parametrizedT);
                }
            }

            // Realiza los giros de los carros
            if (ongoingTurns.Count > 0) {
                foreach (Turn carTurn in ongoingTurns) {
                    // Rota con un semáforo como pivote, usa deltaTime para coordinar con el tiempo de step
                    cars[carTurn.id].transform.RotateAround(carTurn.stepPivot, Vector3.up,
                        carTurn.stepAngle / stepDuration * Time.deltaTime);
                }
            }
        }
    }

    // Método para comunicación con Python, envía datos petición y recibe datos de simulación
    private IEnumerator RequestToPython(string requestName) {
        // Crea un form que se enviará en el método POST
        WWWForm form = new WWWForm();
        string requestInJSON = "{\"request\" : \"" + requestName + "\"}";
        byte[] bodyRaw = System.Text.Encoding.UTF8.GetBytes(requestInJSON);
        form.AddField("request", requestInJSON);
        using (UnityWebRequest www = UnityWebRequest.Post(url, form)) {

            // Preparación de los datos y el encabezado HTTP para salir hacia Python
            www.uploadHandler.Dispose();
            www.uploadHandler = new UploadHandlerRaw(bodyRaw);
            www.SetRequestHeader("Content-Type", "application/json");

            // Se envía el request y se actúa en caso de error o éxito
            yield return www.SendWebRequest();
            if (www.result != UnityWebRequest.Result.ConnectionError &&
                www.result != UnityWebRequest.Result.ProtocolError) {
                string pythonResponse = www.downloadHandler.text;
                
                // Casos considerados de requests distintos
                if (pythonResponse == "{\"order\": \"stop\"}") {
                    // Con la primera request que diga que Python se ha detenido deja de actualizar
                    if (active) Debug.Log("Python ha detenido el envío de datos");
                    active = false;
                }
                else if (pythonResponse == "{\"order\": \"wait\"}") {
                    // Dice que se debe de esperar el primer step, dado que no ha terminado la inicialización
                    Debug.Log("Step en espera de inicialización");
                }
                else if (requestName == "board-init") {
                    // Obtiene el tamaño del tablero y lo genera con esa información
                    boardSize = JsonUtility.FromJson<Board>(pythonResponse);
                    GenerateBoard(boardSize.m, boardSize.n);
                    StartCoroutine(RequestToPython("lights-init"));
                    active = true;
                }
                else if (requestName == "lights-init") {
                    // Obtiene los semáforos en un inicio
                    InitLight[] initLights = JsonHelper.FromJson<InitLight>(pythonResponse);
                    spawnLights(initLights);
                }
                else if (requestName == "step") {
                    StepResponse stepResponse = JsonUtility.FromJson<StepResponse>(pythonResponse);
                    CarStep[] carSteps = JsonHelper.FromJson<CarStep>(stepResponse.carsJson);
                    LightStep[] newLightSteps = JsonHelper.FromJson<LightStep>(stepResponse.lightsJson);
                    foreach (LightStep newStep in newLightSteps) lightSteps.Add(newStep);
                    if (carSteps != null) manageCarSteps(carSteps);
                }
            }
            else {
                // Error en la conexión con Python
                Debug.Log(www.error);
                Debug.Log("No hay comunicación con Python");
                active = false;
            }
        }
    }

    // Colocación de los semáforos
    private void spawnLights (InitLight[] data) {
        int lightsSeparation = 3;
        stopLights = new Dictionary<string, GameObject>();
        for (int i = 0; i < data.Length; i++) {
            // Colocación del semáforo en el estado enviado
            stopLights.Add(data[i].id, Instantiate(stopLightPrefab,
                new Vector3(data[i].x, 0, data[i].y), Quaternion.identity) as GameObject);
            changeStopLight(data[i].id, data[i].state);

            // Rotaciones para que apunten las luces a los carros que controlan
            float rotY = 0.0f;
            if (data[i].id == "North") rotY = 90.0f;
            else if (data[i].id == "East") rotY = 180.0f;
            else if (data[i].id == "South") rotY = 270.0f;
            stopLights[data[i].id].transform.eulerAngles = new Vector3(0, rotY, 0);
            
            // Colocación de las luces en la misma sección
            if (data[i].x < boardSize.m / 2)
                for (int j = data[i].x - lightsSeparation; j >= 0; j -= lightsSeparation)
                    Instantiate(streetLightPrefab, new Vector3((float) j, 0.0f, data[i].y), Quaternion.identity);
            else
                for (int j = data[i].x + lightsSeparation; j < boardSize.m; j += lightsSeparation)
                    Instantiate(streetLightPrefab, new Vector3((float) j, 0.0f, data[i].y), Quaternion.identity);
            if (data[i].y < boardSize.n / 2)
                for (int j = data[i].y - lightsSeparation; j >= 0; j -= lightsSeparation)
                    Instantiate(streetLightPrefab, new Vector3(data[i].x, 0.0f, (float) j), Quaternion.identity);
            else
                for (int j = data[i].y + lightsSeparation; j < boardSize.n; j += lightsSeparation)
                    Instantiate(streetLightPrefab, new Vector3(data[i].x, 0.0f, (float) j), Quaternion.identity);
        }        
    }

    // Cambio de color de las luces del semáforo
    private void changeStopLight(string id, string state) {
        // Apaga al semáforo antes del cambio para evitar dos luces simultaneas
        stopLights[id].transform.Find("Red1").GetComponent<Light>().enabled = false;
        stopLights[id].transform.Find("Red2").GetComponent<Light>().enabled = false;
        stopLights[id].transform.Find("Yellow1").GetComponent<Light>().enabled = false;
        stopLights[id].transform.Find("Yellow2").GetComponent<Light>().enabled = false;
        stopLights[id].transform.Find("Green1").GetComponent<Light>().enabled = false;
        stopLights[id].transform.Find("Green2").GetComponent<Light>().enabled = false;

        // Cambio con el estado elegido
        if (state == "red") {
            stopLights[id].transform.Find("Red1").GetComponent<Light>().enabled = true;
            stopLights[id].transform.Find("Red2").GetComponent<Light>().enabled = true;
            indicators.transform.Find(id).GetComponent<Image>().color = Color.red;
        }
        else if (state == "yellow") {
            stopLights[id].transform.Find("Yellow1").GetComponent<Light>().enabled = true;
            stopLights[id].transform.Find("Yellow2").GetComponent<Light>().enabled = true;
            indicators.transform.Find(id).GetComponent<Image>().color = Color.yellow;
        }
        else if (state == "green") {
            stopLights[id].transform.Find("Green1").GetComponent<Light>().enabled = true;
            stopLights[id].transform.Find("Green2").GetComponent<Light>().enabled = true;
            indicators.transform.Find(id).GetComponent<Image>().color = Color.green;
        }
    }

    // Creación de los movimientos para cada carro
    private void manageCarSteps(CarStep[] steps) {
        foreach (CarStep step in steps) {
            if (step.action == "spawned") {
                // Colocación del carro nuevo
                cars.Add(step.id, Instantiate(carPrefab, new Vector3(step.x1, 0, step.y1),
                    Quaternion.identity) as GameObject);
                float rotY = 0.0f;
                if (step.origin == "South") rotY = 90.0f;
                else if (step.origin == "West") rotY = 180.0f;
                else if (step.origin == "North") rotY = 270.0f;
                cars[step.id].transform.eulerAngles = new Vector3(0, rotY, 0);
            }
            else if (step.action == "destroyed") {
                // Destrucción del carro viejo
                Destroy(cars[step.id]);
                cars.Remove(step.id);
            }
            else if (step.action == "moving" || step.turn == "straight") {
                // Movimiento del carro con una interpolación linear llevada a cabo en Update()
                ongoingMoves.Add(new Move(step.id, new Vector3((float) step.x1, 0, (float) step.y1),
                    new Vector3((float) step.x2, 0, (float) step.y2)));
                cars[step.id].transform.Find("LeftStop").GetComponent<Light>().enabled = false;
                cars[step.id].transform.Find("RightStop").GetComponent<Light>().enabled = false;
            }
            else if (step.action == "turning") {
                // Giro del carro por ejecutar
                ongoingTurns.Add(new Turn(step.id, step.turn, GetTurnPivot(step.origin, step.turn)));
                cars[step.id].transform.Find("LeftStop").GetComponent<Light>().enabled = false;
                cars[step.id].transform.Find("RightStop").GetComponent<Light>().enabled = false;
            }
            else if (step.action == "stopped") {
                cars[step.id].transform.Find("LeftStop").GetComponent<Light>().enabled = true;
                cars[step.id].transform.Find("RightStop").GetComponent<Light>().enabled = true;
            }
        }
    }

    // Define el pivote para rotar el carro en un giro (un semáforo)
    private Vector3 GetTurnPivot(string origin, string turn) {
        if (origin == "North") {
            return turn == "right" ? stopLights["East"].transform.position : stopLights[origin].transform.position;
        }
        else if (origin == "West") {
            return turn == "right" ? stopLights["North"].transform.position : stopLights[origin].transform.position;
        }
        else if (origin == "South") {
            return turn == "right" ? stopLights["West"].transform.position : stopLights[origin].transform.position;
        }
        else {
            return turn == "right" ? stopLights["South"].transform.position : stopLights[origin].transform.position;
        }
    }

    // Corrige la orientación de los carros girando
    private void correctCars () {
        foreach (Turn turn in ongoingTurns) {
            // Considerando que la variación máxima entre rotaciones es de 90 grados entre 4,
            // se ajusta la rotación en "y" al valor más cercano de múltiplos de 22.5
            Vector3 rot = cars[turn.id].transform.eulerAngles;
            rot.y = Mathf.Round(rot.y / 22.5f) * 22.5f;
            cars[turn.id].transform.eulerAngles = rot;
        }
    }

    // Ajuste del tablero, incluyendo el tamaño y la posición de la cámara
    private void GenerateBoard(int width, int height) {
        // Obtención del tablero base, sus vértices
        boardMesh = GameObject.FindGameObjectsWithTag("Board")[0].GetComponent<MeshFilter>().mesh;
        Vector3[] vertices = boardMesh.vertices;

        // Correcciones de tamaño conociendo el tablero base de antemano
        for (int i = 0; i < vertices.Length; i++) {
            if (vertices[i][0] > 6) vertices[i][0] += (float) width - 6.0f;
            else if (vertices[i][0] > 1) vertices[i][0] += (float) width / 2.0f - 3.0f;

            if (vertices[i][2] > 6) vertices[i][2] += (float) height - 6.0f;
            else if (vertices[i][2] > 1) vertices[i][2] += (float) height / 2.0f - 3.0f;
        }
        boardMesh.vertices = vertices;

        // Ajuste de la cámara, considerando un fov horizontal de 90 grados
        float camX = ((float) width + 2.0f) / 2.0f - 1.5f;
        float camY = camX;
        float camZ = - (float) width * 0.3535f + (float) height / 4.0f;
        Camera.main.transform.position = new Vector3(camX, camY, camZ);

        // Obtención del objeto de indicadores
        indicators = GameObject.FindGameObjectsWithTag("Indicators")[0];
    }
}
