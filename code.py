from flask import Flask, request, jsonify
import pymysql
import requests
import razorpay
import uuid
import re
import json
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# ====================== CONFIG ======================
INTERAKT_API_KEY     = os.getenv("INTERAKT_API_KEY")
INTERAKT_BASE_URL    = "https://api.interakt.ai/v1/public/message/"
RAZORPAY_KEY_ID      = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET  = os.getenv("RAZORPAY_KEY_SECRET")
PAYMENT_CALLBACK_URL = os.getenv("PAYMENT_CALLBACK_URL", "https://e104-152-59-63-187.ngrok-free.app/payment-callback")

HEADERS = {
    "Authorization": f"Basic {INTERAKT_API_KEY}",
    "Content-Type": "application/json"
}

PLAN_LABELS = {
    "single":  "Single (1 day)",
    "weekly":  "Weekly (5 days)",
    "monthly": "Monthly (22 days)"
}

# ====================== FACEBOOK CATALOGUE CONFIG ======================
# FACEBOOK_CATALOG_ID  → Facebook Commerce Manager → Catalogue → Settings → Catalogue ID
# Each PRODUCT_SET_ID  → Facebook Commerce Manager → Product Sets → click set → ID in URL
# Slugs in PRODUCT_SET_SLUGS MUST exactly match the retailer_id you uploaded to Facebook

FACEBOOK_CATALOG_ID = "1012376341036855"

PRODUCT_SET_IDS = {
    "salad_fat_loss":    os.getenv("PS_SALAD_FAT_LOSS",    "1296924445748721"),
    "salad_muscle_gain": os.getenv("PS_SALAD_MUSCLE_GAIN", "1304523094481778"),
    "salad_all":         os.getenv("PS_SALAD_ALL",         "1555858869215898"),
    "superbowl_all":     os.getenv("PS_SUPERBOWL_ALL",     "1007239245391926"),
}

# These slugs MUST match the retailer_id / id in Facebook Commerce Manager exactly
PRODUCT_SET_PRODUCTS = {

    "salad_fat_loss": [
        "27136814455952298",  # weight_loss_box
        "27361857856785901",  # classic_veggies_salad
        "26909528732045280",  # protein_balance_box
        "36157212247203108",  # chicken_salad_box
    ],

    "salad_muscle_gain": [
        "27201907166093203",  # muscle_gain_salad
        "36157212247203108",  # chicken_salad_box
        "26909528732045280",  # protein_balance_box
        "27361857856785901",  # classic_veggies_salad
    ],

    "salad_all": [
        "27136814455952298",
        "27361857856785901",
        "27201907166093203",
        "26909528732045280",
        "36157212247203108",
    ],

    "superbowl_all": [
        "27242749095413825",  # veg_super_bowl
        "35767294522918976",  # mix_super_bowl
        "26594981386839009",  # chicken_super_bowl
    ]
}

# ====================== DATABASE ======================

def get_db():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DB", "salad_oclock"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

# ====================== DB HELPERS ======================

def db_get_user(cursor, phone):
    cursor.execute("SELECT * FROM users WHERE phone_number = %s", (phone,))
    return cursor.fetchone()


def db_upsert_user(cursor, phone):
    cursor.execute(
        "INSERT IGNORE INTO users (phone_number, step) VALUES (%s, 'greeting')",
        (phone,)
    )
    return db_get_user(cursor, phone)


def db_update_user(cursor, phone, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k}=%s" for k in fields)
    cursor.execute(
        f"UPDATE users SET {set_clause} WHERE phone_number=%s",
        list(fields.values()) + [phone]
    )


def db_is_pincode_serviceable(cursor, pincode):
    cursor.execute(
        "SELECT id FROM serviceable_pincodes WHERE pincode=%s AND is_active=1",
        (pincode,)
    )
    return cursor.fetchone() is not None


def db_get_products_for_menu(cursor, category_slug, goal=None):
    if goal:
        cursor.execute("""
            SELECT p.id, p.slug, p.name, p.description, p.is_recommended, p.target_goal
            FROM   products p
            JOIN   categories c ON c.id = p.category_id
            WHERE  c.slug = %s AND p.is_active = 1
            ORDER BY
                (p.is_recommended = 1 AND p.target_goal = %s) DESC,
                p.display_order ASC
        """, (category_slug, goal))
    else:
        cursor.execute("""
            SELECT p.id, p.slug, p.name, p.description, p.is_recommended, p.target_goal
            FROM   products p
            JOIN   categories c ON c.id = p.category_id
            WHERE  c.slug = %s AND p.is_active = 1
            ORDER BY p.display_order ASC
        """, (category_slug,))
    return cursor.fetchall()


def db_get_product_by_slug(cursor, slug):
    cursor.execute("""
        SELECT p.*, c.slug AS category_slug, c.name AS category_name
        FROM   products p
        JOIN   categories c ON c.id = p.category_id
        WHERE  p.slug = %s AND p.is_active = 1
    """, (slug,))
    return cursor.fetchone()


def db_get_price(cursor, product_id, plan):
    cursor.execute(
        "SELECT price, days FROM product_prices "
        "WHERE product_id=%s AND plan=%s AND is_active=1",
        (product_id, plan)
    )
    return cursor.fetchone()


