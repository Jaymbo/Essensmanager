# FastAPI-Anwendung: Auth, Services, server-seitige UI (Jinja2 + HTMX).

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import planner as planner_mod
from .body_simulator import BodySimulator
from .domain import nutrient_space as ns
from .models import (Household, Ingredient, LogEntry, MealPlan, NutrientDef,
                     PantryItem, Person, PlanEntry, Recipe, RecipeLine, User,
                     Base, make_engine, make_session_factory)
from .recipe_engine import RecipeEngine, compute_ingredient_vector

DB_PATH = os.environ.get("EM_DB_PATH", "/data/app.db")

engine = make_engine(DB_PATH)
Base.metadata.create_all(engine)
SessionLocal = make_session_factory(engine)

app = FastAPI(title="Essensmanager", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# ---------------------------------------------------------------------------
# Auth (Session-Cookie, PBKDF2-Hashes – kein Secret im Code)
# ---------------------------------------------------------------------------

SECRET = os.environ.get("EM_SECRET", secrets.token_hex(32))
_sessions: dict[str, int] = {}   # token -> user_id (in-memory; Neustart = relogin)


def hash_password(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except ValueError:
        return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get("em_session", "")
    user_id = _sessions.get(token)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(user: User | None) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def current_household(db: Session, user: User) -> Household:
    return db.get(Household, user.household_id)


# ---------------------------------------------------------------------------
# Routes: Auth
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, db: Session = Depends(get_db),
          username: str = Form(...), password: str = Form(...)):
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html",
                                          {"error": "Login fehlgeschlagen"},
                                          status_code=401)
    token = secrets.token_hex(24)
    _sessions[token] = user.id
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("em_session", token, httponly=True, samesite="lax")
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("em_session")
    return resp


# ---------------------------------------------------------------------------
# Routes: Dashboard (Tagesbilanz + Pools)
# ---------------------------------------------------------------------------

def _targets_for(db: Session, person: Person) -> tuple[dict, dict]:
    minimum, maximum = {}, {}
    for d in db.execute(select(NutrientDef)).scalars().all():
        ov = (person.target_override_json or {}).get(d.key) or {}
        if ov.get("min", d.daily_min) is not None:
            minimum[d.key] = float(ov.get("min", d.daily_min))
        if ov.get("max", d.daily_max) is not None:
            maximum[d.key] = float(ov.get("max", d.daily_max))
    return minimum, maximum


def _day_intake(db: Session, person: Person, day: date) -> dict[str, float]:
    entries = db.execute(select(LogEntry).where(
        LogEntry.person_id == person.id, LogEntry.date == day)).scalars().all()
    return ns.add(*[e.nutrient_vector_json for e in entries])


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db),
              person_id: int | None = None, days: int = 7):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    persons = db.execute(select(Person).where(
        Person.household_id == hh.id)).scalars().all()
    person = next((p for p in persons if p.id == person_id), persons[0] if persons else None)
    if person is None:
        return templates.TemplateResponse(request, "dashboard.html",
                                          {"user": user, "hh": hh, "persons": [],
                                           "person": None, "table": [], "days": days})

    sim = BodySimulator(db)
    minimum, maximum = _targets_for(db, person)
    today = date.today()
    daily: list[dict[str, float]] = []
    for i in range(days):
        d = today - timedelta(days=(days - 1 - i))
        daily.append(_day_intake(db, person, d))
    results = sim.simulate_days(daily)

    defs = sorted(db.execute(select(NutrientDef)).scalars().all(),
                  key=lambda d: d.display_order)
    keys = [d.key for d in defs if d.daily_min or d.daily_max]
    names = {d.key: f"{d.name} [{d.unit}]" for d in defs}

    table = []
    for k in keys:
        row = {"key": k, "label": names.get(k, k),
               "min": minimum.get(k), "max": maximum.get(k),
               "days": [], "pool_last": results[-1]["pool"].get(k, 0.0) if results else 0.0}
        statuses = [r["status"].get(k, "no_target") for r in results]
        row["days"] = statuses
        row["overall"] = ("under" if "under" in statuses else
                          "over" if "over" in statuses else
                          "in_range" if "in_range" in statuses else "no_target")
        table.append(row)

    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user, "hh": hh, "persons": persons, "person": person,
        "table": table, "days": days,
        "today": today.isoformat(),
    })


