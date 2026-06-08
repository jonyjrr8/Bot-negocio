"""
Bot de Telegram para tu negocio - Registra ventas, gastos y ganancias
Requisitos: pip install python-telegram-bot anthropic
"""

import json
import os
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# ============================================================
# CONFIGURACIÓN - Edita estos valores
# ============================================================

TELEGRAM_TOKEN = "8885403907:AAFxKheE_jaCXAHrXt48J5wItDMN5q6tb_4"          # Token de @BotFather
ANTHROPIC_API_KEY = "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"  # Clave de console.anthropic.com

# Tus productos y la ganancia por unidad (en pesos)
PRODUCTOS = {
    "vaso": 10,
    "refresco": 8,
    "agua": 5,
    "camisa": 50,
    "pantalon": 80,
    "calcetines": 15,
    "leche": 6,
    "pan": 3,
    "jugo": 12,
    "cafe": 15,
}

# Tu ID de Telegram (solo tú ves las ganancias y resúmenes)
DUENO_ID = 7924667382

# IDs de empleados autorizados (agrega los de tus empleados aquí)
# Deja vacío [] para que cualquiera pueda registrar ventas
EMPLEADOS_AUTORIZADOS = []  # Ejemplo: [111111111, 222222222]

# ============================================================
# BASE DE DATOS (archivo JSON simple)
# ============================================================

DB_FILE = "negocio_data.json"

def cargar_datos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"movimientos": []}

def guardar_datos(datos):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def agregar_movimiento(tipo, descripcion, monto, ganancia=0):
    datos = cargar_datos()
    datos["movimientos"].append({
        "tipo": tipo,           # "venta" o "gasto"
        "descripcion": descripcion,
        "monto": monto,
        "ganancia": ganancia,
        "fecha": datetime.now().isoformat()
    })
    guardar_datos(datos)

# ============================================================
# IA - Interpreta los mensajes de los empleados
# ============================================================

cliente_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PRODUCTOS_STR = "\n".join([f"- {p}: ganancia ${g} por unidad" for p, g in PRODUCTOS.items()])

SYSTEM_PROMPT = f"""Eres el asistente de un negocio pequeño en México. Tu tarea es interpretar mensajes de empleados y extraer información de ventas o gastos.

Productos conocidos y su ganancia por unidad:
{PRODUCTOS_STR}

Cuando recibas un mensaje, responde ÚNICAMENTE con un JSON con este formato:
{{
  "tipo": "venta" | "gasto" | "desconocido",
  "descripcion": "descripción breve",
  "monto": número (precio total cobrado, 0 si no se menciona),
  "ganancia": número (ganancia total calculada),
  "items": [{{"producto": "nombre", "cantidad": número, "ganancia_unitaria": número}}],
  "mensaje_confirmacion": "mensaje amigable para confirmar al empleado"
}}

Reglas:
- Si dice "se vendieron 3 vasos", calcula ganancia = 3 × 10 = 30 pesos
- Si dice "gasto de 200 en limpieza", tipo=gasto, monto=200, ganancia=0
- Si el producto no está en la lista, calcula con ganancia 0 y anótalo
- El mensaje_confirmacion debe ser en español, amigable y breve
- Si no entiendes el mensaje, tipo="desconocido"
- Responde SOLO el JSON, sin texto adicional
"""

def interpretar_mensaje(texto):
    try:
        respuesta = cliente_ai.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto}]
        )
        contenido = respuesta.content[0].text.strip()
        contenido = re.sub(r"```json|```", "", contenido).strip()
        return json.loads(contenido)
    except Exception as e:
        return None

# ============================================================
# RESÚMENES
# ============================================================

def calcular_resumen(dias=1):
    datos = cargar_datos()
    ahora = datetime.now()
    limite = ahora - timedelta(days=dias)

    ventas_total = 0
    gastos_total = 0
    ganancias_total = 0
    movimientos_periodo = []

    for m in datos["movimientos"]:
        fecha = datetime.fromisoformat(m["fecha"])
        if fecha >= limite:
            movimientos_periodo.append(m)
            if m["tipo"] == "venta":
                ventas_total += m.get("monto", 0)
                ganancias_total += m.get("ganancia", 0)
            elif m["tipo"] == "gasto":
                gastos_total += m.get("monto", 0)

    return {
        "ventas": ventas_total,
        "gastos": gastos_total,
        "ganancias": ganancias_total,
        "neto": ganancias_total - gastos_total,
        "num_movimientos": len(movimientos_periodo)
    }