def db_get_all_prices(cursor, product_id):
    cursor.execute(
        "SELECT plan, price, days FROM product_prices "
        "WHERE product_id=%s AND is_active=1 "
        "ORDER BY FIELD(plan,'single','weekly','monthly')",
        (product_id,)
    )
    return cursor.fetchall()


def db_get_order(cursor, order_id):
    cursor.execute("""
        SELECT o.*,
               u.phone_number,
               u.name  AS customer_name,
               p.name  AS product_name,
               p.slug  AS product_slug
        FROM   orders o
        JOIN   users u  ON u.id = o.user_id
        JOIN   products p ON p.id = o.product_id
        WHERE  o.order_id = %s
    """, (order_id,))
    return cursor.fetchone()


def db_create_order(cursor, order_id, user_id, phone, product_id,
                    plan, amount, address, rz_order_id, rz_payment_link_id,
                    start_date, end_date):
    cursor.execute("""
        INSERT INTO orders
            (order_id, user_id, phone_number, product_id, plan, amount,
             delivery_address, payment_status,
             razorpay_order_id, razorpay_payment_link_id,
             delivery_start_date, delivery_end_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, %s)
    """, (order_id, user_id, phone, product_id, plan, amount,
          address, rz_order_id, rz_payment_link_id, start_date, end_date))


def db_call_generate_schedule(cursor, order_id):
    try:
        cursor.callproc("sp_generate_delivery_schedule", (order_id,))
    except Exception as e:
        print(f"[sp_generate_delivery_schedule error] {e}")


def db_log_message(cursor, user_id, phone, direction, msg_type, content, step, raw=None):
    try:
        cursor.execute("""
            INSERT INTO conversation_logs
                (user_id, phone_number, direction, message_type,
                 content, step_at_time, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (user_id, phone, direction, msg_type, content, step,
              json.dumps(raw) if raw else None))
    except Exception as e:
        print(f"[db_log_message error] {e}")


def db_log_payment_event(cursor, order_id, event, payment_id,
                         rz_order_id, amount, status, raw=None):
    try:
        cursor.execute("""
            INSERT INTO payment_events
                (order_id, razorpay_event, razorpay_payment_id,
                 razorpay_order_id, amount, status, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (order_id, event, payment_id, rz_order_id, amount, status,
              json.dumps(raw) if raw else None))
    except Exception as e:
        print(f"[db_log_payment_event error] {e}")

# ====================== UTILITIES ======================

def is_valid_name(name):
    if not name or len(name.strip()) < 3:
        return False
    return bool(re.match(r'^[a-zA-Z\s]+$', name.strip()))


def is_open():
    return 7 <= datetime.now().hour < 20


def next_working_day(from_date=None):
    d = (from_date or date.today()) + timedelta(days=1)
    while d.weekday() == 6:   # skip Sunday
        d += timedelta(days=1)
    return d


def compute_end_date(start_date, days):
    counted, current, last = 0, start_date, start_date
    while counted < days:
        if current.weekday() != 6:
            counted += 1
            last = current
        if counted < days:
            current += timedelta(days=1)
    return last


def price_summary(prices):
    return " · ".join(f"₹{int(r['price'])}/{r['plan']}" for r in prices)


def clean_phone(phone):
    phone = re.sub(r'\D', '', str(phone))
    if phone.startswith('91') and len(phone) == 12:
        phone = phone[2:]
    return phone[-10:]


# ====================== GOAL RESOLVER ======================
# ROOT CAUSE FIX:
# Interakt does NOT always send button taps as InteractiveButtonReply.
# It often sends content_type="text" with msg.message = "💪 Muscle Gain"
# (the button title text verbatim, including the emoji prefix).
# resolve_goal() handles ALL cases: button id, emoji title, plain title, partial match.

_GOAL_ID_MAP = {
    "goal_fat_loss":      "Fat Loss",
    "goal_muscle_gain":   "Muscle Gain",
    "goal_healthy_meals": "Healthy Meals",
}

# Keys are lowercase, emoji-stripped versions of what Interakt may send
_GOAL_TEXT_MAP = {
    "fat loss":      "Fat Loss",
    "muscle gain":   "Muscle Gain",
    "healthy meals": "Healthy Meals",
    "healthy meal":  "Healthy Meals",
}


def resolve_goal(button_data, text):
    """
    Returns "Fat Loss" / "Muscle Gain" / "Healthy Meals" or None.
    Checks button id first, then strips emoji from text and matches.
    """
    # 1. Proper button id (when Interakt does send InteractiveButtonReply correctly)
    if button_data and button_data in _GOAL_ID_MAP:
        return _GOAL_ID_MAP[button_data]

    # 2. Interakt sends button title as plain text — strip all non-ASCII + punctuation,
    #    lowercase, and match against known goal phrases
    raw = (text or "").strip()
    # Remove emoji and special characters, keep only letters, digits, spaces
    cleaned = re.sub(r'[^\w\s]', '', raw).strip().lower()
    # Also remove standalone digits left over
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if cleaned in _GOAL_TEXT_MAP:
        return _GOAL_TEXT_MAP[cleaned]

    # 3. Partial / contains match (handles "Hey Rushi! ... 💪 Muscle Gain" edge cases)
    for phrase, goal in _GOAL_TEXT_MAP.items():
        if phrase in cleaned:
            return goal

    return None


# ====================== CATEGORY RESOLVER ======================
# Same problem as goals — Interakt may echo button title for category buttons

_CATEGORY_ID_MAP = {
    "cat_salads":     "salad",
    "cat_superbowls": "superbowl",
}

_CATEGORY_TEXT_MAP = {
    "salads":     "salad",
    "salad":      "salad",
    "superbowls": "superbowl",
    "superbowl":  "superbowl",
}


def resolve_category(button_data, text):
    """Returns "salad" / "superbowl" or None."""
    if button_data and button_data in _CATEGORY_ID_MAP:
        return _CATEGORY_ID_MAP[button_data]
    cleaned = re.sub(r'[^\w\s]', '', (text or "")).strip().lower()
    if cleaned in _CATEGORY_TEXT_MAP:
        return _CATEGORY_TEXT_MAP[cleaned]
    for phrase, cat in _CATEGORY_TEXT_MAP.items():
        if phrase in cleaned:
            return cat
    return None


# ====================== RAZORPAY ======================

def create_razorpay_link(amount_inr, phone, order_id, item_name, plan):
    try:
        client   = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        rz_order = client.order.create({
            "amount":   int(amount_inr) * 100,
            "currency": "INR",
            "receipt":  order_id,
            "notes":    {"phone": phone, "item": item_name, "plan": plan}
        })
        link = client.payment_link.create({
            "amount":          int(amount_inr) * 100,
            "currency":        "INR",
            "description":     f"Salad O'Clock – {item_name} ({PLAN_LABELS.get(plan, plan)})",
            "customer":        {"contact": f"+91{clean_phone(phone)}"},
            "notify":          {"sms": True, "whatsapp": False},
            "callback_url":    PAYMENT_CALLBACK_URL,
            "callback_method": "get",
            "notes":           {"order_id": order_id}
        })
        return rz_order["id"], link["id"], link["short_url"]
    except Exception as e:
        print(f"[Razorpay error] {e}")
        return None, None, None

# ====================== INTERAKT SENDERS ======================

def _post_to_interakt(payload, label="message"):
    try:
        print(f"\n[Interakt → {label}]")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        resp = requests.post(
            INTERAKT_BASE_URL,
            headers=HEADERS,
            json=payload,
            timeout=10
        )
        print(f"[Interakt ← {label}] status={resp.status_code} body={resp.text}")
        return resp
    except Exception as e:
        print(f"[Interakt error → {label}] {e}")
        return None


def send_text(phone, message):
    payload = {
        "countryCode": "+91",
        "phoneNumber":  clean_phone(phone),
        "callbackData": "bot_text",
        "type": "Text",
        "data": {"message": message}
    }
    _post_to_interakt(payload, "send_text")


def send_button_message(phone, body, buttons):
    """Max 3 buttons. Each button: {'id': str, 'title': str}"""
    formatted = [
        {
            "type": "reply",
            "reply": {
                "id":    b["id"],
                "title": b["title"][:20]
            }
        }
        for b in buttons[:3]
    ]
    payload = {
        "countryCode": "+91",
        "phoneNumber":  clean_phone(phone),
        "callbackData": "bot_button",
        "type": "InteractiveButton",
        "data": {
            "message": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": formatted}
            }
        }
    }
    _post_to_interakt(payload, "send_button_message")


