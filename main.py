import os
from datetime import datetime
import requests
import smtplib
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_bootstrap import Bootstrap
from flask_gravatar import Gravatar
from forms import CreatePostForm, LoginForm, RegisterForm, CommentForm, ContactForm
from flask_login import login_user, LoginManager, login_required, current_user, logout_user
from flask_ckeditor import CKEditor
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, BlogPost, Comment
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("APP_KEY")
ckeditor = CKEditor(app)
Bootstrap(app)
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_user():
    return dict(user=current_user)


@app.context_processor
def inject_year():
    return dict(year=datetime.now().year)


# posts_response = requests.get("https://api.npoint.io/ed99320662742443cc5b")
# posts_response.raise_for_status()
# posts = [Post(r["id"], r["title"], r["subtitle"], r["body"]) for r in posts_response.json()]


def admin_only(f):
    @wraps(f)
    def decorated_function(id, *args, **kwargs):
        try:
            user_id = current_user.id
            user_posts = [post.id for post in current_user.posts]
            if user_id == 1 or id in user_posts:
                return f(id, *args, **kwargs)
        except AttributeError:
            pass
        return abort(403)
    return decorated_function


@app.route('/')
def home():
    print(current_user.is_authenticated)
    posts = BlogPost.query.all()
    return render_template("index.html", posts=posts)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(email=request.form["email"]).first()
        if existing_user:
            flash("There already exists a user with this email address")
            return redirect(url_for("login"))
        new_user = User(
            email=request.form["email"],
            password=generate_password_hash(request.form["password"]),
            name=request.form["name"]
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('home'))
    return render_template("register.html", form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        password = request.form.get('password')
        user = User.query.filter_by(email=request.form["email"]).first()
        if not user:
            flash("No user found with this email address")
            return redirect(url_for("login"))
        if check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Invalid password")
    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/contact', methods=["GET", "POST"])
def contact():
    form = ContactForm()
    data_sent = False
    if form.validate_on_submit():
        with smtplib.SMTP(host=os.environ.get("SMTP_HOST"), port=587) as conn:
            conn.starttls()
            conn.login(user=os.environ.get("SMTP_MAIL"), password=os.environ.get("SMTP_KEY"))
            conn.sendmail(
                from_addr=os.environ.get("SMTP_MAIL"),
                to_addrs=os.environ.get("RECIP_MAIL"),
                msg=f"Subject:New Message\n\n"
                    f"Name: {form.name.data}\n"
                    f"Email: {form.email.data}\n"
                    f"Message: {form.message.data}".encode("utf-8")
            )
        data_sent = True
        form.name.data = ""
        form.email.data = ""
        form.message.data = ""
    return render_template("contact.html", data_sent=data_sent, form=form)


@app.route('/about')
def about():
    return render_template("about.html")


@app.route("/post/<int:id>", methods=["GET", "POST"])
def post(id):
    try:
        blog_post = BlogPost.query.get(id)
        form = CommentForm()
        if form.validate_on_submit():
            if current_user.is_authenticated:
                new_comment = Comment(
                    text=form.comment.data,
                    user_id=current_user.id,
                    blog_post_id=id
                )
                db.session.add(new_comment)
                db.session.commit()
                form.text.data = ""
            else:
                flash("Please log in to leave a comment")
                return redirect(url_for('login'))
        return render_template("post.html", post=blog_post, form=form)
    except IndexError:
        return redirect(url_for("home"))


@app.route("/edit-post/<int:id>", methods=["GET", "POST"])
@admin_only
def edit_post(id):
    post_to_update = BlogPost.query.get(id)
    form = CreatePostForm(
        title=post_to_update.title,
        subtitle=post_to_update.subtitle,
        img_url=post_to_update.img_url,
        body=post_to_update.body
    )
    if form.validate_on_submit():
        post_to_update.title = form.title.data
        post_to_update.subtitle = form.subtitle.data
        post_to_update.img_url = form.img_url.data
        post_to_update.body = form.body.data
        db.session.commit()
        return redirect(url_for("post", id=id))
    return render_template("make-post.html", form=form, is_create=False)


@app.route("/new-post", methods=["GET", "POST"])
@login_required
def add_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            date=datetime.now().strftime("%B %d, %Y"),
            img_url=form.img_url.data,
            author_id=current_user.id
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("post", id=new_post.id))
    return render_template("make-post.html", form=form, is_create=True)


@app.route("/delete-post/<int:id>")
@admin_only
def delete(id):
    post_to_delete = BlogPost.query.get(id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(port=5000, debug=True)
