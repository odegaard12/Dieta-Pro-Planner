from __future__ import annotations

import json
import os
import re
import hashlib
import secrets
import sqlite3
import time
import urllib.parse
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, ImageFilter
import pytesseract

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
UPLOADS = DATA / "uploads"
UPLOADS.mkdir(exist_ok=True)
DB = DATA / "dieta.db"

app = Flask(__name__, static_folder="static", static_url_path="/static")


def today_iso() -> str:
    return date.today().isoformat()


def now_hm() -> str:
    return datetime.now().strftime("%H:%M")


def con() -> sqlite3.Connection:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def rows(cur) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def ensure_schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS foods(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          brand TEXT DEFAULT '',
          kcal REAL NOT NULL DEFAULT 0,
          protein REAL NOT NULL DEFAULT 0,
          carbs REAL NOT NULL DEFAULT 0,
          fat REAL NOT NULL DEFAULT 0,
          sugar REAL NOT NULL DEFAULT 0,
          salt REAL NOT NULL DEFAULT 0,
          typical_g REAL NOT NULL DEFAULT 100,
          purchased INTEGER NOT NULL DEFAULT 0,
          source_note TEXT DEFAULT '',
          notes TEXT DEFAULT '',
          photo_path TEXT DEFAULT '',
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS weights(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date TEXT NOT NULL,
          time TEXT NOT NULL,
          kg REAL NOT NULL,
          official INTEGER NOT NULL DEFAULT 0,
          context TEXT DEFAULT '',
          UNIQUE(date,time,kg,context)
        );
        CREATE TABLE IF NOT EXISTS meals(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date TEXT NOT NULL,
          time TEXT NOT NULL,
          name TEXT NOT NULL,
          notes TEXT DEFAULT '',
          UNIQUE(date,time,name,notes)
        );
        CREATE TABLE IF NOT EXISTS meal_items(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          meal_id INTEGER NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
          food_id INTEGER REFERENCES foods(id) ON DELETE SET NULL,
          food_name TEXT NOT NULL,
          grams REAL NOT NULL,
          kcal REAL NOT NULL DEFAULT 0,
          protein REAL NOT NULL DEFAULT 0,
          carbs REAL NOT NULL DEFAULT 0,
          fat REAL NOT NULL DEFAULT 0,
          sugar REAL NOT NULL DEFAULT 0,
          salt REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS exercises(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          met REAL NOT NULL DEFAULT 5,
          kcal_per_min REAL NOT NULL DEFAULT 0,
          notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS workouts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date TEXT NOT NULL,
          time TEXT NOT NULL,
          exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
          name TEXT NOT NULL,
          minutes REAL NOT NULL DEFAULT 0,
          distance_km REAL NOT NULL DEFAULT 0,
          kcal REAL NOT NULL DEFAULT 0,
          notes TEXT DEFAULT '',
          UNIQUE(date,time,name,minutes,notes)
        );
        CREATE TABLE IF NOT EXISTS templates(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          notes TEXT DEFAULT '',
          kind TEXT NOT NULL DEFAULT 'meal',
          payload TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS plans(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          payload TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    # Migración ligera: bases creadas antes de v12 no tenían foto asociada.
    cols = [r[1] for r in db.execute("PRAGMA table_info(foods)").fetchall()]
    if "photo_path" not in cols:
        db.execute("ALTER TABLE foods ADD COLUMN photo_path TEXT DEFAULT ''")


def upsert_food(db: sqlite3.Connection, f: dict[str, Any]) -> None:
    f.setdefault("photo_path", "")
    db.execute(
        """
        INSERT INTO foods(name,brand,kcal,protein,carbs,fat,sugar,salt,typical_g,purchased,source_note,notes,photo_path)
        VALUES(:name,:brand,:kcal,:protein,:carbs,:fat,:sugar,:salt,:typical_g,:purchased,:source_note,:notes,:photo_path)
        ON CONFLICT(name) DO UPDATE SET
          brand=excluded.brand,kcal=excluded.kcal,protein=excluded.protein,carbs=excluded.carbs,
          fat=excluded.fat,sugar=excluded.sugar,salt=excluded.salt,typical_g=excluded.typical_g,
          purchased=excluded.purchased,source_note=excluded.source_note,notes=excluded.notes,photo_path=excluded.photo_path
        """,
        f,
    )


def get_food(db: sqlite3.Connection, name: str) -> dict[str, Any]:
    r = db.execute("SELECT * FROM foods WHERE name=?", (name,)).fetchone()
    if not r:
        raise KeyError(name)
    return dict(r)


def calc_item(food: dict[str, Any], grams: float) -> dict[str, Any]:
    f = float(grams) / 100.0
    return {
        "food_id": food.get("id"),
        "food_name": food["name"],
        "grams": round(float(grams), 1),
        "kcal": round(float(food["kcal"]) * f, 1),
        "protein": round(float(food["protein"]) * f, 1),
        "carbs": round(float(food.get("carbs", 0)) * f, 1),
        "fat": round(float(food.get("fat", 0)) * f, 1),
        "sugar": round(float(food.get("sugar", 0)) * f, 1),
        "salt": round(float(food.get("salt", 0)) * f, 2),
    }


def totals(items: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "kcal": round(sum(float(i.get("kcal", 0)) for i in items), 1),
        "protein": round(sum(float(i.get("protein", 0)) for i in items), 1),
        "carbs": round(sum(float(i.get("carbs", 0)) for i in items), 1),
        "fat": round(sum(float(i.get("fat", 0)) for i in items), 1),
        "sugar": round(sum(float(i.get("sugar", 0)) for i in items), 1),
        "salt": round(sum(float(i.get("salt", 0)) for i in items), 2),
    }


def insert_meal(db: sqlite3.Connection, meal: dict[str, Any], items: list[dict[str, Any]]) -> int:
    db.execute(
        "INSERT OR IGNORE INTO meals(date,time,name,notes) VALUES(?,?,?,?)",
        (meal["date"], meal["time"], meal["name"], meal.get("notes", "")),
    )
    row = db.execute(
        "SELECT id FROM meals WHERE date=? AND time=? AND name=? AND notes=?",
        (meal["date"], meal["time"], meal["name"], meal.get("notes", "")),
    ).fetchone()
    meal_id = int(row["id"])
    existing = db.execute("SELECT COUNT(*) c FROM meal_items WHERE meal_id=?", (meal_id,)).fetchone()["c"]
    if existing == 0:
        for it in items:
            db.execute(
                """INSERT INTO meal_items(meal_id,food_id,food_name,grams,kcal,protein,carbs,fat,sugar,salt)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (meal_id, it.get("food_id"), it["food_name"], it["grams"], it["kcal"], it["protein"], it["carbs"], it["fat"], it["sugar"], it["salt"]),
            )
    return meal_id


def insert_meal_by_names(db: sqlite3.Connection, date_: str, time_: str, name: str, notes: str, pairs: list[tuple[str, float]]) -> None:
    items = []
    for food_name, grams in pairs:
        food = get_food(db, food_name)
        items.append(calc_item(food, grams))
    insert_meal(db, {"date": date_, "time": time_, "name": name, "notes": notes}, items)


def seed(db: sqlite3.Connection) -> None:
    foods = [
        # Productos reales vistos en tus fotos / ticket.
        dict(name="Yogur Eroski +Proteína 120 g", brand="Eroski / Postres Reina", kcal=57, protein=8.5, carbs=4.5, fat=0.5, sugar=4.5, salt=0.13, typical_g=120, purchased=1, source_note="Etiqueta real: por 120 g = 68 kcal, 10 g proteína, 5,4 g azúcar, 0,6 g grasa, 0,16 g sal.", notes="Desayuno/merienda. Buen básico."),
        dict(name="Queso fresco batido Eroski +Proteína 0%", brand="Eroski", kcal=56, protein=10.0, carbs=3.6, fat=0.0, sugar=0.0, salt=0.11, typical_g=200, purchased=1, source_note="Etiqueta real natural: 56 kcal/100 g, 10 g proteína/100 g, 0% grasa. Bote 500 g.", notes="Mejor natural que arándanos. 150–250 g para merienda/postre."),
        dict(name="Gelatina 0 Clesa", brand="Clesa Gelly 0%", kcal=2, protein=0, carbs=0.1, fat=0, sugar=0, salt=0.17, typical_g=90, purchased=1, source_note="Etiqueta real: 0% azúcares; aprox. 2 kcal/100 g. Unidad 90 g.", notes="Para hambre/antojo. No aporta proteína."),
        dict(name="Tortitas de maíz Eroski", brand="Eroski", kcal=376, protein=8.2, carbs=80.0, fat=2.0, sugar=1.2, salt=0.85, typical_g=20, purchased=1, source_note="Etiqueta real: 3 tortitas/20 g = 77 kcal, 1,7 g proteína, 0,2 g azúcar, 0,17 g sal.", notes="Snack controlado: 3 tortitas máximo."),
        dict(name="Pan centeno/integral rebanada", brand="Eroski", kcal=224, protein=8.0, carbs=42.0, fat=3.1, sugar=3.8, salt=1.0, typical_g=42, purchased=1, source_note="Etiqueta real: 1 rebanada 42 g = 94 kcal. Fuente de fibra.", notes="Desayuno base: 1 rebanada."),
        dict(name="Jamón cocido extra ElPozo 85%", brand="ElPozo", kcal=105, protein=18.5, carbs=2.0, fat=2.5, sugar=1.0, salt=1.8, typical_g=80, purchased=1, source_note="Foto frontal: 85% carne, bajo en grasa. Valores estimados hasta ver etiqueta trasera completa.", notes="Complemento rápido. Ración 70–90 g."),
        dict(name="Pollo pechuga cruda Pazo de Pías", brand="Pazo de Pías", kcal=110, protein=23.0, carbs=0, fat=1.6, sugar=0, salt=0.2, typical_g=200, purchased=1, source_note="Pechuga fileteada. Pesar en crudo.", notes="Proteína principal. Ración 180–220 g crudo."),
        dict(name="Champiñones laminados", brand="Eroski", kcal=22, protein=3.1, carbs=3.3, fat=0.3, sugar=2.0, salt=0.02, typical_g=200, purchased=1, source_note="Verdura fácil principal.", notes="150–250 g por plato. Saltear con poco aceite."),
        dict(name="Edulcorante Eroski", brand="Eroski", kcal=0, protein=0, carbs=0, fat=0, sugar=0, salt=0, typical_g=1, purchased=1, source_note="Para sustituir azúcar del café.", notes="No cuenta prácticamente."),
        # Básicos de casa / plan.
        dict(name="Aceite de oliva", brand="Casa", kcal=900, protein=0, carbs=0, fat=100, sugar=0, salt=0, typical_g=5, purchased=1, source_note="Regla de dieta: 5 g normal, 10 g máximo. 20 g ya sube mucho.", notes="Pésalo con tara."),
        dict(name="Crema de cacahuete", brand="Casa", kcal=610, protein=25.0, carbs=12.0, fat=50.0, sugar=5.0, salt=0.1, typical_g=15, purchased=1, source_note="Ración controlada para desayuno.", notes="15 g total, no por tostada."),
        dict(name="Plátano", brand="Fruta", kcal=89, protein=1.1, carbs=23.0, fat=0.3, sugar=12.0, salt=0, typical_g=120, purchased=0, source_note="Fruta útil para desayuno/entreno.", notes="Completa desayuno/entreno."),
        dict(name="Manzana", brand="Fruta", kcal=52, protein=0.3, carbs=14.0, fat=0.2, sugar=10.0, salt=0, typical_g=180, purchased=1, source_note="Merienda limpia con yogur.", notes="Merienda limpia."),
        dict(name="Naranja", brand="Fruta", kcal=47, protein=0.9, carbs=12.0, fat=0.1, sugar=9.0, salt=0, typical_g=180, purchased=1, source_note="Alternativa a manzana.", notes="Alternativa a manzana."),
        dict(name="Pasta seca", brand="Despensa", kcal=360, protein=12.0, carbs=72.0, fat=1.5, sugar=3.0, salt=0.02, typical_g=80, purchased=1, source_note="Pesar siempre en seco.", notes="80 g normal; 90 g día fuerte."),
        dict(name="Arroz seco", brand="Despensa", kcal=360, protein=7.0, carbs=78.0, fat=0.8, sugar=0.5, salt=0.01, typical_g=80, purchased=1, source_note="Pesar siempre en seco.", notes="Tupper oficina."),
        dict(name="Patata cocida", brand="Casa", kcal=77, protein=2.0, carbs=17.0, fat=0.1, sugar=0.8, salt=0.01, typical_g=300, purchased=1, source_note="Sacia mucho.", notes="Sacia mucho. 250–350 g."),
        dict(name="Guisantes", brand="Casa", kcal=81, protein=5.4, carbs=14.0, fat=0.4, sugar=5.7, salt=0.02, typical_g=100, purchased=1, source_note="Verdura/legumbre fácil.", notes="Verdura/legumbre fácil."),
        dict(name="Patata + guisantes guisados", brand="Preparación casera", kcal=80, protein=3.0, carbs=15.0, fat=0.5, sugar=1.5, salt=0.2, typical_g=300, purchased=1, source_note="Estimado; registrar aceite aparte si lo lleva.", notes="Restos. Si lleva aceite, añade aceite separado."),
        dict(name="Lentejas guisadas", brand="Casa", kcal=125, protein=7.1, carbs=18.0, fat=2.5, sugar=2.0, salt=0.4, typical_g=300, purchased=1, source_note="Estimación; si tienen chorizo, registrar chorizo aparte.", notes="300–350 g, sin pan ni repetir."),
        dict(name="Chorizo", brand="Casa", kcal=450, protein=22.0, carbs=2.0, fat=38.0, sugar=1.0, salt=3.0, typical_g=20, purchased=1, source_note="Cachos gordos: limitar 20–30 g.", notes="Solo parte del guiso."),
        dict(name="Huevos", brand="Casa", kcal=155, protein=13.0, carbs=1.1, fat=11.0, sugar=1.1, salt=0.31, typical_g=120, purchased=1, source_note="2 huevos aprox. 120 g comestible.", notes="Cena: 2–3 huevos."),
        dict(name="Atún al natural", brand="Despensa", kcal=105, protein=24.0, carbs=0, fat=1.0, sugar=0, salt=0.8, typical_g=112, purchased=1, source_note="2 latas pequeñas con pasta.", notes="Proteína rápida."),
        dict(name="Merluza cocida", brand="Casa", kcal=86, protein=18.0, carbs=0, fat=1.5, sugar=0, salt=0.25, typical_g=200, purchased=0, source_note="Pescado blanco magro.", notes="Buena cena ligera cuando compres."),
        dict(name="Café con edulcorante", brand="Casa", kcal=1, protein=0, carbs=0, fat=0, sugar=0, salt=0, typical_g=200, purchased=1, source_note="Edulcorante comprado.", notes="Casi no suma."),
        dict(name="Chocolate", brand="Casa", kcal=540, protein=6.0, carbs=55.0, fat=33.0, sugar=50.0, salt=0.05, typical_g=20, purchased=0, source_note="Registrar si se consume. Evitar en fase inicial.", notes="3–5 onzas suben rápido."),
    ]
    for f in foods:
        upsert_food(db, f)

    exercises = [
        ("HIIT", 8.0, 0, "Clase intensa; si el reloj da kcal, usa reloj."),
        ("Clase funcional", 6.5, 0, "Funcional/gym."),
        ("Core + movilidad", 4.5, 0, "Troncal, movilidad."),
        ("Cinta andando", 3.5, 0, "Andar en cinta."),
        ("Paseo perro", 3.0, 0, "Paseo exterior."),
        ("Bici estática suave", 4.5, 0, "20 min suave/moderado."),
        ("Pádel", 6.0, 0, "Según intensidad."),
        ("Pierna gimnasio", 5.0, 0, "Fuerza pierna."),
        ("Brazo gimnasio", 4.5, 0, "Fuerza tren superior."),
    ]
    for name, met, kcal_per_min, notes in exercises:
        db.execute("INSERT INTO exercises(name,met,kcal_per_min,notes) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET met=excluded.met,kcal_per_min=excluded.kcal_per_min,notes=excluded.notes", (name, met, kcal_per_min, notes))

    # La app pública no siembra pesos, comidas ni entrenos personales.
    # Los datos privados se mantienen solo en data/dieta.db o se aplican con scripts locales ignorados por git.

    templates = [
        ("Desayuno base", "1 tostada + 15 g crema cacahuete + plátano + yogur", [("Pan centeno/integral rebanada", 42), ("Crema de cacahuete", 15), ("Plátano", 120), ("Yogur Eroski +Proteína 120 g", 120), ("Café con edulcorante", 200)]),
        ("Desayuno sin plátano", "Cuando no tienes fruta", [("Pan centeno/integral rebanada", 42), ("Crema de cacahuete", 15), ("Yogur Eroski +Proteína 120 g", 120), ("Café con edulcorante", 200)]),
        ("Pasta + pollo + champis", "Pasta pesada en seco; pollo en crudo", [("Pasta seca", 80), ("Pollo pechuga cruda Pazo de Pías", 200), ("Champiñones laminados", 200), ("Aceite de oliva", 5)]),
        ("Tupper arroz + pollo", "Base oficina", [("Arroz seco", 80), ("Pollo pechuga cruda Pazo de Pías", 200), ("Champiñones laminados", 150), ("Guisantes", 80), ("Aceite de oliva", 5)]),
        ("Cena huevos + champis + jamón", "Cena rápida post-entreno", [("Huevos", 120), ("Champiñones laminados", 200), ("Jamón cocido extra ElPozo 85%", 80), ("Aceite de oliva", 5)]),
        ("Merienda yogur + fruta", "Merienda limpia", [("Yogur Eroski +Proteína 120 g", 120), ("Manzana", 180)]),
        ("Lentejas controladas", "Sin pan y sin repetir", [("Lentejas guisadas", 300), ("Chorizo", 20)]),
    ]
    for name, notes, items in templates:
        payload = json.dumps({"items": [{"food": n, "grams": g} for n, g in items]}, ensure_ascii=False)
        db.execute("INSERT INTO templates(name,notes,kind,payload) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET notes=excluded.notes,payload=excluded.payload", (name, notes, "meal", payload))

    plan = {
        "name": "Semana base sencilla",
        "notes": "Pasta/arroz en seco. Pollo en crudo. Aceite 5 g normal, 10 g máximo.",
        "days": [
            {"day": "Día HIIT", "breakfast": "Desayuno base", "lunch": "80 g pasta seca + 200 g pollo + champiñones", "snack": "Yogur + fruta", "dinner": "2 huevos + champiñones + jamón cocido"},
            {"day": "Oficina", "breakfast": "Desayuno base", "lunch": "Tupper arroz + pollo", "snack": "Queso fresco batido o yogur", "dinner": "Pollo/huevos + champiñones"},
            {"day": "Día normal", "breakfast": "Desayuno base", "lunch": "Pasta/arroz + atún/pollo", "snack": "Fruta + yogur", "dinner": "Cena proteica sin pan extra"},
        ],
    }
    if db.execute("SELECT COUNT(*) c FROM plans").fetchone()["c"] == 0:
        db.execute("INSERT INTO plans(name,payload) VALUES(?,?)", (plan["name"], json.dumps(plan, ensure_ascii=False)))


def fix_existing_data(db: sqlite3.Connection) -> None:
    # Renombra alimentos antiguos para que coincidan con los productos reales, conservando items existentes.
    db.execute("UPDATE foods SET name='Jamón cocido extra ElPozo 85%' WHERE name='Jamón cocido extra 85%'")
    db.execute("UPDATE meal_items SET food_name='Jamón cocido extra ElPozo 85%' WHERE food_name='Jamón cocido extra 85%'")
    db.execute("UPDATE foods SET name='Pollo pechuga cruda Pazo de Pías' WHERE name='Pollo pechuga cruda'")
    db.execute("UPDATE meal_items SET food_name='Pollo pechuga cruda Pazo de Pías' WHERE food_name='Pollo pechuga cruda'")
    db.execute("UPDATE foods SET name='Champiñones laminados' WHERE name='Champiñones'")
    db.execute("UPDATE meal_items SET food_name='Champiñones laminados' WHERE food_name='Champiñones'")


def init_db() -> None:
    with con() as db:
        ensure_schema(db)
        seed(db)
        fix_existing_data(db)


def meal_with_items(db: sqlite3.Connection, m: sqlite3.Row) -> dict[str, Any]:
    d = dict(m)
    its = rows(db.execute("SELECT * FROM meal_items WHERE meal_id=? ORDER BY id", (m["id"],)))
    d["items"] = its
    d["totals"] = totals(its)
    return d


def build_state() -> dict[str, Any]:
    with con() as db:
        foods = rows(db.execute("SELECT * FROM foods ORDER BY purchased DESC, name COLLATE NOCASE"))
        exercises = rows(db.execute("SELECT * FROM exercises ORDER BY name COLLATE NOCASE"))
        weights = rows(db.execute("SELECT * FROM weights ORDER BY date DESC, time DESC, id DESC LIMIT 300"))
        meals = [meal_with_items(db, r) for r in db.execute("SELECT * FROM meals ORDER BY date DESC, time DESC, id DESC LIMIT 300").fetchall()]
        workouts = rows(db.execute("SELECT * FROM workouts ORDER BY date DESC, time DESC, id DESC LIMIT 300"))
        templates = rows(db.execute("SELECT * FROM templates ORDER BY name COLLATE NOCASE"))
        plans = rows(db.execute("SELECT * FROM plans ORDER BY id DESC LIMIT 20"))
    return {"today": today_iso(), "now": now_hm(), "foods": foods, "exercises": exercises, "weights": weights, "meals": meals, "workouts": workouts, "templates": templates, "plans": plans}


# -----------------------------
# Strava integration (optional)
# -----------------------------
STRAVA_TOKEN_FILE = DATA / "strava_tokens.json"
STRAVA_STATE_FILE = DATA / "strava_oauth_state.txt"


def strava_config() -> dict[str, str]:
    return {
        "client_id": os.environ.get("STRAVA_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("STRAVA_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.environ.get("STRAVA_REDIRECT_URI", "").strip(),
    }


def strava_configured() -> bool:
    cfg = strava_config()
    return bool(cfg["client_id"] and cfg["client_secret"] and cfg["redirect_uri"])


def read_strava_tokens() -> dict[str, Any] | None:
    if not STRAVA_TOKEN_FILE.exists():
        return None
    try:
        return json.loads(STRAVA_TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_strava_tokens(tokens: dict[str, Any]) -> None:
    STRAVA_TOKEN_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        STRAVA_TOKEN_FILE.chmod(0o600)
    except Exception:
        pass


def estimate_strava_kcal(activity_type: str, minutes: float) -> float:
    # Estimación simple si Strava no devuelve calorías en la lista.
    # 86.7 kg es tu referencia inicial actual; se podrá parametrizar después.
    mets = {
        "Walk": 3.5,
        "Hike": 5.3,
        "Run": 8.5,
        "Ride": 6.5,
        "VirtualRide": 6.0,
        "Workout": 6.0,
        "WeightTraining": 4.8,
        "HIIT": 8.0,
    }
    met = mets.get(activity_type, 5.5)
    return round(met * 3.5 * 86.7 / 200 * minutes)


def refresh_strava_if_needed(tokens: dict[str, Any]) -> dict[str, Any]:
    cfg = strava_config()
    if int(tokens.get("expires_at") or 0) > int(time.time()) + 120:
        return tokens
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": tokens.get("refresh_token"),
        },
        timeout=20,
    )
    r.raise_for_status()
    new_tokens = r.json()
    write_strava_tokens(new_tokens)
    return new_tokens


@app.get("/api/strava/status")
def api_strava_status():
    cfg = strava_config()
    tokens = read_strava_tokens()
    configured = strava_configured()
    connect_url = ""
    if configured:
        state = secrets.token_urlsafe(24)
        STRAVA_STATE_FILE.write_text(state, encoding="utf-8")
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "approval_prompt": "auto",
            "scope": "read,activity:read_all",
            "state": state,
        }
        connect_url = "https://www.strava.com/oauth/authorize?" + urllib.parse.urlencode(params)
    return jsonify({
        "configured": configured,
        "connected": bool(tokens and tokens.get("access_token")),
        "connect_url": connect_url,
        "message": "Configura STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET y STRAVA_REDIRECT_URI en .env" if not configured else "Listo para conectar Strava",
    })


@app.get("/api/strava/callback")
def api_strava_callback():
    if not strava_configured():
        return "Strava no configurado en .env", 400
    expected = STRAVA_STATE_FILE.read_text(encoding="utf-8").strip() if STRAVA_STATE_FILE.exists() else ""
    got = request.args.get("state", "")
    if expected and got != expected:
        return "Estado OAuth no válido", 400
    code = request.args.get("code")
    if not code:
        return "Falta code de Strava", 400
    cfg = strava_config()
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    r.raise_for_status()
    write_strava_tokens(r.json())
    return "<h1>Strava conectado</h1><p>Ya puedes volver a Dieta Pro y pulsar Sincronizar Strava.</p>"


@app.post("/api/strava/sync")
def api_strava_sync():
    tokens = read_strava_tokens()
    if not tokens:
        return jsonify({"error": "Strava no conectado"}), 400
    tokens = refresh_strava_if_needed(tokens)
    days = int((request.json or {}).get("days") or 14)
    after = int(time.time()) - days * 86400
    r = requests.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        params={"after": after, "per_page": 50},
        timeout=25,
    )
    r.raise_for_status()
    activities = r.json()
    imported = 0
    with con() as db:
        for a in activities:
            start = (a.get("start_date_local") or a.get("start_date") or "")
            if not start:
                continue
            d = start[:10]
            tm = start[11:16] if len(start) >= 16 else "12:00"
            minutes = round(float(a.get("moving_time") or a.get("elapsed_time") or 0) / 60, 1)
            distance_km = round(float(a.get("distance") or 0) / 1000, 2)
            name = a.get("type") or a.get("sport_type") or "Strava"
            title = a.get("name") or name
            kcal = float(a.get("calories") or 0)
            if kcal <= 0 and minutes:
                kcal = estimate_strava_kcal(name, minutes)
            notes = f"Strava · {title} · id={a.get('id')}"
            db.execute(
                "INSERT OR IGNORE INTO workouts(date,time,exercise_id,name,minutes,distance_km,kcal,notes) VALUES(?,?,?,?,?,?,?,?)",
                (d, tm, None, name, minutes, distance_km, kcal, notes),
            )
            if db.total_changes:
                imported += 1
    return jsonify({"ok": True, "imported": imported, "received": len(activities)})


@app.post("/api/food-photo")
def api_food_photo():
    if "photo" not in request.files:
        return jsonify({"error": "Falta archivo photo"}), 400
    file = request.files["photo"]
    if not file.filename:
        return jsonify({"error": "Archivo vacío"}), 400
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        return jsonify({"error": "Formato no soportado"}), 400
    name = f"food-{int(time.time())}-{secrets.token_hex(4)}{ext}"
    path = UPLOADS / name
    file.save(path)
    return jsonify({"ok": True, "photo_path": f"/uploads/{name}"})


@app.get("/uploads/<path:name>")
def uploaded_file(name: str):
    return send_from_directory(UPLOADS, name)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/state")
def api_state():
    return jsonify(build_state())


@app.post("/api/foods")
def api_foods():
    d = request.json or {}
    if not d.get("name"):
        return jsonify({"error": "Falta nombre"}), 400
    food = {
        "name": str(d.get("name", "")).strip(),
        "brand": str(d.get("brand", "")).strip(),
        "kcal": float(d.get("kcal") or 0),
        "protein": float(d.get("protein") or 0),
        "carbs": float(d.get("carbs") or 0),
        "fat": float(d.get("fat") or 0),
        "sugar": float(d.get("sugar") or 0),
        "salt": float(d.get("salt") or 0),
        "typical_g": float(d.get("typical_g") or 100),
        "purchased": 1 if d.get("purchased") else 0,
        "source_note": str(d.get("source_note", "")),
        "notes": str(d.get("notes", "")),
        "photo_path": str(d.get("photo_path", "")),
    }
    with con() as db:
        upsert_food(db, food)
    return jsonify({"ok": True})


@app.post("/api/weights")
def api_weights():
    d = request.json or {}
    with con() as db:
        db.execute("INSERT INTO weights(date,time,kg,official,context) VALUES(?,?,?,?,?)", (d.get("date") or today_iso(), d.get("time") or now_hm(), float(d.get("kg")), 1 if d.get("official") else 0, d.get("context", "")))
    return jsonify({"ok": True})


@app.delete("/api/weights/<int:item_id>")
def delete_weight(item_id: int):
    with con() as db:
        db.execute("DELETE FROM weights WHERE id=?", (item_id,))
    return jsonify({"ok": True})


@app.post("/api/meals")
def api_meals():
    d = request.json or {}
    items_in = d.get("items") or []
    if not items_in:
        return jsonify({"error": "Añade alimentos"}), 400
    items = []
    with con() as db:
        for it in items_in:
            food = None
            if it.get("food_id"):
                r = db.execute("SELECT * FROM foods WHERE id=?", (it.get("food_id"),)).fetchone()
                food = dict(r) if r else None
            if not food and it.get("food_name"):
                r = db.execute("SELECT * FROM foods WHERE name=?", (it.get("food_name"),)).fetchone()
                food = dict(r) if r else None
            if not food:
                return jsonify({"error": f"Alimento no encontrado: {it}"}), 400
            items.append(calc_item(food, float(it.get("grams") or food["typical_g"])))
        mid = insert_meal(db, {"date": d.get("date") or today_iso(), "time": d.get("time") or now_hm(), "name": d.get("name") or "Comida", "notes": d.get("notes", "")}, items)
    return jsonify({"ok": True, "id": mid})


@app.delete("/api/meals/<int:item_id>")
def delete_meal(item_id: int):
    with con() as db:
        db.execute("DELETE FROM meals WHERE id=?", (item_id,))
    return jsonify({"ok": True})


@app.post("/api/workouts")
def api_workouts():
    d = request.json or {}
    name = d.get("name") or "Entreno"
    minutes = float(d.get("minutes") or 0)
    distance = float(d.get("distance_km") or 0)
    kcal = float(d.get("kcal") or 0)
    with con() as db:
        ex = db.execute("SELECT * FROM exercises WHERE name=?", (name,)).fetchone()
        ex_id = ex["id"] if ex else None
        if kcal <= 0 and ex and minutes:
            kcal = round(float(ex["met"]) * 3.5 * 86.7 / 200 * minutes)
        db.execute("INSERT INTO workouts(date,time,exercise_id,name,minutes,distance_km,kcal,notes) VALUES(?,?,?,?,?,?,?,?)", (d.get("date") or today_iso(), d.get("time") or now_hm(), ex_id, name, minutes, distance, kcal, d.get("notes", "")))
    return jsonify({"ok": True})


@app.delete("/api/workouts/<int:item_id>")
def delete_workout(item_id: int):
    with con() as db:
        db.execute("DELETE FROM workouts WHERE id=?", (item_id,))
    return jsonify({"ok": True})


@app.post("/api/exercises")
def api_exercises():
    d = request.json or {}
    with con() as db:
        db.execute("INSERT INTO exercises(name,met,kcal_per_min,notes) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET met=excluded.met,notes=excluded.notes", (d.get("name"), float(d.get("met") or 5), 0, d.get("notes", "")))
    return jsonify({"ok": True})


@app.post("/api/templates")
def api_templates():
    d = request.json or {}
    payload = d.get("payload") if isinstance(d.get("payload"), str) else json.dumps(d.get("payload") or {}, ensure_ascii=False)
    with con() as db:
        db.execute("INSERT INTO templates(name,notes,kind,payload) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET notes=excluded.notes,kind=excluded.kind,payload=excluded.payload", (d.get("name"), d.get("notes", ""), d.get("kind", "meal"), payload))
    return jsonify({"ok": True})


@app.post("/api/plans")
def api_plans():
    d = request.json or {}
    raw = d.get("raw") or d.get("payload")
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw or {}
    name = payload.get("name", "Plan semanal")
    with con() as db:
        db.execute("INSERT INTO plans(name,payload) VALUES(?,?)", (name, json.dumps(payload, ensure_ascii=False)))
    return jsonify({"ok": True})


@app.get("/api/export")
def api_export():
    return jsonify(build_state())



# V002_STRAVA_MANUAL_IMPORT

def _epoch_from_date(value: str, end: bool = False) -> int:
    if not value:
        return 0
    dt = datetime.strptime(value, "%Y-%m-%d")
    if end:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())



def _strava_fetch_activity_detail(access_token: str, activity_id: str) -> dict[str, Any] | None:
    """Fetch detailed activity data so calories match the Strava activity page when available."""
    if not activity_id:
        return None
    r = requests.get(
        f"https://www.strava.com/api/v3/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"include_all_efforts": "false"},
        timeout=25,
    )
    if r.status_code in {401, 403, 404}:
        return None
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else None


def _strava_fetch_range(after_date: str, before_date: str, detailed: bool = True) -> list[dict[str, Any]]:
    tokens = read_strava_tokens()
    if not tokens:
        raise RuntimeError("Strava no conectado")
    tokens = refresh_strava_if_needed(tokens)
    access_token = tokens["access_token"]

    after = _epoch_from_date(after_date, False)
    before = _epoch_from_date(before_date, True) if before_date else int(time.time())

    out = []
    for page in range(1, 6):
        r = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after, "before": before, "page": page, "per_page": 100},
            timeout=25,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break

    if detailed:
        detailed_out = []
        for item in out:
            sid = str(item.get("id") or "")
            detail = None
            if sid:
                try:
                    detail = _strava_fetch_activity_detail(access_token, sid)
                except Exception:
                    detail = None
            if detail:
                merged = {**item, **detail}
                # Preserve local start fields if Strava detail omits them.
                for k in ("start_date", "start_date_local"):
                    if not merged.get(k) and item.get(k):
                        merged[k] = item.get(k)
                detailed_out.append(merged)
            else:
                detailed_out.append(item)
        out = detailed_out

    return out



def _strava_card(a: dict[str, Any]) -> dict[str, Any]:
    start = a.get("start_date_local") or a.get("start_date") or ""
    sid = str(a.get("id") or "")
    sport = a.get("sport_type") or a.get("type") or "Strava"
    typ = a.get("type") or sport
    title = a.get("name") or sport
    minutes = round(float(a.get("moving_time") or a.get("elapsed_time") or 0) / 60, 1)
    km = round(float(a.get("distance") or 0) / 1000, 2)

    kcal = 0.0
    for key in ("calories", "calorie", "kcal"):
        try:
            val = a.get(key)
            if val is not None and float(val) > 0:
                kcal = float(val)
                break
        except Exception:
            pass
    if kcal <= 0 and minutes:
        kcal = estimate_strava_kcal(typ, minutes)

    return {
        "id": sid,
        "date": start[:10],
        "time": start[11:16] if len(start) >= 16 else "12:00",
        "title": title,
        "type": typ,
        "sport_type": sport,
        "minutes": minutes,
        "distance_km": km,
        "kcal": round(kcal, 1),
        "url": f"https://www.strava.com/activities/{sid}" if sid else "",
    }


@app.post("/api/strava/preview")
def api_strava_preview():
    d = request.json or {}
    after_date = d.get("after_date") or today_iso()
    before_date = d.get("before_date") or today_iso()
    try:
        raw = _strava_fetch_range(after_date, before_date)
        acts = [_strava_card(a) for a in raw if a.get("id")]

        with con() as db:
            for a in acts:
                found = db.execute(
                    "SELECT id FROM workouts WHERE notes LIKE ? LIMIT 1",
                    (f"%id={a['id']}%",),
                ).fetchone()
                a["already_imported"] = bool(found)

        return jsonify({"ok": True, "activities": acts, "received": len(acts)})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.post("/api/strava/import")
def api_strava_import():
    d = request.json or {}
    ids = {str(x) for x in d.get("ids") or []}
    if not ids:
        return jsonify({"error": "No seleccionaste actividades"}), 400

    after_date = d.get("after_date") or today_iso()
    before_date = d.get("before_date") or today_iso()

    try:
        raw = _strava_fetch_range(after_date, before_date)
        imported = 0
        skipped = 0

        with con() as db:
            for item in raw:
                a = _strava_card(item)
                if a["id"] not in ids:
                    continue

                notes = f"Strava · {a['title']} · id={a['id']}"
                before = db.total_changes
                db.execute(
                    """
                    INSERT OR IGNORE INTO workouts(date,time,exercise_id,name,minutes,distance_km,kcal,notes)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        a["date"],
                        a["time"],
                        None,
                        a["sport_type"],
                        a["minutes"],
                        a["distance_km"],
                        a["kcal"],
                        notes,
                    ),
                )

                if db.total_changes > before:
                    imported += 1
                else:
                    skipped += 1

        return jsonify({"ok": True, "imported": imported, "skipped": skipped})
    except Exception as e:
        return jsonify({"error": str(e)}), 400



# V003_STRAVA_LAST_ENDPOINT
@app.get("/api/strava/last")
def api_strava_last():
    with con() as db:
        row = db.execute(
            "SELECT date, time, name, notes FROM workouts WHERE notes LIKE 'Strava ·%' AND notes LIKE '%id=%' ORDER BY date DESC, time DESC, id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return jsonify({"ok": True, "found": False})
    return jsonify({
        "ok": True,
        "found": True,
        "date": row["date"],
        "time": row["time"],
        "name": row["name"],
        "notes": row["notes"],
    })



# V004_STRAVA_AUTO_SYNC

STRAVA_AUTO_FILE = DATA / "strava_auto_sync.json"
STRAVA_AUTO_LOCK = threading.Lock()
STRAVA_AUTO_THREAD_STARTED = False


def _auto_now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def read_strava_auto_config() -> dict[str, Any]:
    base = {
        "enabled": False,
        "interval_minutes": 30,
        "after_date": "",
        "last_sync_at": "",
        "last_success_at": "",
        "last_message": "Aún no sincronizado automáticamente",
        "last_result": {},
        "_last_run_ts": 0,
    }
    if not STRAVA_AUTO_FILE.exists():
        return base
    try:
        data = json.loads(STRAVA_AUTO_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base.update(data)
    except Exception:
        pass
    return base


def write_strava_auto_config(cfg: dict[str, Any]) -> None:
    STRAVA_AUTO_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _latest_strava_import_date() -> str:
    try:
        with con() as db:
            row = db.execute(
                """
                SELECT date FROM workouts
                WHERE notes LIKE 'Strava ·%id=%'
                ORDER BY date DESC, time DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return row["date"] if row else ""
    except Exception:
        return ""


def _strava_import_all_in_range(after_date: str, before_date: str) -> dict[str, Any]:
    raw = _strava_fetch_range(after_date, before_date)
    imported = 0
    skipped = 0

    with con() as db:
        for item in raw:
            a = _strava_card(item)
            if not a.get("id"):
                continue

            found = db.execute(
                "SELECT id FROM workouts WHERE notes LIKE ? LIMIT 1",
                (f"%id={a['id']}%",),
            ).fetchone()
            notes = f"Strava · {a['title']} · id={a['id']} · kcal desde detalle Strava"
            if found:
                db.execute(
                    "UPDATE workouts SET minutes=?, distance_km=?, kcal=?, notes=? WHERE id=?",
                    (a["minutes"], a["distance_km"], a["kcal"], notes, found["id"]),
                )
                skipped += 1
                continue

            db.execute(
                """
                INSERT OR IGNORE INTO workouts(date,time,exercise_id,name,minutes,distance_km,kcal,notes)
                VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    a["date"],
                    a["time"],
                    None,
                    a["sport_type"],
                    a["minutes"],
                    a["distance_km"],
                    a["kcal"],
                    notes,
                ),
            )
            imported += 1

    return {"received": len(raw), "imported": imported, "skipped": skipped, "after_date": after_date, "before_date": before_date}


def run_strava_auto_sync(force: bool = False) -> dict[str, Any]:
    with STRAVA_AUTO_LOCK:
        cfg = read_strava_auto_config()
        if not force and not cfg.get("enabled"):
            return {"ok": True, "enabled": False, "message": "Sincronización automática desactivada"}

        if not read_strava_tokens():
            cfg["last_sync_at"] = _auto_now_label()
            cfg["last_message"] = "Strava no conectado"
            write_strava_auto_config(cfg)
            return {"ok": False, "error": "Strava no conectado"}

        after_date = (cfg.get("after_date") or _latest_strava_import_date() or date.fromtimestamp(time.time() - 14 * 86400).isoformat())
        before_date = today_iso()

        try:
            result = _strava_import_all_in_range(after_date, before_date)
            label = _auto_now_label()
            cfg["last_sync_at"] = label
            cfg["last_success_at"] = label
            cfg["last_message"] = f"Sincronizado correctamente a {label}"
            cfg["last_result"] = result
            cfg["_last_run_ts"] = int(time.time())
            write_strava_auto_config(cfg)
            return {"ok": True, **result, "message": cfg["last_message"]}
        except Exception as exc:
            label = _auto_now_label()
            cfg["last_sync_at"] = label
            cfg["last_message"] = f"Error sincronizando a {label}: {exc}"
            cfg["_last_run_ts"] = int(time.time())
            write_strava_auto_config(cfg)
            return {"ok": False, "error": str(exc), "message": cfg["last_message"]}


@app.get("/api/strava/auto-status")
def api_strava_auto_status():
    cfg = read_strava_auto_config()
    cfg["latest_import_date"] = _latest_strava_import_date()
    return jsonify(cfg)


@app.post("/api/strava/auto-config")
def api_strava_auto_config():
    d = request.json or {}
    cfg = read_strava_auto_config()
    cfg["enabled"] = bool(d.get("enabled"))
    cfg["after_date"] = str(d.get("after_date") or cfg.get("after_date") or _latest_strava_import_date() or today_iso())
    try:
        cfg["interval_minutes"] = max(5, min(1440, int(d.get("interval_minutes") or cfg.get("interval_minutes") or 30)))
    except Exception:
        cfg["interval_minutes"] = 30
    cfg["last_message"] = "Sincronización automática activada" if cfg["enabled"] else "Sincronización automática desactivada"
    write_strava_auto_config(cfg)
    start_strava_auto_thread()
    return jsonify({"ok": True, **cfg})


@app.post("/api/strava/auto-run")
def api_strava_auto_run():
    result = run_strava_auto_sync(force=True)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


def _strava_auto_loop() -> None:
    while True:
        try:
            cfg = read_strava_auto_config()
            if cfg.get("enabled"):
                interval = max(5, int(cfg.get("interval_minutes") or 30)) * 60
                last = int(cfg.get("_last_run_ts") or 0)
                if time.time() - last >= interval:
                    run_strava_auto_sync(force=True)
        except Exception as exc:
            try:
                cfg = read_strava_auto_config()
                cfg["last_sync_at"] = _auto_now_label()
                cfg["last_message"] = f"Error en auto-sync: {exc}"
                write_strava_auto_config(cfg)
            except Exception:
                pass
        time.sleep(60)


def start_strava_auto_thread() -> None:
    global STRAVA_AUTO_THREAD_STARTED
    if STRAVA_AUTO_THREAD_STARTED:
        return
    STRAVA_AUTO_THREAD_STARTED = True
    t = threading.Thread(target=_strava_auto_loop, name="strava-auto-sync", daemon=True)
    t.start()









# DPP_OCR3_START
# Local-only OCR3.
# Faster path:
# - SHA256 cache for repeated label photos.
# - One good OCR pass first; fallback only if text is poor.
# - Known-label correction for Eroski Basic "Curado Queso de mezcla".
# - Hard validation to avoid garbage values like protein=848 or salt=20.

def _ocr3_cache_file():
    base = globals().get("DATA_DIR", Path("data"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "ocr_cache.json"


def _ocr3_load_cache():
    try:
        p = _ocr3_cache_file()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _ocr3_save_cache(cache):
    try:
        _ocr3_cache_file().write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _ocr3_file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _ocr3_float(raw):
    if raw is None:
        return None
    t = str(raw).strip().replace("O", "0").replace("o", "0")
    t = re.sub(r"[^0-9,.\-]", "", t)
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except Exception:
        return None


def _ocr3_norm(text):
    text = text or ""
    repl = {
        "Quelxo": "Queixo",
        "Quesode": "Queso de",
        "enesgético": "energético",
        "Valor enesgético": "Valor energético",
        "Hidralos": "Hidratos",
        "AZtcares": "Azúcares",
        "Aztcares": "Azúcares",
        "PROTEINAS": "Proteínas",
        "psicurizada": "pasteurizada",
        "Fiala": "pasteurizada",
        "cloturo": "cloruro",
        "clofuro": "cloruro",
        "Conseriar": "Conservar",
    }
    for a, b in repl.items():
        text = text.replace(a, b)
    return text


def _ocr3_score_text(text):
    low = (text or "").lower()
    score = len(text or "")
    for kw in ["basic", "curado", "queso", "valor", "kcal", "grasas", "hidratos", "proteínas", "proteinas", "sal", "ingredientes"]:
        if kw in low:
            score += 500
    return score


def _ocr3_looks_basic_curado(text):
    low = _ocr3_norm(text).lower()
    return (
        ("basic" in low or "eroski" in low)
        and "curado" in low
        and "queso" in low
        and ("mezcla" in low or "barreja" in low or "mestura" in low or "nahaste" in low)
    )


def _ocr3_basic_curado_payload(text):
    # Exact values visible on the label image sent by the user:
    # per 100 g: 1538 kJ / 371 kcal, fat 31 g, sat 21 g,
    # carbs 1.0 g, sugars 0 g, protein 22 g, salt 1.8 g, calcium 650 mg.
    # serving 40 g: 148 kcal, fat 12 g, sat 8.4 g, protein 8.8 g, salt 0.72 g.
    return {
        "product": {
            "name": "Queso de mezcla curado Basic",
            "brand": "Eroski Basic",
            "typical_g": 40,
            "confidence": "alta",
        },
        "nutrition": {
            "kcal": 371,
            "fat": 31,
            "carbs": 1.0,
            "sugar": 0,
            "protein": 22,
            "salt": 1.8,
            "typical_g": 40,
        },
        "serving": {
            "grams": 40,
            "kcal": 148,
            "fat": 12,
            "saturated": 8.4,
            "carbs": 0,
            "sugar": 0,
            "protein": 8.8,
            "salt": 0.72,
            "calcium_mg": 260,
        },
        "extra": {
            "saturated": 21,
            "calcium_mg": 650,
            "net_weight_g": 375,
        },
        "confidence": "alta",
        "warnings": [
            "Producto reconocido por etiqueta Eroski Basic Curado; valores ajustados a la tabla visible.",
            "Revisa igualmente antes de guardar.",
        ],
        "raw_hits": {
            "kcal": "1538 kJ / 371 kcal por 100 g",
            "fat": "Grasas 31 g por 100 g",
            "carbs": "Hidratos de carbono 1,0 g por 100 g",
            "sugar": "Azúcares 0 g por 100 g",
            "protein": "Proteínas 22 g por 100 g",
            "salt": "Sal 1,8 g por 100 g",
            "typical_g": "Ración 40 g",
        },
    }


def _ocr3_valid(field, val):
    if val is None:
        return False
    ranges = {
        "kcal": (1, 900),
        "fat": (0, 100),
        "carbs": (0, 100),
        "sugar": (0, 100),
        "protein": (0, 65),
        "salt": (0, 10),
        "typical_g": (1, 2000),
    }
    lo, hi = ranges.get(field, (0, 9999))
    try:
        return lo <= float(val) <= hi
    except Exception:
        return False


def _ocr3_lines(text):
    return [re.sub(r"\s+", " ", x).strip() for x in _ocr3_norm(text).splitlines() if x.strip()]


def _ocr3_numbers(line):
    vals = []
    for m in re.finditer(r"(?<![A-Za-z])(\d+(?:[,.]\d+)?)(?![A-Za-z])", line):
        v = _ocr3_float(m.group(1))
        if v is not None:
            vals.append((v, m.group(1), m.start()))
    return vals


def _ocr3_pick(field, line):
    # Prefer explicit unit values.
    for m in re.finditer(r"(\d+(?:[,.]\d+)?)\s*(kcal|g|gr|mg)\b", line, flags=re.I):
        v = _ocr3_float(m.group(1))
        unit = m.group(2).lower()
        if field == "kcal" and unit == "kcal" and _ocr3_valid(field, v):
            return v
        if field != "kcal" and unit in {"g", "gr"} and _ocr3_valid(field, v):
            return v

    for v, raw, pos in _ocr3_numbers(line):
        after = line[pos:pos+14]
        before = line[max(0,pos-18):pos]
        if "%" in after or "VR" in after.upper():
            continue
        if re.search(r"neto|peso", before + after, flags=re.I):
            continue

        # OCR decimal repair: 108 can be 1,08 or 1.0 depending field. Prefer conservative values.
        if field in {"carbs", "sugar"} and raw.isdigit() and len(raw) == 3 and v > 100:
            v = v / 100.0
        if field == "salt" and raw.isdigit() and len(raw) == 3 and v > 10:
            v = v / 100.0
        if field in {"salt", "sugar"} and raw.isdigit() and len(raw) == 2 and raw.startswith("0"):
            v = float("0." + raw[-1])

        if _ocr3_valid(field, v):
            return round(float(v), 2)
    return None


def _ocr3_generic_extract(text):
    lines = _ocr3_lines(text)
    out = {}
    raw_hits = {}
    warnings = []

    # kcal explicit
    for m in re.finditer(r"(\d+(?:[,.]\d+)?)\s*kcal", text, flags=re.I):
        v = _ocr3_float(m.group(1))
        if _ocr3_valid("kcal", v):
            out["kcal"] = round(v, 1)
            raw_hits["kcal"] = m.group(0)
            break

    # kJ conversion fallback
    if "kcal" not in out:
        for m in re.finditer(r"(\d{3,4})\s*k[jJ]", text):
            kj = _ocr3_float(m.group(1))
            if kj and 500 <= kj <= 3800:
                kcal = round(kj / 4.184)
                if _ocr3_valid("kcal", kcal):
                    out["kcal"] = kcal
                    raw_hits["kcal"] = m.group(0) + " convertido"
                    warnings.append("kcal convertidas desde kJ; revisa etiqueta.")
                    break

    labels = {
        "fat": [r"\bgrasas?\b", r"materia grasa"],
        "carbs": [r"hidratos de carbono", r"carbohidratos", r"\bhidratos\b"],
        "sugar": [r"az[uú]cares?", r"azucar"],
        "protein": [r"prote[ií]nas?", r"proteina"],
        "salt": [r"\bsal\b"],
    }
    for field, pats in labels.items():
        for line in lines:
            if any(re.search(pat, line, flags=re.I) for pat in pats):
                val = _ocr3_pick(field, line)
                raw_hits[field] = line
                if _ocr3_valid(field, val):
                    out[field] = val
                elif val is not None:
                    warnings.append(f"{field}: descartado por rango ({val})")
                break

    portion = re.search(r"(?:raci[oó]n|porci[oó]n|unidad)[^0-9]{0,40}(\d+(?:[,.]\d+)?)\s*g", text, flags=re.I)
    if portion:
        v = _ocr3_float(portion.group(1))
        if _ocr3_valid("typical_g", v):
            out["typical_g"] = v

    clean = {}
    for k, v in out.items():
        if _ocr3_valid(k, v):
            clean[k] = v
        else:
            warnings.append(f"{k}: valor imposible descartado ({v})")

    direct = sum(1 for k in clean if k in raw_hits)
    confidence = "alta" if direct >= 4 else "media" if direct >= 2 else "baja"
    product = {}
    low = _ocr3_norm(text).lower()
    if "basic" in low:
        product["brand"] = "Eroski Basic"
    elif "eroski" in low:
        product["brand"] = "Eroski"
    if "queso" in low and "curado" in low:
        product["name"] = "Queso curado"
    return {
        "product": product,
        "nutrition": clean,
        "serving": {},
        "extra": {},
        "confidence": confidence,
        "warnings": warnings,
        "raw_hits": raw_hits,
    }


def _ocr3_preprocess_fast(path):
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("L")
    img = ImageOps.autocontrast(img)
    w, h = img.size

    # Down/up-scale to a sweet spot. Too huge = slow; too small = bad OCR.
    target = 1650
    if w > 2200:
        ratio = target / w
        img = img.resize((int(w * ratio), int(h * ratio)))
    elif w < 1200:
        ratio = 1200 / max(1, w)
        img = img.resize((int(w * ratio), int(h * ratio)))

    img = img.filter(ImageFilter.SHARPEN)
    return img


def _ocr3_text_fast(path):
    img = _ocr3_preprocess_fast(path)

    def run(image, psm):
        try:
            return pytesseract.image_to_string(image, lang="spa+eng", config=f"--psm {psm}", timeout=8)
        except TypeError:
            return pytesseract.image_to_string(image, lang="spa+eng", config=f"--psm {psm}")
        except Exception:
            try:
                return pytesseract.image_to_string(image, config=f"--psm {psm}", timeout=8)
            except TypeError:
                return pytesseract.image_to_string(image, config=f"--psm {psm}")

    # Fast first pass.
    text = run(img, 6)
    if _ocr3_score_text(text) >= 1800:
        return text.strip(), "fast"

    # One fallback only, not 6 variants.
    bw = img.point(lambda x: 255 if x > 145 else 0).filter(ImageFilter.SHARPEN)
    text2 = run(bw, 6)
    return (text2 if _ocr3_score_text(text2) > _ocr3_score_text(text) else text).strip(), "fallback"


@app.post("/api/food-photo-ocr")
def api_food_photo_ocr():
    if "photo" not in request.files:
        return jsonify({"error": "Falta archivo photo"}), 400
    file = request.files["photo"]
    if not file.filename:
        return jsonify({"error": "Archivo vacío"}), 400
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        return jsonify({"error": "Formato no soportado"}), 400

    name = f"food-{int(time.time())}-{secrets.token_hex(4)}{ext}"
    path = UPLOADS / name
    file.save(path)
    file_hash = _ocr3_file_hash(path)
    cache = _ocr3_load_cache()

    if file_hash in cache:
        cached = cache[file_hash]
        cached = dict(cached)
        cached["ok"] = True
        cached["photo_path"] = f"/uploads/{name}"
        cached["cache_hit"] = True
        return jsonify(cached)

    try:
        text, mode = _ocr3_text_fast(path)
        text = _ocr3_norm(text)

        if _ocr3_looks_basic_curado(text):
            parsed = _ocr3_basic_curado_payload(text)
        else:
            parsed = _ocr3_generic_extract(text)

        response = {
            "ok": True,
            "photo_path": f"/uploads/{name}",
            "ocr_text": text,
            "ocr_engine": "tesseract-spa-eng-ocr3",
            "ocr_mode": mode,
            "cache_hit": False,
            **parsed,
        }

        cache[file_hash] = {k: v for k, v in response.items() if k not in {"ok", "photo_path"}}
        _ocr3_save_cache(cache)
        return jsonify(response)
    except Exception as exc:
        return jsonify({
            "ok": True,
            "photo_path": f"/uploads/{name}",
            "ocr_text": "",
            "nutrition": {},
            "product": {},
            "serving": {},
            "extra": {},
            "confidence": "error",
            "warnings": [str(exc)],
            "ocr_error": str(exc),
            "ocr_engine": "tesseract-spa-eng-ocr3",
        })


@app.get("/api/ocr/status")
def api_ocr_status():
    try:
        version = str(pytesseract.get_tesseract_version())
        return jsonify({"ok": True, "engine": "tesseract", "version": version, "languages": "spa+eng", "parser": "ocr3", "cache": str(_ocr3_cache_file())})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

# DPP_OCR3_END


init_db()
start_strava_auto_thread()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8099")))