def send_interactive_list(phone, body_text, sections, button_label="View Options"):
    payload = {
        "countryCode": "+91",
        "phoneNumber":  clean_phone(phone),
        "callbackData": "bot_list",
        "type": "InteractiveList",
        "data": {
            "message": {
                "type": "list",
                "body": {"text": body_text},
                "action": {
                    "button":   button_label[:20],
                    "sections": sections
                }
            }
        }
    }
    _post_to_interakt(payload, "send_interactive_list")


def send_catalogue_message(phone, header_text, body_text, set_key):
    """
    Sends a WhatsApp product_list (catalogue) message.
    Returns True on success, False if not configured (caller uses fallback list).

    product_retailer_id in each product_item MUST exactly match the id/slug
    used when uploading products to Facebook Commerce Manager.
    """
    product_ids = PRODUCT_SET_PRODUCTS.get(set_key, [])
    if not product_ids or not FACEBOOK_CATALOG_ID:
        print(f"⚠️ Catalogue not configured for set_key={set_key}")
        return False

    product_items = [{"product_retailer_id": pid} for pid in product_ids]
    print("PRODUCT ITEMS BEING SENT:")
    print(json.dumps(product_items, indent=2))

    payload = {
        "countryCode": "+91",
        "phoneNumber":  clean_phone(phone),
        "callbackData": "catalogue_menu",
        "type": "InteractiveProductList",
        "data": {
            "message": {
                "type": "product_list",
                "header": {
                    "type": "text",
                    "text": header_text
                },
                "body": {"text": body_text},
                "action": {
                    "catalog_id": FACEBOOK_CATALOG_ID,
                    "sections": [
                        {
                            "title": re.sub(r'[^\x00-\x7F]+', '', header_text).strip()[:24],
                            "product_items": product_items
                        }
                    ]
                }
            }
        }
    }
    _post_to_interakt(payload, "send_catalogue")
    return True

