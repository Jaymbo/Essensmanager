# Persistenz: SQLAlchemy-Modelle (SQLite).
# Alle haushaltsbezogenen Tabellen haben household_id (Multi-Tenant lite).
# Globale Referenzdaten (NutrientDef, Process, InteractionRule) sind haushaltsfrei.

from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey,
                        Integer, String, UniqueConstraint, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DB_PATH = "/data/app.db"


class Base(DeclarativeBase):
    pass


# ---------- Globale Referenzdaten ----------

class NutrientDef(Base):
    """Eine Dimension im Nährstoffraum (global)."""
    __tablename__ = "nutrient_defs"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)   # z.B. 'vit_c'
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(16))               # mg, µg, g, kcal
    daily_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    daily_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    absorb_efficiency: Mapped[float] = mapped_column(Float, default=1.0)
    half_life_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    pool_capacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(400), default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class Process(Base):
    """Ein Kochprozess mit Retentionsfaktoren pro Nährstoff (global, editierbar)."""
    __tablename__ = "processes"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)   # 'fry', 'bake', ...
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(400), default="")
    factors: Mapped[dict] = mapped_column(JSON, default=dict)   # {nutrient_key: factor}
    source: Mapped[str] = mapped_column(String(400), default="")


class InteractionRule(Base):
    """Bioverfügbarkeits-Interaktion (global, editierbar)."""
    __tablename__ = "interaction_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(64))       # nutrient_key
    kind: Mapped[str] = mapped_column(String(16))         # enhancer | inhibitor
    compound: Mapped[str] = mapped_column(String(64))     # Stoff-Key der Mahlzeit
    effect: Mapped[float] = mapped_column(Float)          # max. relativer Effekt
    half_saturation: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(400), default="")


# ---------- Haushaltsbezogene Daten ----------

class Household(Base):
    __tablename__ = "households"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    users: Mapped[list["User"]] = relationship(back_populates="household")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    household: Mapped[Household] = relationship(back_populates="users")


class Person(Base):
    """Person im Haushalt mit individuellen Ziel-Overrides."""
    __tablename__ = "persons"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    name: Mapped[str] = mapped_column(String(120))
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    activity: Mapped[float] = mapped_column(Float, default=1.4)  # PAL 1.2-2.4
    target_override_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # {nutrient_key: {"min": x, "max": y}}


class Ingredient(Base):
    """Grundzutat: Nährwerte pro 100 g (haushaltsbezogen, kopierbar aus Seeds)."""
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id"), nullable=True)  # None = global/Seed
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80), default="")
    nutrients: Mapped[dict] = mapped_column(JSON, default=dict)  # per 100 g
    source: Mapped[str] = mapped_column(String(200), default="")
    usda_fdc_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    __table_args__ = (UniqueConstraint("household_id", "name"),)


class Recipe(Base):
    """Rezept: Zutatenzeilen + Prozessketten. Nährvektor wird gecacht."""
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    name: Mapped[str] = mapped_column(String(160))
    servings: Mapped[int] = mapped_column(Integer, default=4)
    instructions: Mapped[str] = mapped_column(String(4000), default="")
    nutrient_cache: Mapped[dict] = mapped_column(JSON, default=dict)  # gesamt + pro Portion
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lines: Mapped[list["RecipeLine"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan")


class RecipeLine(Base):
    """Eine Zutat im Rezept mit Prozesskette."""
    __tablename__ = "recipe_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    grams_raw: Mapped[float] = mapped_column(Float)
    process_chain: Mapped[list] = mapped_column(JSON, default=list)  # ['fry','bake']
    # Kochverluste: Rohgewicht -> verzehrfertiges Gewicht (Wasser-/Fettverlust)
    yield_factor: Mapped[float] = mapped_column(Float, default=1.0)
    recipe: Mapped[Recipe] = relationship(back_populates="lines")


class PantryItem(Base):
    """Vorrat: vorhandene Zutat mit Menge und Ablaufdatum."""
    __tablename__ = "pantry_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    grams: Mapped[float] = mapped_column(Float)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str] = mapped_column(String(40), default="fridge")  # fridge/pantry/freezer


class MealPlan(Base):
    __tablename__ = "meal_plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    start_date: Mapped[date] = mapped_column(Date)
    days: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft/confirmed
    entries: Mapped[list["PlanEntry"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan")


class PlanEntry(Base):
    """Eine geplante Mahlzeit: Rezept × Tag × Mahlzeit × Personen."""
    __tablename__ = "plan_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("meal_plans.id"))
    day_index: Mapped[int] = mapped_column(Integer)          # 0..days-1
    meal_slot: Mapped[str] = mapped_column(String(20))       # breakfast/lunch/dinner/snack
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    persons: Mapped[int] = mapped_column(Integer, default=1)
    plan: Mapped[MealPlan] = relationship(back_populates="entries")


class LogEntry(Base):
    """Tagebuch: tatsächlicher Verzehr – Basis der Körpersimulation."""
    __tablename__ = "log_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("households.id"))
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id"))
    date: Mapped[date] = mapped_column(Date)
    meal_slot: Mapped[str] = mapped_column(String(20), default="")
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id"), nullable=True)
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredients.id"), nullable=True)
    grams_consumed: Mapped[float] = mapped_column(Float)
    process_chain: Mapped[list] = mapped_column(JSON, default=list)
    nutrient_vector_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def make_engine(db_path: str = DB_PATH):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
