import os
import uuid
import secrets
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

# Імпорт моделей та сесії
from online_restaurant_db import Session, Users, Menu, Orders, Reservation

app = Flask(__name__)

# --- НАЛАШТУВАННЯ ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = '#cv)3v7w$*s3fk;5c!@y0?:?№3"9)#'
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'menu')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Ліміт на завантаження 16МБ

# --- FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    with Session() as db_session:
        return db_session.get(Users, int(user_id))

# --- ГЕНЕРАЦІЯ CSRF ТОКЕНА ---
@app.before_request
def ensure_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)

# --- ГОЛОВНА СТОРІНКА ---
@app.route('/')
@app.route('/home')
def home():
    with Session() as db:
        featured = db.query(Menu).filter(Menu.active == True, Menu.discount > 0).order_by(func.random()).limit(3).all()
        if not featured:
            featured = db.query(Menu).filter_by(active=True).limit(3).all()
    return render_template('home.html', featured=featured)

# --- МЕНЮ ТА СТРАВИ ---
@app.route('/menu')
def menu():
    with Session() as db:
        if current_user.is_authenticated and current_user.nickname == 'Admin':
            all_positions = db.query(Menu).all()
        else:
            all_positions = db.query(Menu).filter_by(active=True).all()
    return render_template('menu.html', all_positions=all_positions)

@app.route('/position/<name>', methods=['GET', 'POST'])
def position(name):
    with Session() as db:
        item = db.query(Menu).filter_by(name=name).first()
        if not item:
            return "Страва не знайдена", 404
            
        if request.method == 'POST':
            qty = int(request.form.get('num', 1))
            basket = session.get('basket', {})
            basket[name] = basket.get(name, 0) + qty
            if basket[name] > 10: basket[name] = 10
            session['basket'] = basket
            session.modified = True
            flash(f"Додано {name} ({qty} шт.) у кошик", "success")
            return redirect(url_for('menu'))
            
    return render_template('position.html', position=item)

# --- АДМІН-ПАНЕЛЬ (КЕРУВАННЯ МЕНЮ) ---
@app.route("/add_position", methods=['GET', 'POST'])
@login_required
def add_position():
    if current_user.nickname != 'Admin': return "No access", 403
    if request.method == "POST":
        file = request.files.get('img')
        f_name = f"{uuid.uuid4()}_{file.filename}" if file and file.filename != '' else "default.png"
        
        if file and file.filename != '': 
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], f_name))
            
        with Session() as db:
            db.add(Menu(
                name=request.form['name'], 
                weight=request.form['weight'],
                ingredients=request.form['ingredients'], 
                description=request.form['description'],
                price=int(request.form['price']), 
                discount=int(request.form.get('discount', 0)),
                file_name=f_name, 
                active=True
            ))
            db.commit()
        flash("Нову страву успішно додано!", "success")
        return redirect(url_for('menu'))
    return render_template('add_position.html')

@app.route('/admin/toggle_active/<int:item_id>')
@login_required
def toggle_active(item_id):
    if current_user.nickname != 'Admin': return "No access", 403
    with Session() as db:
        item = db.query(Menu).get(item_id)
        if item:
            item.active = not item.active
            db.commit()
    return redirect(url_for('menu'))

@app.route('/admin/delete_position/<int:item_id>')
@login_required
def delete_position(item_id):
    if current_user.nickname != 'Admin': return "No access", 403
    with Session() as db:
        item = db.query(Menu).get(item_id)
        if item:
            if item.file_name and item.file_name != "default.png":
                path = os.path.join(app.config['UPLOAD_FOLDER'], item.file_name)
                if os.path.exists(path):
                    os.remove(path)
            db.delete(item)
            db.commit()
            flash("Страву видалено назавжди", "info")
    return redirect(url_for('menu'))

# --- КОШИК ТА ЗАМОВЛЕННЯ ---
@app.route('/cart')
@login_required
def cart():
    basket = session.get('basket', {})
    items_in_cart = []
    total_sum = 0
    with Session() as db:
        for name, qty in basket.items():
            item = db.query(Menu).filter_by(name=name).first()
            if item:
                price = int(item.price * (100 - item.discount) / 100)
                subtotal = price * qty
                total_sum += subtotal
                items_in_cart.append({'obj': item, 'qty': qty, 'price': price, 'subtotal': subtotal})
    return render_template('cart.html', items=items_in_cart, total_sum=total_sum)

