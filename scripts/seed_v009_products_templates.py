from __future__ import annotations
import json, sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "dieta.db"

FOODS = [
  ("Yogur Eroski +Proteína 120 g","Eroski / Postres Reina",57,8.5,4.5,0.5,4.5,0.13,120,"Etiqueta: unidad 120 g aprox. 68 kcal y 10 g proteína.","Básico desayuno/merienda."),
  ("Pan centeno/integral rebanada","Eroski",224,8,42,3.1,3.8,1.0,42,"Etiqueta: 1 rebanada 42 g aprox. 94 kcal.","Desayuno base."),
  ("Café con edulcorante","Casa",1,0,0,0,0,0,200,"Café solo con edulcorante.","Prácticamente no cuenta."),
  ("Gelatina 0 Clesa","Clesa",2,0,0.1,0,0,0.17,90,"Gelatina 0% azúcares. Unidad aprox. 90 g.","Para hambre/antojo."),
  ("Pollo pechuga cruda Pazo de Pías","Pazo de Pías",110,23,0,1.6,0,0.2,224,"Pechuga fileteada. Pesar en crudo.","Proteína principal."),
  ("Jamón cocido extra","Eroski / extra",98,18.5,0.3,2.5,0.3,1.9,80,"Etiqueta foto: 98 kcal y 18,5 g proteína por 100 g.","Revuelto/cena rápida."),
  ("Judía verde plana Eliges","Eliges",44,2,7,0.2,2.2,0.03,250,"Bolsa: 250 g = 110 kcal.","Verdura base. Cocer antes de saltear."),
  ("Arroz 3 delicias Basic Eroski","Eroski Basic",102,4,18,1.32,1.2,0.33,100,"Etiqueta foto: 102 kcal/100 g.","Usar controlado: 100 g."),
  ("Queso Larsa clásico cremoso","Larsa",352,24,1,28,1,1.5,10,"Etiqueta foto: 352 kcal/100 g.","Muy calórico: 10–15 g."),
  ("Pasta seca","Casa",356,12,72,1.5,3,0.02,80,"Pesar siempre en seco.","Ración habitual 80 g seco."),
  ("Arroz seco","Casa",360,7,79,0.7,0.2,0.01,80,"Pesar siempre en seco.","Ración habitual 70–80 g seco."),
  ("Aceite de oliva","Casa",884,0,0,100,0,0,5,"Regla: 5 g normal, 10 g máximo.","Pésalo con tara."),
  ("Huevos","Casa",143,12.6,0.7,9.5,0.4,0.36,120,"2 huevos medianos aprox. 120 g.","Base de cena rápida."),
  ("Plátano","Fruta",89,1.1,23,0.3,12,0.01,120,"Fruta útil antes de entrenar.","Pre-entreno o desayuno."),
  ("Manzana","Fruta",52,0.3,14,0.2,10,0,180,"Merienda limpia.","Buena con yogur."),
  ("Chocolate onzas estimado","Estimado",550,6,55,34,50,0.05,20,"4 onzas estimadas como 20 g.","Snack dulce estimado."),
  ("Piruleta estimada","Estimado",390,0,98,0,90,0,10,"Piruleta pequeña estimada 10 g.","Snack puntual."),
  ("Galletas pequeñas con chocolate estimadas","Estimado",480,6,65,22,32,0.5,18,"3 galletas pequeñas estimadas como 18 g.","Snack dulce nocturno estimado."),
]

TEMPLATES = [
  ("Desayuno base limpio","Tostada + café + yogur proteico. Sin plátano.",[("Pan centeno/integral rebanada",42),("Yogur Eroski +Proteína 120 g",120),("Café con edulcorante",200)]),
  ("Desayuno con plátano","Para día con entreno o hambre.",[("Pan centeno/integral rebanada",42),("Yogur Eroski +Proteína 120 g",120),("Café con edulcorante",200),("Plátano",120)]),
  ("Comida pasta + pollo + yogur","Pasta siempre en seco. Tupper/comida fuerte.",[("Pasta seca",80),("Pollo pechuga cruda Pazo de Pías",224),("Aceite de oliva",5),("Yogur Eroski +Proteína 120 g",120)]),
  ("Tupper arroz seco + pollo","Arroz pesado en seco. Base oficina.",[("Arroz seco",80),("Pollo pechuga cruda Pazo de Pías",224),("Aceite de oliva",5),("Yogur Eroski +Proteína 120 g",120)]),
  ("Cena limpia huevos + jamón + judía","Cena ligera/proteica después de día con dulce.",[("Judía verde plana Eliges",250),("Huevos",120),("Jamón cocido extra",80),("Aceite de oliva",5)]),
  ("Cena post-entreno arroz controlado","Con carbo controlado. Usar si hubo mucho deporte.",[("Judía verde plana Eliges",250),("Arroz 3 delicias Basic Eroski",100),("Huevos",120),("Jamón cocido extra",80),("Queso Larsa clásico cremoso",10),("Aceite de oliva",5)]),
  ("Merienda yogur + fruta","Merienda limpia y fácil.",[("Yogur Eroski +Proteína 120 g",120),("Manzana",180)]),
  ("Pre-entreno plátano","30–90 min antes de entrenar.",[("Plátano",120)]),
  ("Snack dulce estimado","Para registrar antojos sin esconderlos.",[("Chocolate onzas estimado",20)]),
  ("Gelatina anti-antojo","Cuando hay hambre dulce y no toca sumar kcal.",[("Gelatina 0 Clesa",90)]),
]

def main():
    if not DB.exists():
        raise SystemExit(f"No existe DB local: {DB}")
    con = sqlite3.connect(DB)
    for name,brand,kcal,protein,carbs,fat,sugar,salt,typical,source,notes in FOODS:
        con.execute('''
        INSERT INTO foods(name,brand,kcal,protein,carbs,fat,sugar,salt,typical_g,purchased,source_note,notes,photo_path)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,COALESCE((SELECT photo_path FROM foods WHERE name=?),''))
        ON CONFLICT(name) DO UPDATE SET
          brand=excluded.brand,kcal=excluded.kcal,protein=excluded.protein,carbs=excluded.carbs,
          fat=excluded.fat,sugar=excluded.sugar,salt=excluded.salt,typical_g=excluded.typical_g,
          purchased=1,source_note=excluded.source_note,notes=excluded.notes
        ''', (name,brand,kcal,protein,carbs,fat,sugar,salt,typical,1,source,notes,name))
    for name,notes,items in TEMPLATES:
        payload = json.dumps({"items":[{"food":f,"grams":g} for f,g in items]}, ensure_ascii=False)
        con.execute('''
        INSERT INTO templates(name,notes,kind,payload)
        VALUES(?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET notes=excluded.notes,kind=excluded.kind,payload=excluded.payload
        ''', (name,notes,"meal",payload))
    con.commit()
    con.close()
    print(f"OK seed v0.0.9: {len(FOODS)} alimentos y {len(TEMPLATES)} plantillas.")

if __name__ == "__main__":
    main()
