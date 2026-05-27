from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, redirect, request, send_from_directory
from werkzeug.utils import secure_filename

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


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8099")))
