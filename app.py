from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
from flask import make_response
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
from flask import make_response

app = Flask(__name__)
app.secret_key = "queen_shop_secret_key"


# ==========================
# DATABASE CONFIG
# ==========================
import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        print("DATABASE ERROR:", e)
        return None

# ==========================
# INIT DATABASE
# ==========================
def init_db():

    conn = get_db_connection()
    if not conn:
        print("Skipping DB setup (DB not ready)")
        return

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE,
            password VARCHAR(100),
            role VARCHAR(50)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shops (
            id SERIAL PRIMARY KEY,
            shop_name VARCHAR(150),
            shop_type VARCHAR(100)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150),
            price NUMERIC(10,2),
            stock INT,
            shop_id INT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            id SERIAL PRIMARY KEY,
            shop_id INT REFERENCES shops(id) ON DELETE CASCADE,
            stock_name VARCHAR(150),
            quantity INT,
            selling_price NUMERIC(10,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id SERIAL PRIMARY KEY,
            shop_id INT,
            stock_id INT,
            quantity INT,
            total NUMERIC(10,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
    SELECT COALESCE(SUM(quantity), 0)
    FROM sales
    WHERE DATE(created_at) = CURRENT_DATE
""")
    today_items_sold = cur.fetchone()[0]

    conn.commit()

    # default admin
    cur.execute("SELECT username FROM users WHERE username=%s", ("queen",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (username, password, role)
            VALUES (%s, %s, %s)
        """, ("queen", "1234", "Admin"))
        conn.commit()

    cur.close()
    conn.close()

# Create tables on startup
try:
    init_db()
    print("Database initialized successfully")
except Exception as e:
    print("Database initialization failed:", e)


def get_db_connection():
    try:
        return psycopg2.connect(
            DATABASE_URL,
            sslmode="require"
        )
    except Exception as e:
        print("DATABASE ERROR:", e)
        return None


# ==========================
# LOGIN
# ==========================
@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        if username == "queen" and password == "1234":
            session["user"] = "queen"
            session["role"] = "Admin"
            return redirect(url_for("dashboard"))

        conn = get_db_connection()

        if conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT username, role
                FROM users
                WHERE username=%s AND password=%s
            """, (username, password))

            user = cur.fetchone()

            cur.close()
            conn.close()

            if user:
                session["user"] = user[0]
                session["role"] = user[1]
                return redirect(url_for("dashboard"))

        return render_template("login.html", error="Invalid login")

    return render_template("login.html")


# ==========================
# DASHBOARD
# ==========================
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect(url_for("login"))

    shop_count = 0
    product_count = 0
    today_sales = 0
    today_items_sold = 0   
    user_count = 0   
    low_stock = 0   # 

    conn = get_db_connection()

    if conn:
        cur = conn.cursor()

        # TOTAL SHOPS
        cur.execute("SELECT COUNT(*) FROM shops")
        shop_count = cur.fetchone()[0]

        # TOTAL PRODUCTS
        cur.execute("SELECT COUNT(*) FROM products")
        product_count = cur.fetchone()[0]

        # TODAY SALES VALUE
        cur.execute("""
            SELECT COALESCE(SUM(total), 0)
            FROM sales
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_sales = cur.fetchone()[0]

        # TODAY ITEMS SOLD
        cur.execute("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM sales
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        today_items_sold = cur.fetchone()[0]

        # USERS COUNT
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]

        # LOW STOCK 
        cur.execute("""
            SELECT COUNT(*)
            FROM stocks
            WHERE quantity < 10
        """)
        low_stock = cur.fetchone()[0]

        cur.close()
        conn.close()

    return render_template(
        "dashboard.html",
        username=session["user"],
        role=session["role"],
        shop_count=shop_count,
        product_count=product_count,
        today_sales=today_sales,
        today_items_sold=today_items_sold,
        user_count=user_count,
        low_stock=low_stock   # 
    )

# ==========================
# LOGOUT
# ==========================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================
# SHOPS PAGE
# ==========================
@app.route("/shops")
def shops():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    data = []

    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, shop_name, shop_type FROM shops ORDER BY id DESC")
        data = cur.fetchall()
        cur.close()
        conn.close()

    return render_template("shops.html", shops=data)


# ==========================
# VIEW SHOP + STOCK SYSTEM
# ==========================
@app.route("/view-shop/<int:shop_id>", methods=["GET", "POST"])
def view_shop(shop_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if not conn:
        return "Database not connected"

    cur = conn.cursor()

    # ==========================
    # ADD STOCK
    # ==========================
    if request.method == "POST":

        stock_name = request.form["stock_name"]
        quantity = int(request.form["quantity"])
        selling_price = request.form["selling_price"]

        # CHECK IF STOCK ALREADY EXISTS
        cur.execute("""
            SELECT id, quantity
            FROM stocks
            WHERE shop_id=%s
            AND LOWER(stock_name)=LOWER(%s)
        """, (shop_id, stock_name))

        existing_stock = cur.fetchone()

        if existing_stock:

            new_quantity = existing_stock[1] + quantity

            cur.execute("""
                UPDATE stocks
                SET quantity=%s
                WHERE id=%s
            """, (
                new_quantity,
                existing_stock[0]
            ))

        else:

            cur.execute("""
                INSERT INTO stocks
                (shop_id, stock_name, quantity, selling_price)
                VALUES (%s, %s, %s, %s)
            """, (
                shop_id,
                stock_name,
                quantity,
                selling_price
            ))

        conn.commit()

        return redirect(url_for("view_shop", shop_id=shop_id))

    # ==========================
    # SHOP INFO
    # ==========================
    cur.execute("""
        SELECT id, shop_name, shop_type
        FROM shops
        WHERE id=%s
    """, (shop_id,))

    shop = cur.fetchone()

    # ==========================
    # SEARCH STOCK
    # ==========================
    search = request.args.get("search", "").strip()

    if search:

        cur.execute("""
            SELECT id, stock_name, quantity, selling_price
            FROM stocks
            WHERE shop_id=%s
            AND LOWER(stock_name) LIKE LOWER(%s)
            ORDER BY stock_name
        """, (
            shop_id,
            f"%{search}%"
        ))

    else:

        cur.execute("""
            SELECT id, stock_name, quantity, selling_price
            FROM stocks
            WHERE shop_id=%s
            ORDER BY id DESC
        """, (shop_id,))

    stocks = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "view_shop.html",
        shop=shop,
        stocks=stocks,
        search=search
    )


# ==========================
# CREATE SHOP
# ==========================
@app.route("/create-shop", methods=["POST"])
def create_shop():

    if "user" not in session:
        return redirect(url_for("login"))

    shop_name = request.form.get("shop_name")
    shop_type = request.form.get("shop_type")

    conn = get_db_connection()

    if conn:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO shops (shop_name, shop_type)
            VALUES (%s, %s)
        """, (shop_name, shop_type))

        conn.commit()
        cur.close()
        conn.close()

    return redirect(url_for("shops"))


# ==========================
# EDIT SHOP
# ==========================
@app.route("/edit-shop/<int:shop_id>", methods=["GET", "POST"])
def edit_shop(shop_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":

        cur = conn.cursor()

        cur.execute("""
            UPDATE shops
            SET shop_name=%s, shop_type=%s
            WHERE id=%s
        """, (
            request.form["shop_name"],
            request.form["shop_type"],
            shop_id
        ))

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("shops"))

    cur = conn.cursor()

    cur.execute("""
        SELECT id, shop_name, shop_type
        FROM shops
        WHERE id=%s
    """, (shop_id,))

    shop = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("edit_shop.html", shop=shop)



# ==========================
# REPORTS
# ==========================

@app.route("/reports", methods=["GET", "POST"])
def reports():

    if "user" not in session:
        return redirect(url_for("login"))

    report_data = []
    total_sales = 0

    if request.method == "POST":

        start_date = request.form["start_date"]
        end_date = request.form["end_date"]

        conn = get_db_connection()

        if conn:
            cur = conn.cursor()

            # ==========================
            # SALES DETAILS (FIXED)
            # NOW INCLUDES STOCK NAME
            # ==========================
            cur.execute("""
                SELECT 
                    s.id,
                    sh.shop_name,
                    st.stock_name,
                    s.quantity,
                    s.total,
                    s.created_at
                FROM sales s
                JOIN shops sh ON s.shop_id = sh.id
                JOIN stocks st ON s.stock_id = st.id
                WHERE DATE(s.created_at) BETWEEN %s AND %s
                ORDER BY s.created_at DESC
            """, (start_date, end_date))

            report_data = cur.fetchall()

            # ==========================
            # TOTAL SALES (UNCHANGED)
            # ==========================
            cur.execute("""
                SELECT COALESCE(SUM(total), 0)
                FROM sales
                WHERE DATE(created_at) BETWEEN %s AND %s
            """, (start_date, end_date))

            total_sales = cur.fetchone()[0]

            cur.close()
            conn.close()

    return render_template(
        "reports.html",
        report_data=report_data,
        total_sales=total_sales
    )


# ==========================
# PDF REPORT DOWNLOAD
# ==========================

@app.route("/download-report", methods=["POST"])
def download_report():

    if "user" not in session:
        return redirect(url_for("login"))

    start_date = request.form["start_date"]
    end_date = request.form["end_date"]

    conn = get_db_connection()
    data = []

    if conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                sh.shop_name,
                st.stock_name,
                s.quantity,
                s.total,
                s.created_at
            FROM sales s
            JOIN shops sh ON s.shop_id = sh.id
            JOIN stocks st ON s.stock_id = st.id
            WHERE DATE(s.created_at) BETWEEN %s AND %s
            ORDER BY s.created_at DESC
        """, (start_date, end_date))

        data = cur.fetchall()

        cur.close()
        conn.close()

    # ==========================
    # CREATE PDF (PRO TABLE STYLE)
    # ==========================
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)

    elements = []

    styles = getSampleStyleSheet()
    title = Paragraph("SALES REPORT", styles["Title"])
    elements.append(title)

    subtitle = Paragraph(f"Period: {start_date} to {end_date}", styles["Normal"])
    elements.append(subtitle)

    elements.append(Spacer(1, 12))

    # TABLE HEADER
    table_data = [
        ["Shop", "Item", "Qty", "Total (K)", "Date"]
    ]

    # TABLE ROWS
    for row in data:
        table_data.append([
            row[0],
            row[1],
            str(row[2]),
            str(row[3]),
            str(row[4])
        ])

    table = Table(table_data, repeatRows=1)

    # STYLE
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 1), (3, -1), "CENTER"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ])

    table.setStyle(style)

    elements.append(table)

    doc.build(elements)

    buffer.seek(0)

    return make_response(
        buffer.read(),
        200,
        {
            "Content-Type": "application/pdf",
            "Content-Disposition": "attachment; filename=sales_report.pdf"
        }
    )