# ---------------------------------------------------------------------------
# Routes: Tagebuch (Log)
# ---------------------------------------------------------------------------

@app.get("/log", response_class=HTMLResponse)
def log_form(request: Request, db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    persons = db.execute(select(Person).where(Person.household_id == hh.id)).scalars().all()
    recipes = db.execute(select(Recipe).where(Recipe.household_id == hh.id)).scalars().all()
    ingredients = db.execute(select(Ingredient).where(
        (Ingredient.household_id == hh.id) | (Ingredient.household_id.is_(None)))).scalars().all()
    entries = db.execute(select(LogEntry).where(
        LogEntry.household_id == hh.id).order_by(LogEntry.date.desc())).scalars().all()
    return templates.TemplateResponse(request, "log.html", {
        "user": user, "persons": persons, "recipes": recipes,
        "ingredients": ingredients, "entries": entries,
        "today": date.today().isoformat(),
    })


@app.post("/log")
def log_add(db: Session = Depends(get_db), request: Request = None,
            person_id: int = Form(...), day: str = Form(...),
            meal_slot: str = Form("lunch"),
            recipe_id: int | None = Form(None),
            ingredient_id: int | None = Form(None),
            grams: float = Form(...),
            process_chain: str = Form("")):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    chain = [p.strip() for p in process_chain.split(",") if p.strip()]

    if recipe_id:
        recipe = db.get(Recipe, recipe_id)
        if recipe is None or recipe.household_id != hh.id:
            raise HTTPException(404)
        eng = RecipeEngine(db)
        cache = eng.recipe_vector(recipe)
        # Vektor des gegessenen Anteils (Anteil der Portionen)
        share = grams / 100.0  # Konvention: Gramm = % des Rezepts gegessen
        vec = ns.scale(cache.get("total", {}), share)
        entry = LogEntry(household_id=hh.id, person_id=person_id,
                         date=date.fromisoformat(day), meal_slot=meal_slot,
                         recipe_id=recipe_id, grams_consumed=grams,
                         process_chain=[], nutrient_vector_json=vec)
    elif ingredient_id:
        vec = compute_ingredient_vector(db, ingredient_id, grams, chain)
        entry = LogEntry(household_id=hh.id, person_id=person_id,
                         date=date.fromisoformat(day), meal_slot=meal_slot,
                         ingredient_id=ingredient_id, grams_consumed=grams,
                         process_chain=chain, nutrient_vector_json=vec)
    else:
        raise HTTPException(400, "Rezept oder Zutat angeben")
    db.add(entry)
    db.commit()
    return RedirectResponse("/log", status_code=303)


@app.post("/log/delete")
def log_delete(entry_id: int = Form(...), request: Request = None,
               db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    entry = db.get(LogEntry, entry_id)
    if entry and entry.household_id == user.household_id:
        db.delete(entry)
        db.commit()
    return RedirectResponse("/log", status_code=303)


# ---------------------------------------------------------------------------
# Routes: Rezepte
# ---------------------------------------------------------------------------

@app.get("/recipes", response_class=HTMLResponse)
def recipes(request: Request, db: Session = Depends(get_db),
            q: str = "", ingredient_id: int | None = None,
            process: str | None = None):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    eng = RecipeEngine(db)
    found = eng.search(hh.id, query=q,
                       ingredient_ids=[ingredient_id] if ingredient_id else None,
                       process_keys=[process] if process else None)
    ingredients = db.execute(select(Ingredient).where(
        (Ingredient.household_id == hh.id) | (Ingredient.household_id.is_(None)))).scalars().all()
    processes = db.execute(select(Ingredient)).scalars().all()  # placeholder
    from .models import Process
    procs = db.execute(select(Process)).scalars().all()
    # Vektoren für Anzeige
    view = []
    for r in found:
        cache = eng.recipe_vector(r)
        view.append({"recipe": r, "per_serving": cache.get("per_serving", {})})
    return templates.TemplateResponse(request, "recipes.html", {
        "user": user, "recipes_view": view, "ingredients": ingredients,
        "processes": procs, "q": q, "sel_ingredient": ingredient_id,
        "sel_process": process,
    })


@app.get("/recipes/new", response_class=HTMLResponse)
def recipe_new_form(request: Request, db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    ingredients = db.execute(select(Ingredient).where(
        (Ingredient.household_id == hh.id) | (Ingredient.household_id.is_(None)))).scalars().all()
    from .models import Process
    procs = db.execute(select(Process)).scalars().all()
    return templates.TemplateResponse(request, "recipe_new.html", {
        "user": user, "ingredients": ingredients, "processes": procs,
    })


@app.post("/recipes/new")
def recipe_new(request: Request, db: Session = Depends(get_db),
               name: str = Form(...), servings: int = Form(4),
               instructions: str = Form("")):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    recipe = Recipe(household_id=hh.id, name=name, servings=servings,
                    instructions=instructions)
    db.add(recipe)
    db.commit()
    return RedirectResponse(f"/recipes/{recipe.id}", status_code=303)


@app.post("/recipes/{recipe_id}/lines")
def recipe_add_line(recipe_id: int, request: Request, db: Session = Depends(get_db),
                    ingredient_id: int = Form(...), grams_raw: float = Form(...),
                    process_chain: str = Form(""),
                    yield_factor: float = Form(1.0)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.household_id != hh.id:
        raise HTTPException(404)
    chain = [p.strip() for p in process_chain.split(",") if p.strip()]
    db.add(RecipeLine(recipe_id=recipe.id, ingredient_id=ingredient_id,
                      grams_raw=grams_raw, process_chain=chain,
                      yield_factor=max(0.05, min(yield_factor, 2.0))))
    eng = RecipeEngine(db)
    eng.recipe_vector(recipe)  # Cache neu berechnen
    db.commit()
    return RedirectResponse(f"/recipes/{recipe.id}", status_code=303)


@app.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def recipe_detail(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.household_id != hh.id:
        raise HTTPException(404)
    eng = RecipeEngine(db)
    cache = eng.recipe_vector(recipe)
    lines = []
    for ln in recipe.lines:
        ing = db.get(Ingredient, ln.ingredient_id)
        lines.append({"line": ln, "ingredient": ing})
    return templates.TemplateResponse(request, "recipe_detail.html", {
        "user": user, "recipe": recipe, "lines": lines,
        "total": cache.get("total", {}), "per_serving": cache.get("per_serving", {}),
    })


# ---------------------------------------------------------------------------
# Routes: Vorrat
# ---------------------------------------------------------------------------

@app.get("/pantry", response_class=HTMLResponse)
def pantry(request: Request, db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    items = db.execute(select(PantryItem).where(
        PantryItem.household_id == hh.id)).scalars().all()
    view = [{"item": it, "ingredient": db.get(Ingredient, it.ingredient_id)} for it in items]
    ingredients = db.execute(select(Ingredient).where(
        (Ingredient.household_id == hh.id) | (Ingredient.household_id.is_(None)))).scalars().all()
    return templates.TemplateResponse(request, "pantry.html", {
        "user": user, "items_view": view, "ingredients": ingredients,
        "today": date.today().isoformat(),
    })


@app.post("/pantry/add")
def pantry_add(request: Request, db: Session = Depends(get_db),
               ingredient_id: int = Form(...), grams: float = Form(...),
               expires_on: str | None = Form(None), location: str = Form("fridge")):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    db.add(PantryItem(household_id=hh.id, ingredient_id=ingredient_id, grams=grams,
                      expires_on=date.fromisoformat(expires_on) if expires_on else None,
                      location=location))
    db.commit()
    return RedirectResponse("/pantry", status_code=303)


@app.post("/pantry/delete")
def pantry_delete(item_id: int = Form(...), request: Request = None,
                  db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    item = db.get(PantryItem, item_id)
    if item and item.household_id == user.household_id:
        db.delete(item)
        db.commit()
    return RedirectResponse("/pantry", status_code=303)


# ---------------------------------------------------------------------------
# Routes: Planer
# ---------------------------------------------------------------------------

@app.get("/plan", response_class=HTMLResponse)
def plan_form(request: Request, db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    persons = db.execute(select(Person).where(Person.household_id == hh.id)).scalars().all()
    plans = db.execute(select(MealPlan).where(
        MealPlan.household_id == hh.id).order_by(MealPlan.start_date.desc())).scalars().all()
    plans_view = []
    for p in plans:
        entries = db.execute(select(PlanEntry).where(PlanEntry.plan_id == p.id)).scalars().all()
        detail = []
        for e in entries:
            detail.append({"entry": e, "recipe": db.get(Recipe, e.recipe_id)})
        plans_view.append({"plan": p, "entries": detail})
    return templates.TemplateResponse(request, "plan.html", {
        "user": user, "persons": persons, "plans_view": plans_view,
        "today": date.today().isoformat(),
    })


@app.post("/plan/generate")
def plan_generate(request: Request, db: Session = Depends(get_db),
                  start_date: str = Form(...), days: int = Form(3),
                  prefer_pantry: bool = Form(False),
                  person_ids: list[int] = Form([])):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    persons = {int(pid): 1 for pid in person_ids}
    if not persons:
        all_p = db.execute(select(Person).where(
            Person.household_id == hh.id)).scalars().all()
        persons = {p.id: 1 for p in all_p}
    person0 = db.get(Person, next(iter(persons)))
    targets = person0.target_override_json if person0 else {}
    planner = planner_mod.GreedyPlanner(db)
    try:
        planner.plan(planner_mod.PlanRequest(
            household_id=hh.id, start_date=date.fromisoformat(start_date),
            days=days, persons=persons, prefer_pantry=prefer_pantry),
            person_targets=targets)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse("/plan", status_code=303)


@app.post("/plan/confirm")
def plan_confirm(plan_id: int = Form(...), request: Request = None,
                 db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    plan = db.get(MealPlan, plan_id)
    if plan and plan.household_id == user.household_id:
        plan.status = "confirmed"
        db.commit()
    return RedirectResponse("/plan", status_code=303)


@app.post("/plan/delete")
def plan_delete(plan_id: int = Form(...), request: Request = None,
                db: Session = Depends(get_db)):
    user = require_user(current_user(request, db))
    plan = db.get(MealPlan, plan_id)
    if plan and plan.household_id == user.household_id:
        db.delete(plan)
        db.commit()
    return RedirectResponse("/plan", status_code=303)


# ---------------------------------------------------------------------------
# Routes: Zutaten (inkl. USDA-Upload)
# ---------------------------------------------------------------------------

@app.get("/ingredients", response_class=HTMLResponse)
def ingredients(request: Request, db: Session = Depends(get_db), q: str = ""):
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    stmt = select(Ingredient).where(
        (Ingredient.household_id == hh.id) | (Ingredient.household_id.is_(None)))
    if q:
        stmt = stmt.where(Ingredient.name.ilike(f"%{q}%"))
    rows = db.execute(stmt).scalars().all()
    return templates.TemplateResponse(request, "ingredients.html", {
        "user": user, "ingredients": rows, "q": q,
    })


@app.get("/ingredients/new", response_class=HTMLResponse)
def ingredient_new_form(request: Request):
    user = require_user(current_user(request, db))
    return templates.TemplateResponse(request, "ingredient_new.html", {"user": user})


@app.post("/ingredients/new")
def ingredient_new(request: Request, db: Session = Depends(get_db),
                   name: str = Form(...), category: str = Form(""),
                   nutrients_json: str = Form("{}")):
    import json as _json
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    try:
        nutrients = _json.loads(nutrients_json)
        if not isinstance(nutrients, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(400, "nutrients_json muss ein JSON-Objekt sein")
    db.add(Ingredient(household_id=hh.id, name=name, category=category,
                      nutrients=nutrients, source="manuell"))
    db.commit()
    return RedirectResponse("/ingredients", status_code=303)


@app.post("/ingredients/usda")
def ingredients_usda(request: Request, db: Session = Depends(get_db),
                     food_csv: bytes = Form(...), nutrient_csv: bytes = Form(...),
                     limit: int = Form(200)):
    from .importer import import_usda_fdc_csv
    user = require_user(current_user(request, db))
    hh = current_household(db, user)
    count = import_usda_fdc_csv(db, hh.id, food_csv, nutrient_csv, limit=limit)
    return RedirectResponse(f"/ingredients?q=&msg={count}+importiert", status_code=303)