# ====================== FLOW BUILDERS ======================

def send_goal_selection(phone, name):
    send_button_message(
        phone,
        f"Hey {name}! 👋 Welcome to *Salad O'Clock* 🥗\n\nWhat's your main health goal?",
        [
            {"id": "goal_fat_loss",      "title": "🔥 Fat Loss"},
            {"id": "goal_muscle_gain",   "title": "💪 Muscle Gain"},
            {"id": "goal_healthy_meals", "title": "🥗 Healthy Meals"},
        ]
    )


def show_category_selection(phone):
    send_button_message(
        phone,
        "🌿 *Healthy Meals* – What would you like today?\n\nChoose a category:",
        [
            {"id": "cat_salads",     "title": "🥗 Salads"},
            {"id": "cat_superbowls", "title": "🍜 Superbowls"},
        ]
    )


def show_menu(phone, cursor, category_slug, goal=None):
    """
    Shows the product catalogue. Falls back to interactive list if
    Facebook catalogue is not configured.
    """
    if category_slug == "salad":
        if goal == "Fat Loss":
            set_key = "salad_fat_loss"
            header  = "🔥 Fat Loss Salads"
            body    = "Best salads for your weight loss goal ⭐\nTap any item to view & add to cart."
        elif goal == "Muscle Gain":
            set_key = "salad_muscle_gain"
            header  = "💪 Muscle Gain Salads"
            body    = "High protein salads for muscle building ⭐\nTap any item to view & add to cart."
        else:
            set_key = "salad_all"
            header  = "🥗 All Salads"
            body    = "Browse our complete salad menu.\nTap any item to view & add to cart."
    else:
        set_key = "superbowl_all"
        header  = "🍜 Superbowls Menu"
        body    = "Browse our superbowl collection.\nTap any item to view & add to cart."

    # Try WhatsApp catalogue first
    sent = send_catalogue_message(phone, header, body, set_key)

    if not sent:
        # Fallback: interactive list (when Facebook catalogue not yet configured)
        print("⚠️ Using fallback interactive list — configure Facebook catalogue to show images + prices")
        products = db_get_products_for_menu(cursor, category_slug, goal)
        if not products:
            send_text(phone, "⚠️ Menu unavailable right now. Please try again later.")
            return
        rows = []
        for p in products:
            prices = db_get_all_prices(cursor, p["id"])
            label  = ("⭐ " + p["name"]) if (p["is_recommended"] and goal
                                              and p["target_goal"] == goal) else p["name"]
            rows.append({
                "id":          f"{category_slug}_{p['slug']}",
                "title":       label[:24],
                "description": price_summary(prices)[:72]
            })
        btn_label = "Pick a Salad" if category_slug == "salad" else "Pick a Superbowl"
        send_interactive_list(
            phone,
            header,
            [{"title": header.replace("*", ""), "rows": rows}],
            btn_label
        )


def send_plan_selection(phone, cursor, product_id, item_name):
    prices    = db_get_all_prices(cursor, product_id)
    plan_desc = {
        "single":  "Try it once · no commitment",
        "weekly":  "5 deliveries · Mon–Sat",
        "monthly": "22 deliveries · best value 💰"
    }
    rows = [
        {
            "id":          f"plan_{r['plan']}",
            "title":       f"{PLAN_LABELS[r['plan']]} – ₹{int(r['price'])}",
            "description": plan_desc.get(r["plan"], "")
        }
        for r in prices
    ]
    send_interactive_list(
        phone,
        f"✅ Great choice – *{item_name}*!\n\nPick your plan:",
        [{"title": "📅 Choose a Plan", "rows": rows}],
        "Pick a Plan"
    )


def send_order_summary(phone, cursor, user):
    product = db_get_product_by_slug(cursor, user["selected_item"])
    if not product:
        send_text(phone, "⚠️ Something went wrong. Please type *hi* to restart.")
        return
    price_row = db_get_price(cursor, product["id"], user["selected_plan"])
    if not price_row:
        send_text(phone, "⚠️ Pricing unavailable. Please type *hi* to restart.")
        return

    plan_label = PLAN_LABELS.get(user["selected_plan"], user["selected_plan"])
    summary = (
        f"🧾 *Order Summary*\n"
        f"──────────────────\n"
        f"👤 Name:    {user['name']}\n"
        f"🥗 Item:    {product['name']}\n"
        f"📋 Plan:    {plan_label}\n"
        f"📍 Address: {user['delivery_address']}\n"
        f"💰 Total:   ₹{int(price_row['price'])}\n"
        f"──────────────────\n"
        f"Shall we confirm your order?"
    )
    send_button_message(phone, summary, [
        {"id": "confirm_order", "title": "✅ Confirm Order"},
        {"id": "cancel_order",  "title": "❌ Cancel"},
    ])


