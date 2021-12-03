using System;
using UnityEngine;

// Clases fáciles de deserializar para JSONUtility
[Serializable]
public class Board {
    public int m, n;
}

[Serializable]
public class InitLight {
    public string id, state;
    public int x, y;
}

[Serializable]
public class StepResponse {
    public string carsJson, lightsJson;
}

[Serializable]
public class CarStep {
    public int id, x1, x2, y1, y2;
    public string origin, action, turn;
}

[Serializable]
public class LightStep {
    public string id, state;
}

// Movimiento de un carro en línea recta
public class Move {
    public int id;
    public Vector3 origin, destination;

    // Constructor manual
    public Move (int _id, Vector3 _origin, Vector3 _destination) {
        this.id = _id;
        this.origin = _origin;
        this.destination = _destination;
    }
}

// Movimiento de un carro en línea recta
public class Turn {
    public int id;
    public float stepAngle;
    public Vector3 stepPivot;

    // Constructor manual
    public Turn (int _id, string _turnDirection, Vector3 _pivot) {
        this.id = _id;
        this.stepAngle = _turnDirection == "right" ? -45.0f : 22.5f;
        this.stepPivot = _pivot;
    }
}