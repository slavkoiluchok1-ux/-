import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect

from messenger_project_db import Session, Users, Friends, Messages, Base, engine

app = Flask(__name__)

app.config['SECRET_KEY'] = 'dev-key-12345-change-me' 
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

csrf = CSRFProtect(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  

Base.metadata.create_all(engine)

@login_manager.user_loader
def load_user(user_id):
    with Session() as session:
        return session.get(Users, int(user_id))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        nickname = request.form.get('nickname')
        email = request.form.get('email')
        password = request.form.get('password')

        with Session() as session:
            user_exists = session.query(Users).filter(
                (Users.email == email) | (Users.nickname == nickname)
            ).first()
            
            if user_exists:
                flash('Нікнейм або Email вже використовуються!', 'danger')
                return render_template('registr.html')

            new_user = Users(nickname=nickname, email=email)
            new_user.set_password(password)
            session.add(new_user)
            session.commit()
            
            login_user(new_user)
            flash('Реєстрація успішна!', 'success')
            return redirect(url_for('home'))
            
    return render_template('registr.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        nickname = request.form.get('nickname')
        password = request.form.get('password')

        with Session() as session:
            user = session.query(Users).filter_by(nickname=nickname).first()
            if user and user.check_password(password):
                login_user(user)
                flash(f'З поверненням, {nickname}!', 'success')
                return redirect(url_for('home'))
            
            flash('Невірний логін або пароль', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Ви вийшли із системи', 'info')
    return redirect(url_for('login'))


@app.route('/')
@app.route('/home')
@login_required
def home():
    return render_template('index.html', username=current_user.nickname)

@app.route("/search_friends", methods=["GET", "POST"])
@login_required
def search_friends():
    if request.method == 'POST':
        target_name = request.form.get('name')
        
        if target_name == current_user.nickname:
            flash("Ви не можете додати себе в друзі", "warning")
            return redirect(url_for('search_friends'))

        with Session() as session:
            target = session.query(Users).filter_by(nickname=target_name).first()
            if not target:
                flash("Користувача не знайдено", "danger")
            else:
                already_friends = session.query(Friends).filter(
                    ((Friends.sender == current_user.id) & (Friends.recipient == target.id)) |
                    ((Friends.sender == target.id) & (Friends.recipient == current_user.id))
                ).first()
                
                if already_friends:
                    flash("Ви вже друзі або запит вже надіслано", "info")
                else:
                    new_request = Friends(sender=current_user.id, recipient=target.id, status=False)
                    session.add(new_request)
                    session.commit()
                    flash("Запит на дружбу надіслано!", "success")
                    
    return render_template("search_friends.html")

@app.route('/friend_requests')
@login_required
def friend_requests():
    with Session() as session:
        requests = session.query(Friends).filter_by(recipient=current_user.id, status=False).all()
        data = {r.sender_user.id: r.sender_user.nickname for r in requests}
        return render_template('friend_requests.html', data=data)

@app.route('/friend_requests_confirm', methods=["POST"])
@login_required
def friend_requests_confirm():
    sender_id = request.form.get('id')
    answer = request.form.get('result')
    
    with Session() as session:
        friend_req = session.query(Friends).filter_by(
            sender=sender_id, recipient=current_user.id, status=False
        ).first()
        
        if friend_req:
            if answer == 'yes':
                friend_req.status = True
                flash("Дружбу підтверджено!", "success")
            else:
                session.delete(friend_req)
                flash("Запит відхилено", "info")
            session.commit()
            
    return redirect(url_for('friend_requests'))

@app.route("/my_friends")
@login_required
def my_friends():
    with Session() as session:
        sent = session.query(Friends).filter_by(sender=current_user.id, status=True).all()
        received = session.query(Friends).filter_by(recipient=current_user.id, status=True).all()
        
        friends_list = [f.recipient_user.nickname for f in sent] + \
                       [f.sender_user.nickname for f in received]
                       
        return render_template("my_friends.html", data=friends_list)

@app.route('/create_message/<string:user_name>', methods=["GET", "POST"])
@login_required
def create_message(user_name):
    if request.method == 'POST':
        msg_text = request.form.get("text")
        if not msg_text or not msg_text.strip():
            flash("Повідомлення не може бути порожнім", "warning")
            return redirect(url_for('create_message', user_name=user_name))

        with Session() as session:
            recipient = session.query(Users).filter_by(nickname=user_name).first()
            if recipient:
                new_msg = Messages(
                    sender=current_user.id, 
                    recipient=recipient.id, 
                    message_text=msg_text
                )
                session.add(new_msg)
                session.commit()
                flash(f"Повідомлення для {user_name} надіслано!", "success")
                return redirect(url_for('my_friends'))
                
    return render_template('create_message.html', target_name=user_name)

@app.route("/new_messages")
@login_required
def new_messages():
    with Session() as session:
        unread = session.query(Messages).filter_by(
            recipient=current_user.id, status_check=False
        ).all()
        
        data = {}
        for m in unread:
            sender_nick = m.sender_user.nickname
            if sender_nick not in data:
                data[sender_nick] = []
            data[sender_nick].append(m.message_text)
            
            m.status_check = True 
            
        session.commit()
        return render_template('new_messages.html', data=data)

if __name__ == '__main__':
    app.run(debug=True)