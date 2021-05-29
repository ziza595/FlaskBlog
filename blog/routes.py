from datetime import datetime
import os
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from blog import app, db, bcrypt, login_manager, mail
from blog.forms import RegistrationForm, LoginForm, UpdateAccountForm, PostForm, RequestResetForm, ResetPasswordForm
from blog.models import User, Post
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message


@app.context_processor
def inject_now():
    return {'now': datetime.now()}


@app.context_processor
def utility_processor():
    def pluralize(count, singular, plural=None):
        if not isinstance(count, int):
            raise ValueError('"{}" must be an integer'.format(count))
        
        if plural is None:
            plural = singular + 's'
        
        if count == 1:
            string = singular
        else:
            string = plural

        return f"{count} {string}"

    return dict(pluralize=pluralize)


@app.route('/')
def home():
    return render_template('pages/home.html')


@app.route('/contact')
def contact():
    return render_template('pages/contact.html', title='Contact')


@app.route('/about')
def about():
    return render_template('pages/about.html', title='A propos')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        flash('Votre compte a été crée avec succès ! Vous pouvez maintenant vous connectez', 'success')
        return redirect(url_for('login'))
    return render_template('pages/register.html', form=form, title='Inscription')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Connexion échouée ! Vérifier vos identifiants', 'danger')
    return render_template('pages/login.html', form=form, title='Connexion')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/img/profile_pics', picture_fn)
    form_picture.save(picture_path)

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        db.session.commit()
        flash('Votre compte a bien été mis à jour !', 'success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
    image_file = url_for('static', filename='img/profile_pics/' + current_user.image_file)
    return render_template('pages/account.html', image_file=image_file, form=form, title='Account')


@app.route('/blog')
def posts_index():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('posts/index.html', posts=posts, title='Blog')

@app.route('/blog/user/<string:username>')
def user_posts(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(author=user).order_by(Post.date_posted.desc()).paginate(page=page, per_page=5)
    return render_template('posts/user_posts.html', user=user, posts=posts, title='Blog')


@app.route('/blog/posts/<int:id>')
def posts_show(id):
    post = Post.query.get(id)
    return render_template('posts/show.html', post=post, title='Blog')


@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(title=form.title.data, content=form.content.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Votre post est créé avec succès !', 'success')
        return redirect(url_for('posts_index'))
    return render_template('posts/create_post.html', form=form, title='Blog - New post', legend='Nouveau post')


@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('posts/post.html', post=post, title=post.title)


@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash('Votre post a bien été mis à jour !', 'success')
        return redirect(url_for('post', post_id=post.id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.content.data = post.content
    return render_template('posts/create_post.html', post=post, form=form, title=post.title, legend='Mettre à jour le post')


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash('Votre post a été supprimé !', 'success')
    return redirect(url_for('posts_index'))


@app.errorhandler(404)
def page_not_found(error):
    return render_template('errors/404.html'), 404


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password reset request', sender='noreply@demo.com', recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link :
{url_for('reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
'''
    mail.send(msg)


@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('posts_index'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        send_reset_email(user)
        flash('Un email vous est envoyé avec des instructions pour réinitialiser votre mot de passe.', 'info')
        return redirect(url_for('login'))
    return render_template('pages/reset_request.html', title='Reset password', form=form)


@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('posts_index'))
    user = User.verify_reset_token(token)
    if user is None:
        flash("C'est un jeton invalide ou expiré", 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Votre mot de passe a été mis à jour ! Vous pouvez maintenant vous connectez', 'success')
        return redirect(url_for('login'))
    return render_template('pages/reset_token.html', title='Reset password', form=form)