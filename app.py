import os
import math
from dataclasses import dataclass
from dotenv import load_dotenv

import streamlit as st
from openai import OpenAI

# ----------------------------
# MacroMate: Macro Coach
# ----------------------------

load_dotenv()

st.set_page_config(page_title="MacroMate", page_icon="🥗", layout="centered")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

st.title("🥗 MacroMate")
st.caption("A simple macro coach (education + planning). Not medical advice.")

with st.expander("Important note"):
    st.write(
        "MacroMate provides general fitness nutrition guidance only. "
        "If you have a medical condition, history of eating disorders, "
        "or are under 18, consider using this with a qualified professional."
    )

# ----------------------------
# Helpers
# ----------------------------

@dataclass
class UserProfile:
    sex: str
    age: int
    height_cm: float
    weight_kg: float
    activity: str
    goal: str
    pace: str

ACTIVITY_MULTIPLIERS = {
    "Sedentary (little/no exercise)": 1.2,
    "Light (1–3 days/wk)": 1.375,
    "Moderate (3–5 days/wk)": 1.55,
    "Very active (6–7 days/wk)": 1.725,
    "Athlete (2x/day training)": 1.9,
}

def mifflin_st_jeor(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    # BMR estimate
    if sex == "Male":
        return 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    else:
        return 10 * weight_kg + 6.25 * height_cm - 5 * age - 161

def round_to(n: float, base: int = 5) -> int:
    return int(base * round(n / base))

def compute_calorie_target(tdee: float, goal: str, pace: str) -> int:
    # Conservative defaults
    if goal == "Maintain":
        delta = 0
    elif goal == "Cut":
        delta = -300 if pace == "Slow" else (-500 if pace == "Standard" else -700)
    else:  # Bulk
        delta = +200 if pace == "Slow" else (+300 if pace == "Standard" else +450)

    # Keep a sensible floor (very rough)
    target = max(1200, tdee + delta)
    return round_to(target, 10)

def compute_macros(weight_kg: float, calories: int, goal: str):
    """
    Simple macro model:
    - Protein: 1.8g/kg (cut/maintain) or 1.6g/kg (bulk)
    - Fat:     0.8g/kg (cut/maintain) or 0.9g/kg (bulk)
    - Carbs:   remainder
    """
    if goal == "Bulk":
        protein_g = 1.6 * weight_kg
        fat_g = 0.9 * weight_kg
    else:
        protein_g = 1.8 * weight_kg
        fat_g = 0.8 * weight_kg

    protein_cal = protein_g * 4
    fat_cal = fat_g * 9
    remaining = max(0, calories - (protein_cal + fat_cal))
    carbs_g = remaining / 4

    # Round nicely
    return {
        "protein_g": round(protein_g),
        "fat_g": round(fat_g),
        "carbs_g": round(carbs_g),
        "calories": calories,
    }

def macro_percentages(macros: dict):
    cals = macros["calories"]
    p = macros["protein_g"] * 4
    f = macros["fat_g"] * 9
    c = macros["carbs_g"] * 4
    # avoid div by 0
    if cals <= 0:
        return (0, 0, 0)
    return (p / cals * 100, c / cals * 100, f / cals * 100)

# ----------------------------
# UI inputs
# ----------------------------

col1, col2 = st.columns(2)
with col1:
    sex = st.selectbox("Sex", ["Male", "Female"])
    age = st.number_input("Age", min_value=13, max_value=90, value=19, step=1)
    height_cm = st.number_input("Height (cm)", min_value=120.0, max_value=230.0, value=180.0, step=0.5)
with col2:
    weight_kg = st.number_input("Weight (kg)", min_value=35.0, max_value=200.0, value=80.0, step=0.5)
    activity = st.selectbox("Activity level", list(ACTIVITY_MULTIPLIERS.keys()))
    

goal = st.radio("Goal", ["Cut", "Maintain", "Bulk"], horizontal=True)
pace = st.select_slider("Pace", options=["Slow", "Standard", "Aggressive"], value="Standard")


profile = UserProfile(
    sex=sex,
    age=int(age),
    height_cm=float(height_cm),
    weight_kg=float(weight_kg),
    activity=activity,
    goal=goal,
    pace=pace,
)

# ----------------------------
# Calculate
# ----------------------------

bmr = mifflin_st_jeor(profile.sex, profile.weight_kg, profile.height_cm, profile.age)
tdee = bmr * ACTIVITY_MULTIPLIERS[profile.activity]
cal_target = compute_calorie_target(tdee, profile.goal, profile.pace)
macros = compute_macros(profile.weight_kg, cal_target, profile.goal)
p_pct, c_pct, f_pct = macro_percentages(macros)

st.subheader("Your targets")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Calories", f'{macros["calories"]} kcal')
c2.metric("Protein", f'{macros["protein_g"]} g')
c3.metric("Carbs", f'{macros["carbs_g"]} g')
c4.metric("Fat", f'{macros["fat_g"]} g')

st.caption(
    f"Macro split (approx): Protein {p_pct:.0f}% • Carbs {c_pct:.0f}% • Fat {f_pct:.0f}%"
)

with st.expander("How this was estimated"):
    st.write(
        f"- BMR (Mifflin–St Jeor): **{bmr:.0f} kcal/day**\n"
        f"- Activity multiplier: **{ACTIVITY_MULTIPLIERS[profile.activity]}**\n"
        f"- Estimated TDEE: **{tdee:.0f} kcal/day**\n"
        f"- Goal adjustment ({profile.goal}, {profile.pace}): built into calorie target\n"
        "- Macros: protein + fat set by bodyweight, carbs = remaining calories"
    )

# ----------------------------
# AI plan generation
# ----------------------------

st.subheader("Meal Plan Generator 🍔")

if not OPENAI_API_KEY:
    st.info("Add your OPENAI_API_KEY in a .env file to enable the AI plan.")
else:
    generate = st.button("Generate my MacroMate plan ✨", use_container_width=True)

    if generate:
        with st.spinner("Cooking up your plan..."):
            # Keep it conservative and non-medical.
            user_context = {
                "age": profile.age,
                "sex": profile.sex,
                "height_cm": profile.height_cm,
                "weight_kg": profile.weight_kg,
                "activity": profile.activity,
                "goal": profile.goal,
                "pace": profile.pace,
                "targets": macros,
    
            }

            prompt = f"""
You are MacroMate, a helpful fitness nutrition coach.
You provide general educational guidance. You do NOT diagnose or treat medical conditions.
Be practical, concise, and supportive.

Given this user profile (JSON):
{user_context}

Output:
1) A short plan for hitting the daily targets (meals structure + protein strategy).
2) A 1-day sample menu (breakfast/lunch/dinner/snack) with rough macros per meal.
3) A "weekly check-in rule" (how to adjust calories if weight trend is not moving).
4) 3 simple grocery staples list.

Constraints:
- Avoid medical claims.
- Prefer generally accessible whole foods.
"""
            # Using Responses API (recommended for new projects)
            response = client.responses.create(
                model="gpt-4o-mini",
                input=prompt,
            )

            st.markdown(response.output_text)