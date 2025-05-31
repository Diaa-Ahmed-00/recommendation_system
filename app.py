from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import pyodbc
from dotenv import load_dotenv
from decimal import Decimal
from datetime import date, datetime
import logging
import random

# Load environment variables
load_dotenv()

# Setup Flask
app = Flask(__name__)
CORS(app)

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Database config
server = os.getenv('SQL_SERVER')
database = os.getenv('SQL_DATABASE')
username = os.getenv('SQL_USER')
password = os.getenv('SQL_PASSWORD')

def get_db_connection():
    try:
        conn = pyodbc.connect(
            f'DRIVER={{ODBC Driver 17 for SQL Server}};'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID={username};'
            f'PWD={password}'
        )
        logging.info("Database connection established successfully.")
        return conn
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return None

def row_to_dict(cursor, row):
    row_dict = {}
    for i, column in enumerate(cursor.description):
        value = row[i]
        if isinstance(value, Decimal):
            value = float(value)
        elif isinstance(value, bytes):
            value = value.decode(errors="ignore")
        elif isinstance(value, (date, datetime)):
            value = value.isoformat()
        row_dict[column[0]] = value
    return row_dict

def get_all_items():
    conn = get_db_connection()
    if conn is None:
        raise Exception("Failed to connect to database.")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM dbo.Item;")
        rows = cursor.fetchall()
        items = [row_to_dict(cursor, row) for row in rows]
        return items
    finally:
        cursor.close()
        conn.close()

def get_user_purchases(user_id):
    conn = get_db_connection()
    if conn is None:
        return []
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT i.*
            FROM Order_Items oi
            INNER JOIN Order_inf oin ON oi.Order_ID = oin.IDFromPaymob
            INNER JOIN Item i ON oi.Item_ID = i.Item_ID
            WHERE oin.Buyer_ID = ?
        """, (user_id,))
        purchases = [row_to_dict(cursor, row) for row in cursor.fetchall()]
        return purchases
    finally:
        cursor.close()
        conn.close()


@app.route("/purchased", methods=["GET"])
def get_purchased_products():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        purchased_items = get_user_purchases(user_id)
        return jsonify({
            "message": "success",
            "products": purchased_items
        })
    except Exception as e:
        logging.error(f"Error in /purchased endpoint: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/recommend", methods=["GET"])
def recommend():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        all_items = get_all_items()
        purchased_items = get_user_purchases(user_id)

        if not purchased_items:
            selected_items = random.sample(all_items, min(20, len(all_items)))
        else:
            purchased_ids = {item["Item_ID"] for item in purchased_items}
            purchased_categories = {item["Category_ID"] for item in purchased_items if item.get("Category_ID") is not None}
            purchased_brands = {item["Brand_ID"] for item in purchased_items if item.get("Brand_ID") is not None}
            purchased_descriptions = [item["Description"] for item in purchased_items if item.get("Description")]

            def is_similar(item):
                if item["Item_ID"] in purchased_ids:
                    return False
                if item.get("Category_ID") in purchased_categories:
                    return True
                if item.get("Brand_ID") in purchased_brands:
                    return True
                if any(desc.lower() in item.get("Description", "").lower() for desc in purchased_descriptions):
                    return True
                return False

            similar_items = [item for item in all_items if is_similar(item)]
            selected_items = similar_items[:20] if similar_items else random.sample(all_items, min(20, len(all_items)))

        # تحويل البيانات لشكل مركب (يشبه المتوقع في الواجهة)
        def wrap_product(item):
            return {
                "Data": item,
                "images": {},
                "Brand": {
                    "Brand_ID": item.get("Brand_ID"),
                    "Brand_Name": item.get("Brand_Name", ""),
                    "Brand_Image": item.get("Brand_Image", "")
                },
                "Detilas": item.get("Detilas", {})
            }

        wrapped_products = [wrap_product(item) for item in selected_items]

        formatted_response = {
            "message": "success",
            "products": wrapped_products
        }
        return jsonify(formatted_response)

    except Exception as e:
        logging.error(f"Error in recommend endpoint: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)