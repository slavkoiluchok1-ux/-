from flask import Flask, render_template, request, redirect, url_for
from databases import Session, Product, Order

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/products')
def products():
    with Session() as session:
        all_products = session.query(Product).all()
    return render_template('products.html', products=all_products)

@app.route('/order/<int:product_id>', methods=['GET', 'POST'])
def order(product_id):
    with Session() as session:
        product = session.get(Product, product_id)
        
        if request.method == 'POST':
            phone = request.form.get('phone')
            email = request.form.get('email')
            
            if phone and email:
                new_order = Order(phone=phone, email=email, product_id=product_id)
                session.add(new_order)
                session.commit()
                return redirect(url_for('thanks'))
            
        return render_template('order.html', product=product)

@app.route('/my-orders')
def my_orders():
    phone = request.args.get('phone')
    orders = []
    if phone:
        with Session() as session:
            orders = session.query(Order).filter(Order.phone == phone).all()
    return render_template('my_orders.html', orders=orders, phone=phone)

@app.route('/thanks')
def thanks():
    return render_template('thanks.html')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=8000)