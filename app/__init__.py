from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_mail import Mail
import logging
from logging.handlers import SMTPHandler,RotatingFileHandler
import os
from elasticsearch import Elasticsearch

bootstrap = Bootstrap()
mail = Mail()
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
moment = Moment()
login.login_view='auth.login'
login.login_messsage='Please log in to access this page.'

def create_app(config_class=Config):

    #App API initializations
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    mail.init_app(app)
    bootstrap.init_app(app)
    moment.init_app(app)
    app.elasticsearch = Elasticsearch([app.config['ELASTICSEARCH_URL']], verify_certs=False) if app.config['ELASTICSEARCH_URL'] else None

    #Registering the blurprints
    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.pages import bp as pages_bp
    app.register_blueprint(pages_bp)

    from app.todo import bp as todo_bp
    app.register_blueprint(todo_bp)

    if not app.debug:
        #Mail support for error reporting
        if app.config['MAIL_SERVER']:
            auth = None
            if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
                auth = (app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            secure = None
            if app.config['MAIL_USE_TLS']:
                secure = ()
            mail_handler = SMTPHandler(
                mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
                fromaddr='no-reply@' + app.config['MAIL_SERVER'],
                toaddrs=app.config['ADMINS'], subject='Weekly planner Failure',
                credentials=auth, secure=secure)
            mail_handler.setLevel(logging.ERROR)
            app.logger.addHandler(mail_handler)

        #logging
        if app.config['LOG_TO_STDOUT']:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
        else:
            if not os.path.exists('logs'):
                os.mkdir('logs')
            file_handler = RotatingFileHandler('logs/todo.log', maxBytes=10240,
                                               backupCount=10)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Weekly Planner startup')

    return app