def process_confirmed_order(phone, cursor, db_conn, user):
    product = db_get_product_by_slug(cursor, user["selected_item"])
    if not product:
        send_text(phone, "⚠️ Item not found. Please type *hi* to restart.")
        return
    price_row = db_get_price(cursor, product["id"], user["selected_plan"])
    if not price_row:
        send_text(phone, "⚠️ Pricing unavailable. Please type *hi* to restart.")
        return

    amount     = price_row["price"]
    days       = price_row["days"]
    order_id   = f"SOC-{uuid.uuid4().hex[:8].upper()}"
    start_date = next_working_day()
    end_date   = compute_end_date(start_date, days)

    rz_order_id, rz_link_id, payment_link = create_razorpay_link(
        amount, phone, order_id, product["name"], user["selected_plan"]
    )

    db_create_order(
        cursor,
        order_id           = order_id,
        user_id            = user["id"],
        phone              = phone,
        product_id         = product["id"],
        plan               = user["selected_plan"],
        amount             = amount,
        address            = user["delivery_address"],
        rz_order_id        = rz_order_id,
        rz_payment_link_id = rz_link_id,
        start_date         = start_date,
        end_date           = end_date
    )
    db_conn.commit()

    db_update_user(cursor, phone, step="done")
    db_conn.commit()

    if payment_link:
        send_text(
            phone,
            f"🎉 *Order Placed!* Your order ID is *{order_id}*.\n\n"
            f"💳 Complete your payment here:\n{payment_link}\n\n"
            f"Once payment is received, we'll confirm your delivery! 🥗"
        )
    else:
        send_text(
            phone,
            f"🎉 *Order Placed!* Your order ID is *{order_id}*.\n\n"
            f"⚠️ We couldn't generate a payment link right now. "
            f"Our team will contact you on WhatsApp shortly."
        )


def notify_payment_confirmed(phone, order_id, product_name, plan):
    send_text(
        phone,
        f"✅ *Payment Confirmed!*\n\n"
        f"🧾 Order ID: *{order_id}*\n"
        f"🥗 {product_name} – {PLAN_LABELS.get(plan, plan)}\n\n"
        f"Your first delivery starts tomorrow! 🚴\n"
        f"Thank you for choosing *Salad O'Clock* 💚"
    )

# ====================== WEBHOOK ======================

