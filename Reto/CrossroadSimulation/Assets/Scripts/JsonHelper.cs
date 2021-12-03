/*
Librería remedio a que JsonUtility no trabaje correctamente con arrays al
momento de deserializar. El sitio del autor original ya no está disponible:
https://www.boxheadproductions.com.au/deserializing-top-level-arrays-in-json-with-unity/

La clase se comentó como respuesta en Stack Overflow por Programmer en 2016:
https://stackoverflow.com/questions/36239705
*/

using System;
using System.Collections;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

public static class JsonHelper {
    public static T[] FromJson<T>(string json) {
        Wrapper<T> wrapper = JsonUtility.FromJson<Wrapper<T>>(json);
        return wrapper.Items;
    }

    public static string ToJson<T>(T[] array) {
        Wrapper<T> wrapper = new Wrapper<T>();
        wrapper.Items = array;
        return JsonUtility.ToJson(wrapper);
    }

    public static string ToJson<T>(T[] array, bool prettyPrint) {
        Wrapper<T> wrapper = new Wrapper<T>();
        wrapper.Items = array;
        return JsonUtility.ToJson(wrapper, prettyPrint);
    }

    [Serializable]
    private class Wrapper<T> {
        public T[] Items;
    }
}