# ==========================
# USERS PAGE
# ==========================
@app.route("/users", methods=["GET", "POST"])
def users():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    error = None

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        role = request.form.get("role", "User")

        if conn:
            cur = conn.cursor()

            # CHECK IF USER EXISTS
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            existing = cur.fetchone()

            if existing:
                error = "Username already exists"
            else:
                cur.execute("""
                    INSERT INTO users (username, password, role)
                    VALUES (%s, %s, %s)
                """, (username, password, role))

                conn.commit()

            cur.close()

    # ALWAYS LOAD USERS AFTER POST OR GET
    users_list = []

    if conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT id, username, role
            FROM users
            ORDER BY id DESC
        """)

        users_list = cur.fetchall()

        cur.close()
        conn.close()

    return render_template("users.html", users=users_list, error=error)


# ==========================
# EDIT USER
# ==========================
@app.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        cur = conn.cursor()

        cur.execute("""
            UPDATE users
            SET username=%s, password=%s, role=%s
            WHERE id=%s
        """, (username, password, role, user_id))

        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for("users"))

    cur = conn.cursor()

    cur.execute("""
        SELECT id, username, password, role
        FROM users
        WHERE id=%s
    """, (user_id,))

    user = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("edit_user.html", user=user)

# ==========================
# DELETE USER
# ==========================
@app.route("/delete-user/<int:user_id>")
def delete_user(user_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    # PREVENT DELETING ADMINS
    cur.execute("SELECT role FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()

    if user and user[0] == "Admin":
        cur.close()
        conn.close()
        return "Admin cannot be deleted"

    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()

    cur.close()
    conn.close()

    return redirect(url_for("users"))



# ==========================
# VIEW STOCK
# ==========================
@app.route("/view-stock")
def view_stock():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    shops = []

    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, shop_name, shop_type FROM shops ORDER BY id DESC")
        shops = cur.fetchall()
        cur.close()
        conn.close()

    return render_template("view_stock.html", shops=shops)



# ==========================
# VIEW STOCK FOR EACH SHOP
# ==========================
@app.route("/shop-stock/<int:shop_id>")
def shop_stock(shop_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if not conn:
        return "Database not connected"

    cur = conn.cursor()

    # shop info
    cur.execute("""
        SELECT id, shop_name, shop_type
        FROM shops
        WHERE id=%s
    """, (shop_id,))
    shop = cur.fetchone()

    # stocks
    cur.execute("""
        SELECT id, stock_name, quantity, selling_price
        FROM stocks
        WHERE shop_id=%s
        ORDER BY id DESC
    """, (shop_id,))
    stocks = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("shop_stock.html", shop=shop, stocks=stocks)


# ==========================
# DELETE STOCK
# ==========================
@app.route("/delete-stock/<int:stock_id>")
def delete_stock(stock_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if conn:
        cur = conn.cursor()

        cur.execute(
            "DELETE FROM stocks WHERE id=%s",
            (stock_id,)
        )

        conn.commit()

        cur.close()
        conn.close()

    return redirect(request.referrer)


# ==========================
# RECORD SALE
# ==========================
@app.route("/record-sale")
def record_sale():

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    shops = []

    if conn:
        cur = conn.cursor()
        cur.execute("SELECT id, shop_name, shop_type FROM shops ORDER BY id DESC")
        shops = cur.fetchall()
        cur.close()
        conn.close()

    return render_template("record_sale.html", shops=shops)



# ==========================
# SALE AND STOCK INPUT
# ==========================

@app.route("/shop-sale/<int:shop_id>", methods=["GET", "POST"])
def shop_sale(shop_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if not conn:
        return "DB not connected"

    cur = conn.cursor()

    # GET STOCKS
    cur.execute("""
        SELECT id, stock_name, quantity, selling_price
        FROM stocks
        WHERE shop_id=%s
        ORDER BY id DESC
    """, (shop_id,))
    stocks = cur.fetchall()

    # PROCESS SALE
    if request.method == "POST":

        stock_id = request.form["stock_id"]
        qty_sold = int(request.form["quantity"])

        # get stock info
        cur.execute("""
            SELECT quantity, selling_price
            FROM stocks
            WHERE id=%s
        """, (stock_id,))
        stock = cur.fetchone()

        if stock:

            current_qty = stock[0]
            price = float(stock[1])

            if qty_sold <= current_qty:

                new_qty = current_qty - qty_sold
                total = qty_sold * price

                # update stock
                cur.execute("""
                    UPDATE stocks
                    SET quantity=%s
                    WHERE id=%s
                """, (new_qty, stock_id))

                # insert sale
                cur.execute("""
                    INSERT INTO sales (shop_id, stock_id, quantity, total)
                    VALUES (%s, %s, %s, %s)
                """, (shop_id, stock_id, qty_sold, total))

                conn.commit()

        return redirect(url_for("shop_sale", shop_id=shop_id))

    # shop info
    cur.execute("SELECT id, shop_name FROM shops WHERE id=%s", (shop_id,))
    shop = cur.fetchone()

    cur.close()
    conn.close()

    return render_template("shop_sale.html", shop=shop, stocks=stocks)


# ==========================
# HELPER FUNCTION TO GET TODAY'S SALES
# ==========================
from datetime import datetime, date

def get_today_sales():
    conn = get_db_connection()
    total = 0

    if conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT COALESCE(SUM(total), 0)
            FROM sales
            WHERE DATE(created_at) = CURRENT_DATE
        """)

        total = cur.fetchone()[0]

        cur.close()
        conn.close()

    return total


# ==========================
# DELETE SHOP
# ==========================
@app.route("/delete-shop/<int:shop_id>")
def delete_shop(shop_id):

    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    cur = conn.cursor()

    cur.execute("DELETE FROM shops WHERE id=%s", (shop_id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for("shops"))


# ==========================
# START APP
# ==========================
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)