def formatear_resumen(r, titulo):
    return (
        f"📊 *{titulo}*\n\n"
        f"💰 Ventas: ${r['ventas']:,.0f}\n"
        f"📈 Ganancias brutas: ${r['ganancias']:,.0f}\n"
        f"📉 Gastos: ${r['gastos']:,.0f}\n"
        f"✅ *Ganancia neta: ${r['neto']:,.0f}*\n\n"
        f"📝 Movimientos registrados: {r['num_movimientos']}"
    )

# ============================================================
# HANDLERS DEL BOT
# ============================================================

def es_dueno(user_id):
    return user_id == DUENO_ID

def es_autorizado(user_id):
    if es_dueno(user_id):
        return True
    if not EMPLEADOS_AUTORIZADOS:
        return True
    return user_id in EMPLEADOS_AUTORIZADOS

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    productos_lista = "\n".join([f"  • {p} → +${g}" for p, g in PRODUCTOS.items()])
    await update.message.reply_text(
        "👋 ¡Hola! Soy el bot de tu negocio.\n\n"
        "📦 *Productos configurados:*\n"
        f"{productos_lista}\n\n"
        "📝 *Comandos disponibles:*\n"
        "/hoy — Resumen del día\n"
        "/semana — Resumen semanal\n"
        "/ayuda — Ver instrucciones\n\n"
        "Para registrar, solo manda un mensaje normal como:\n"
        "_'Se vendieron 5 vasos'_\n"
        "_'Gasto de 150 en bolsas'_",
        parse_mode="Markdown"
    )

async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_dueno(update.effective_user.id):
        await update.message.reply_text("⛔ Solo el dueño puede ver los reportes.")
        return
    r = calcular_resumen(dias=1)
    await update.message.reply_text(formatear_resumen(r, "Resumen de hoy"), parse_mode="Markdown")

async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_dueno(update.effective_user.id):
        await update.message.reply_text("⛔ Solo el dueño puede ver los reportes.")
        return
    r = calcular_resumen(dias=7)
    await update.message.reply_text(formatear_resumen(r, "Resumen de la semana"), parse_mode="Markdown")

async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *¿Cómo usar el bot?*\n\n"
        "*Registrar ventas:*\n"
        "• 'Se vendieron 3 vasos'\n"
        "• 'Vendí 2 camisas y 1 pantalón'\n"
        "• 'Venta de 5 refrescos'\n\n"
        "*Registrar gastos:*\n"
        "• 'Gasto de 200 en limpieza'\n"
        "• 'Compré bolsas por 80 pesos'\n\n"
        "*Ver reportes:*\n"
        "/hoy — Ver el resumen de hoy\n"
        "/semana — Ver la semana completa",
        parse_mode="Markdown"
    )

async def manejar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_autorizado(update.effective_user.id):
        await update.message.reply_text("⛔ No tienes acceso a este bot.")
        return

    texto = update.message.text
    nombre = update.effective_user.first_name or "empleado"

    await update.message.reply_text("⏳ Procesando...")

    resultado = interpretar_mensaje(texto)

    if not resultado or resultado.get("tipo") == "desconocido":
        await update.message.reply_text(
            "❓ No entendí ese mensaje. Intenta con algo como:\n"
            "• 'Se vendieron 3 vasos'\n"
            "• 'Gasto de 100 pesos en bolsas'"
        )
        return

    tipo = resultado["tipo"]
    descripcion = resultado.get("descripcion", texto)
    monto = resultado.get("monto", 0)
    ganancia = resultado.get("ganancia", 0)
    confirmacion = resultado.get("mensaje_confirmacion", "Registrado correctamente.")

    agregar_movimiento(tipo, descripcion, monto, ganancia)

    icono = "🛒" if tipo == "venta" else "💸"

    if es_dueno(update.effective_user.id):
        detalle = f"\n📈 Ganancia: ${ganancia:,.0f}" if tipo == "venta" else f"\n📉 Gasto: ${monto:,.0f}"
        await update.message.reply_text(
            f"{icono} *{confirmacion}*\n"
            f"👤 Registrado por: {nombre}"
            f"{detalle}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"{icono} ¡Registrado! Gracias {nombre} 👍")

# ============================================================
# ARRANCAR EL BOT
# ============================================================

def main():
    print("🤖 Bot iniciando...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("hoy", cmd_hoy))
    app.add_handler(CommandHandler("semana", cmd_semana))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_mensaje))

    print("✅ Bot corriendo. Presiona Ctrl+C para detener.")
    app.run_polling()

if __name__ == "__main__":
    main()