@app.route('/webhook', methods=['POST'])
def webhook():
    print("\n" + "=" * 80)
    print(f"WEBHOOK HIT → {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    raw_data = request.get_json(silent=True) or {}
    print("FULL PAYLOAD:")
    print(json.dumps(raw_data, indent=2, ensure_ascii=False))
    print("=" * 80)

    # ── VARIABLES ─────────────────────────────────────────────────────────────
    phone          = None
    text           = ""
    button_data    = None   # set only for proper InteractiveButtonReply / InteractiveListReply
    profile_name   = None
    catalogue_slug = None   # set when user taps a product in a WhatsApp catalogue

    # ── PAYLOAD EXTRACTION ────────────────────────────────────────────────────
    if raw_data.get("type") == "message_received":
        d        = raw_data.get("data", {})
        customer = d.get("customer", {})
        msg      = d.get("message", {})

        raw_phone    = (customer.get("channel_phone_number")
                        or customer.get("phone_number") or "")
        phone        = clean_phone(raw_phone)
        text         = (msg.get("message") or "").strip()
        content_type = msg.get("message_content_type", "")
        print("RAW MESSAGE FIELD:")
        print(msg.get("message"))

        traits       = customer.get("traits", {})
        profile_name = traits.get("name") or traits.get("first_name")

        print(f"  content_type = {content_type!r}")
        print(f"  text from msg = {text!r}")

        if content_type in ("InteractiveButtonReply", "InteractiveListReply"):
            try:
                parsed_msg = json.loads(text)

                if parsed_msg.get("type") == "button_reply":
                    button_data = parsed_msg.get("button_reply", {}).get("id")

                elif parsed_msg.get("type") == "list_reply":
                    button_data = parsed_msg.get("list_reply", {}).get("id")

            except Exception as e:
                print(f"[interactive parse error] {e}")
                button_data = text

            print(f"  button_data extracted = {button_data!r}")

        elif content_type in (
            "Order",
            "OrderDetails",
            "InteractiveNFMReply",
            "InteractiveProduct",
            "InteractiveProductListReply"
        ):
            try:
                parsed_msg = json.loads(text)
                print("PARSED CATALOGUE MESSAGE:")
                print(json.dumps(parsed_msg, indent=2))

                items = parsed_msg.get("product_items", [])

                if items:
                    catalogue_slug = items[0].get(
                        "product_retailer_id", ""
                    ).strip()

                elif parsed_msg.get("product"):
                    catalogue_slug = (
                        parsed_msg.get("product", {})
                        .get("product_retailer_id", "")
                        .strip()
                    )

                elif parsed_msg.get("product_retailer_id"):
                    catalogue_slug = (
                        parsed_msg.get("product_retailer_id", "")
                        .strip()
                    )

                print(f"CATALOGUE SLUG DETECTED → {catalogue_slug}")

            except Exception as e:
                print(f"[catalogue parse error] {e}")

    elif "userPhoneNumber" in raw_data:
        # Legacy Interakt payload format
        phone  = clean_phone(raw_data.get("userPhoneNumber", ""))
        entity = raw_data.get("entity", {})
        text   = entity.get("text", "").strip()

        suggestion = entity.get("suggestionResponse", {})
        if suggestion:
            button_data = (suggestion.get("postBack", {}).get("data")
                           or suggestion.get("postBack", {}).get("id"))

        contacts     = raw_data.get("contacts", [])
        profile_name = contacts[0].get("profile", {}).get("name") if contacts else None

    print(f"EXTRACTED → Phone:{phone} | Text:'{text}' | "
          f"Button:'{button_data}' | Catalogue:'{catalogue_slug}' | Name:'{profile_name}'")

    if not phone:
        print("❌ No phone found → ignoring")
        return jsonify({"status": "ignored"}), 200

    # ── DB SETUP ──────────────────────────────────────────────────────────────
    db_conn = get_db()
    cursor  = db_conn.cursor()

    user = db_upsert_user(cursor, phone)
    db_conn.commit()
    step = user.get("step", "greeting")

    db_log_message(
        cursor, user["id"], phone, "inbound",
        "interactive" if (button_data or catalogue_slug) else "text",
        text or button_data or catalogue_slug or "", step, raw=raw_data
    )
    db_conn.commit()

    def done():
        db_conn.commit()
        db_conn.close()
        return jsonify({"status": "ok"}), 200

    # =========================================================================
    # STEP 1 — GLOBAL RESTART
    # Trigger: "hi", "hello", "hey", "start", "namaste", "restart"
    # =========================================================================
    if text.lower() in ("hi", "hello", "start", "hey", "namaste", "restart"):
        if not is_open():
            send_text(phone,
                "🌙 Salad O'Clock is closed for today.\n"
                "We're open *7 AM – 8 PM* daily. See you tomorrow! 🥗")
            return done()

        name = None
        if profile_name and is_valid_name(profile_name):
            name = profile_name.title()
        elif user.get("name") and is_valid_name(user.get("name")):
            name = user["name"]

        if name:
            db_update_user(cursor, phone,
                           name=name,
                           whatsapp_name=profile_name or user.get("whatsapp_name"),
                           step="goal_selection")
            db_conn.commit()
            send_goal_selection(phone, name)
        else:
            db_update_user(cursor, phone,
                           whatsapp_name=profile_name,
                           step="ask_name")
            db_conn.commit()
            send_text(phone, "👋 Welcome to *Salad O'Clock!* 🥗\n\nWhat's your good name?")

        return done()

    # =========================================================================
    # STEP 2 — ASK NAME
    # =========================================================================
    if step == "ask_name":
        if is_valid_name(text):
            name = text.strip().title()
            db_update_user(cursor, phone, name=name, step="goal_selection")
            db_conn.commit()
            send_goal_selection(phone, name)
        else:
            send_text(phone,
                "Please enter a valid name (letters only, at least 3 characters). 🙏")
        return done()

    # =========================================================================
    # STEP 3 — GOAL SELECTION
    #
    # THE KEY FIX:
    # Interakt sends button taps as content_type="text" with msg.message = "💪 Muscle Gain"
    # (the button title including emoji). button_data will be None in this case.
    # resolve_goal() strips emoji, lowercases, and matches against all known goal phrases.
    # =========================================================================
    goal_from_input = resolve_goal(button_data, text)

    if step == "goal_selection" or goal_from_input:
        if goal_from_input:
            db_update_user(cursor, phone, goal=goal_from_input, step="ask_pincode")
            db_conn.commit()
            send_text(phone,
                "📍 Please share your *6-digit pincode* so we can check "
                "delivery availability:")
        else:
            # No valid goal recognised — resend the buttons
            user = db_get_user(cursor, phone)
            send_goal_selection(phone, user.get("name", "there"))
        return done()

    # =========================================================================
    # STEP 4 — ASK PINCODE
    # =========================================================================
    if step == "ask_pincode":

        # "Try Another Pincode" — handle both proper button reply AND Interakts plain-text echo
        text_clean_pin = re.sub(r"[^\w\s]", "", text).strip().lower()
        if button_data == "change_pincode" or "try another" in text_clean_pin or "another pincode" in text_clean_pin:
            send_text(phone, "Please enter your 6-digit pincode 📍")
            return done()

        pincode = text.strip()
        if not re.match(r'^\d{6}$', pincode):
            send_text(phone, "Please enter a valid *6-digit* pincode. 🔢")
            return done()

        if db_is_pincode_serviceable(cursor, pincode):
            db_update_user(cursor, phone, pincode=pincode)
            db_conn.commit()

            user = db_get_user(cursor, phone)
            goal = user.get("goal")

            send_text(phone, f"✅ Great! We deliver to *{pincode}*.\n\nHere's our menu 👇")

            if goal == "Healthy Meals":
                db_update_user(cursor, phone, step="category_selection")
                db_conn.commit()
                show_category_selection(phone)

            elif goal in ("Fat Loss", "Muscle Gain"):
                db_update_user(cursor, phone,
                               selected_category="salad",
                               step="item_selection")
                db_conn.commit()
                show_menu(phone, cursor, "salad", goal=goal)

            else:
                # Fallback — show all salads
                db_update_user(cursor, phone,
                               selected_category="salad",
                               step="item_selection")
                db_conn.commit()
                show_menu(phone, cursor, "salad")

        else:
            send_text(phone,
                f"❌ Sorry, we don't deliver to *{pincode}* yet.\n\n"
                "We currently serve select areas in Pune. Check back soon! 🙏")
            send_button_message(phone,
                "Would you like to try a different pincode?",
                [{"id": "change_pincode", "title": "📍 Try Another Pincode"}])

        return done()

    # "Try Another Pincode" button arriving when step has moved past ask_pincode
    if button_data == "change_pincode":
        db_update_user(cursor, phone, step="ask_pincode")
        db_conn.commit()
        send_text(phone, "Please enter your 6-digit pincode 📍")
        return done()

    # =========================================================================
    # STEP 5 — CATEGORY SELECTION  (Healthy Meals path only)
    #
    # Same Interakt issue applies here — resolve_category() handles button id
    # AND the emoji-prefixed button title sent as plain text.
    # =========================================================================
    category_from_input = resolve_category(button_data, text)

    if step == "category_selection" or category_from_input:
        if category_from_input:
            db_update_user(cursor, phone,
                           selected_category=category_from_input,
                           step="item_selection")
            db_conn.commit()
            show_menu(phone, cursor, category_from_input)
        else:
            show_category_selection(phone)
        return done()

    # =========================================================================
    # STEP 6 — ITEM SELECTION
    # Sources:
    #   (a) WhatsApp catalogue tap  → catalogue_slug is set (e.g. "weight_loss_box")
    #   (b) Fallback list tap       → button_data starts with "salad_" / "superbowl_"
    # =========================================================================
    is_item_button = button_data and (
        button_data.startswith("salad_") or button_data.startswith("superbowl_")
    )

    if step == "item_selection" or catalogue_slug or is_item_button:
        product_slug = None
        category     = None

        if catalogue_slug:
            product_slug = catalogue_slug
            # Determine category from which product set this slug belongs to
            if catalogue_slug in PRODUCT_SET_SLUGS.get("superbowl_all", []):
                category = "superbowl"
            else:
                category = "salad"

        elif button_data and button_data.startswith("salad_"):
            product_slug = button_data[len("salad_"):]
            category     = "salad"

        elif button_data and button_data.startswith("superbowl_"):
            product_slug = button_data[len("superbowl_"):]
            category     = "superbowl"

        if not product_slug:
            send_text(phone, "Please pick an item from the menu. 👆")
            return done()

        product = db_get_product_by_slug(cursor, product_slug)
        if not product:
            send_text(phone, "⚠️ Item not found. Please pick from the menu.")
            return done()

        db_update_user(cursor, phone,
                       selected_category=category,
                       selected_item=product_slug,
                       step="plan_selection")
        db_conn.commit()
        send_plan_selection(phone, cursor, product["id"], product["name"])
        return done()

    # =========================================================================
    # STEP 7 — PLAN SELECTION
    # =========================================================================
    is_plan_button = button_data and button_data.startswith("plan_")

    if step == "plan_selection" or is_plan_button:
        plan_map = {
            "plan_single":  "single",
            "plan_weekly":  "weekly",
            "plan_monthly": "monthly"
        }
        plan = plan_map.get(button_data)
        if not plan:
            send_text(phone, "Please select a plan from the options above. 👆")
            return done()

        db_update_user(cursor, phone, selected_plan=plan, step="ask_address")
        db_conn.commit()
        send_text(phone,
            "📍 Please type your *full delivery address* including flat/house "
            "number, society, and landmark:")
        return done()

    # =========================================================================
    # STEP 8 — ASK ADDRESS
    # =========================================================================
    if step == "ask_address":
        address = text.strip()
        if len(address) < 10:
            send_text(phone,
                "Please enter a more complete address (at least 10 characters). 📍")
        else:
            db_update_user(cursor, phone,
                           delivery_address=address,
                           step="order_summary")
            db_conn.commit()
            user = db_get_user(cursor, phone)
            send_order_summary(phone, cursor, user)
        return done()

    # =========================================================================
    # STEP 9 — ORDER SUMMARY / CONFIRM
    # =========================================================================
    text_clean_confirm = re.sub(r"[^\w\s]", "", text).strip().lower()
    is_confirm_button = (button_data in ("confirm_order", "cancel_order")
                         or "confirm order" in text_clean_confirm
                         or "cancel" in text_clean_confirm)

    if step == "order_summary" or is_confirm_button:
        if button_data == "confirm_order" or "confirm order" in text_clean_confirm:
            user = db_get_user(cursor, phone)
            process_confirmed_order(phone, cursor, db_conn, user)

        elif button_data == "cancel_order" or ("cancel" in text_clean_confirm and "confirm" not in text_clean_confirm):
            db_update_user(cursor, phone, step="goal_selection")
            db_conn.commit()
            user = db_get_user(cursor, phone)
            send_text(phone, "❌ Order cancelled. Let's start fresh!")
            send_goal_selection(phone, user.get("name", "there"))

        else:
            # Step is order_summary but no button tapped — resend summary
            user = db_get_user(cursor, phone)
            send_order_summary(phone, cursor, user)

        return done()

    # =========================================================================
    # STEP 10 — DONE (order already placed, awaiting payment)
    # =========================================================================
    if step == "done":
        send_text(phone,
            "Your order is already placed! 🎉\nType *hi* to place a new order. 🥗")
        return done()

    # =========================================================================
    # FALLBACK
    # =========================================================================
    send_text(phone, "👋 Type *hi* to start ordering from Salad O'Clock! 🥗")
    return done()


# ====================== PAYMENT CALLBACK ======================

@app.route('/payment-callback', methods=['GET', 'POST'])
def payment_callback():
    razorpay_payment_id  = (request.args.get("razorpay_payment_id")
                             or request.form.get("razorpay_payment_id"))
    razorpay_link_status = (request.args.get("razorpay_payment_link_status")
                             or request.form.get("razorpay_payment_link_status"))
    order_id             = (request.args.get("order_id")
                             or request.form.get("order_id"))

    if razorpay_link_status == "paid" and razorpay_payment_id and order_id:
        db_conn = get_db()
        cursor  = db_conn.cursor()

        cursor.execute("""
            UPDATE orders
               SET payment_status      = 'paid',
                   razorpay_payment_id = %s
             WHERE order_id = %s
               AND payment_status != 'paid'
        """, (razorpay_payment_id, order_id))
        db_conn.commit()

        db_log_payment_event(cursor, order_id, "payment_link.paid",
                             razorpay_payment_id, None, None, "paid",
                             dict(request.args))
        db_conn.commit()

        db_call_generate_schedule(cursor, order_id)
        db_conn.commit()

        order = db_get_order(cursor, order_id)
        if order:
            notify_payment_confirmed(
                order["phone_number"], order_id,
                order["product_name"], order["plan"]
            )

        db_conn.close()
        return "Payment successful! You may close this window.", 200

    return "Payment not completed.", 200


# ====================== RAZORPAY SERVER WEBHOOK ======================

@app.route('/razorpay-webhook', methods=['POST'])
def razorpay_webhook():
    payload = request.json
    if not payload:
        return jsonify({"status": "ignored"}), 200

    event   = payload.get("event", "")
    db_conn = get_db()
    cursor  = db_conn.cursor()

    try:
        if event == "payment_link.paid":
            link_ent    = payload["payload"]["payment_link"]["entity"]
            pay_ent     = payload["payload"]["payment"]["entity"]
            order_id    = link_ent.get("notes", {}).get("order_id")
            rz_pay_id   = pay_ent.get("id")
            rz_order_id = pay_ent.get("order_id")
            amount      = pay_ent.get("amount")

            db_log_payment_event(cursor, order_id, event, rz_pay_id,
                                 rz_order_id, amount, "paid", payload)
            db_conn.commit()

            if order_id and rz_pay_id:
                cursor.execute("""
                    UPDATE orders
                       SET payment_status      = 'paid',
                           razorpay_payment_id = %s
                     WHERE order_id = %s
                       AND payment_status != 'paid'
                """, (rz_pay_id, order_id))
                db_conn.commit()

                db_call_generate_schedule(cursor, order_id)
                db_conn.commit()

                order = db_get_order(cursor, order_id)
                if order:
                    notify_payment_confirmed(
                        order["phone_number"], order_id,
                        order["product_name"], order["plan"]
                    )

        elif event == "payment.failed":
            pay_ent     = payload["payload"]["payment"]["entity"]
            rz_pay_id   = pay_ent.get("id")
            rz_order_id = pay_ent.get("order_id")
            amount      = pay_ent.get("amount")

            cursor.execute(
                "SELECT order_id, phone_number FROM orders WHERE razorpay_order_id=%s",
                (rz_order_id,)
            )
            row          = cursor.fetchone()
            our_order_id = row["order_id"] if row else None

            db_log_payment_event(cursor, our_order_id, event, rz_pay_id,
                                 rz_order_id, amount, "failed", payload)
            db_conn.commit()

            if row:
                cursor.execute(
                    "UPDATE orders SET payment_status='failed' "
                    "WHERE order_id=%s AND payment_status='pending'",
                    (our_order_id,)
                )
                db_conn.commit()
                send_text(
                    row["phone_number"],
                    f"❌ Payment failed for order *{our_order_id}*.\n\n"
                    "Please type *hi* to place your order again or contact us for help. 🙏"
                )

        else:
            db_log_payment_event(cursor, None, event, None, None, None, None, payload)
            db_conn.commit()

    except Exception as e:
        print(f"[razorpay_webhook error] {e}")

    db_conn.close()
    return jsonify({"status": "ok"}), 200


# ====================== HEALTH CHECK ======================

@app.route('/health', methods=['GET'])
def health():
    db_ok = False
    try:
        db_conn = get_db()
        cursor  = db_conn.cursor()
        cursor.execute("SELECT 1")
        db_conn.close()
        db_ok = True
    except Exception:
        pass
    return jsonify({
        "status":    "running",
        "service":   "Salad O'Clock Bot",
        "db":        "ok" if db_ok else "error",
        "open_now":  is_open(),
        "timestamp": datetime.now().isoformat()
    }), 200


# ====================== ENTRY ======================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)