@app.route('/update_cart/<name>/<action>')
@login_required
def update_cart(name, action):
    basket = session.get('basket', {})
    if name in basket:
        if action == 'plus' and basket[name] < 10: basket[name] += 1
        elif action == 'minus':
            if basket[name] > 1: basket[name] -= 1
            else: basket.pop(name)
        elif action == 'delete': basket.pop(name)
    session['basket'] = basket
    session.modified = True
    return redirect(url_for('cart'))

@app.route('/confirm_order', methods=['POST'])
@login_required
def confirm_order():
    basket = session.get('basket', {})
    if not basket: return redirect(url_for('menu'))
    with Session() as db:
        db.add(Orders(order_list=basket, order_time=datetime.now(), user_id=current_user.id))
        db.commit()
    session.pop('basket', None)
    flash("Замовлення прийнято!", "success")
    return redirect(url_for('my_orders'))

# --- БРОНЮВАННЯ СТОЛІВ ---
@app.route('/reserve', methods=['GET', 'POST'])
@login_required
def reserve():
    if request.method == 'POST':
        time_str = request.form.get('time')
        if not time_str:
            flash("Оберіть дату та час!", "danger")
            return redirect(url_for('reserve'))
        try:
            time_obj = datetime.strptime(time_str, '%Y-%m-%dT%H:%M')
            with Session() as db:
                db.add(Reservation(
                    time_start=time_obj, 
                    type_table=request.form.get('table_type'), 
                    user_id=current_user.id
                ))
                db.commit()
            flash("Стіл заброньовано!", "success")
            return redirect(url_for('my_orders'))
        except ValueError:
            flash("Помилка формату часу", "danger")
    return render_template('reservation.html')

@app.route('/cancel_reservation/<int:res_id>')
@login_required
def cancel_reservation(res_id):
    with Session() as db:
        res = db.query(Reservation).filter_by(id=res_id, user_id=current_user.id).first()
        if res:
            db.delete(res)
            db.commit()
            flash("Ваше бронювання успішно скасовано.", "info")
        else:
            flash("Помилка: Бронювання не знайдено.", "danger")
    return redirect(url_for('my_orders'))

# --- ОСОБИСТИЙ КАБІНЕТ ТА АДМІН-СПИСКИ ---
@app.route('/my_orders')
@login_required
def my_orders():
    with Session() as db:
        orders = db.query(Orders).filter_by(user_id=current_user.id).order_by(Orders.order_time.desc()).all()
        reservations = db.query(Reservation).filter_by(user_id=current_user.id).order_by(Reservation.time_start.asc()).all()
    return render_template('my_orders.html', orders=orders, reservations=reservations)

@app.route('/admin/orders')
@login_required
def admin_orders():
    if current_user.nickname != 'Admin': return "Access Denied", 403
    with Session() as db:
        orders = db.query(Orders).options(joinedload(Orders.user)).order_by(Orders.order_time.desc()).all()
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/delete_order/<int:order_id>')
@login_required
def admin_delete_order(order_id):
    if current_user.nickname != 'Admin': return "Access Denied", 403
    with Session() as db:
        order = db.query(Orders).get(order_id)
        if order:
            db.delete(order)
            db.commit()
            flash(f"Замовлення #{order_id} успішно видалено!", "success")
    return redirect(url_for('admin_orders'))

@app.route('/admin/reservations')
@login_required
def admin_reservations():
    if current_user.nickname != 'Admin': return "Access Denied", 403
    with Session() as db:
        res = db.query(Reservation).options(joinedload(Reservation.user)).order_by(Reservation.time_start.asc()).all()
    return render_template('admin_reservations.html', reservations=res)

@app.route('/admin/delete_reservation/<int:res_id>')
@login_required
def admin_delete_reservation(res_id):
    if current_user.nickname != 'Admin': return "Access Denied", 403
    with Session() as db:
        res = db.query(Reservation).get(res_id)
        if res:
            db.delete(res)
            db.commit()
            flash(f"Бронювання #{res_id} видалено.", "success")
    return redirect(url_for('admin_reservations'))

# --- АВТОРИЗАЦІЯ ---
@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nick, mail, pw = request.form['nickname'], request.form['email'], request.form['password']
        with Session() as db:
            if db.query(Users).filter((Users.email == mail) | (Users.nickname == nick)).first():
                flash('Такий користувач вже є!', 'danger')
            else:
                user = Users(nickname=nick, email=mail)
                user.set_password(pw)
                db.add(user)
                db.commit()
                login_user(user)
                return redirect(url_for('home'))
    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nick, pw = request.form['nickname'], request.form['password']
        with Session() as db:
            user = db.query(Users).filter_by(nickname=nick).first()
            if user and user.check_password(pw):
                login_user(user)
                return redirect(url_for('home'))
            flash('Невірний логін або пароль', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)