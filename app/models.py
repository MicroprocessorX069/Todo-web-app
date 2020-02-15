from flask import current_app
from datetime import datetime
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login
from app.search import add_to_index, remove_from_index, query_index
from hashlib import md5
import jwt
from time import time
import os
from flask import send_from_directory

class SearchableMixin(object):
	@classmethod
	def search(cls, expression, page, per_page):
		ids, total = query_index(cls.__tablename__, expression, page, per_page)
		if total == 0:
			return cls.query.filter_by(id=0), 0
		when = []
		for i in range(len(ids)):
			when.append((ids[i], i))
		return cls.query.filter(cls.id.in_(ids)).order_by(
		    db.case(when, value=cls.id)), total

	@classmethod
	def before_commit(cls, session):
		session._changes = {
		    'add': list(session.new),
		    'update': list(session.dirty),
		    'delete': list(session.deleted)
		}

	@classmethod
	def after_commit(cls, session):
		for obj in session._changes['add']:
			if isinstance(obj, SearchableMixin):
				add_to_index(obj.__tablename__, obj)
		for obj in session._changes['update']:
			if isinstance(obj, SearchableMixin):
				add_to_index(obj.__tablename__, obj)
		for obj in session._changes['delete']:
			if isinstance(obj, SearchableMixin):
				remove_from_index(obj.__tablename__, obj)
		session._changes = None

	@classmethod
	def reindex(cls):
		for obj in cls.query:
		    add_to_index(cls.__tablename__, obj)

db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)

followers = db.Table('followers',
		db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
		db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
		)

class User(UserMixin, SearchableMixin, db.Model):
	__searchable__ = ['username', 'email']
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String(64), index=True, unique=True)
	email = db.Column(db.String(120), index=True, unique=True)
	password_hash = db.Column(db.String(128))
	first_name=db.Column(db.String(40), default="None")
	last_name=db.Column(db.String(60), default = "None")
	about_me = db.Column(db.String(140))
	profile_pic=db.Column(db.String(10),default="None")
	last_seen = db.Column(db.DateTime, default=datetime.utcnow)
	posts = db.relationship('Post', backref='author', lazy='dynamic')
	tasks = db.relationship('Task', backref='doer', lazy = 'dynamic')
	#Need to change here. 15:08
	followed = db.relationship(
				'User', secondary = followers,
				#primary join is for connections from User to other users.
				# c is for columns of table followers
				primaryjoin = (followers.c.follower_id == id),
				#secondaryjoin is for connections of user whom I am following
				secondaryjoin = (followers.c.followed_id == id),
				backref = db.backref('followers', lazy = 'dynamic'), lazy = 'dynamic')
	challenges_followed = db.relationship('Challenge', secondary='challengers',
											backref = db.backref('challengers', lazy = 'dynamic'))

	def __repr__(self):
		return '<User {}>'.format(self.username)

	#Generates SHA 256 hash of the given password
	def set_password(self, password):
		self.password_hash = generate_password_hash(password)

	def check_password(self, password):
		return check_password_hash(self.password_hash, password)

	def avatar(self,size):
		digest=md5(self.email.lower().encode('utf-8')).hexdigest()
		return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)


	def set_profile_pic(self,status):
		self.profile_pic = status
		print("Profile pic set:",self.profile_pic)

	def is_following(self, user):
		#Checks the complete column of followers for user.id
		return self.followed.filter( followers.c.followed_id == user.id).count() > 0

	def follow(self, user):
		if not self.is_following(user):
			self.followed.append(user)

	def unfollow(self, user):
		if self.is_following(user):
			self.followed.remove(user)

	def followed_posts(self):
		followed = Post.query.join(
		    followers, (followers.c.followed_id == Post.user_id)).filter(
		        followers.c.follower_id == self.id)
		own = Post.query.filter_by(user_id = self.id)
		return followed.union(own).order_by(Post.timestamp.desc())

	def get_reset_password_token(self, expires_in=600):
		return jwt.encode({'reset_password':self.id, 'exp': time()+expires_in}, current_app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')

	@staticmethod
	def verify_reset_password_token(token):
		try:
			id = jwt.decode(token, app.config['SECRET_KEY'], algorithm = ['HS256'])['reset_password']
		except:
			return
		return User.query.get(id)


@login.user_loader
def load_user(id):
	return User.query.get(int(id))

class Task(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(50))
	timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	#Active Pending, Active on track, Complete
	challenge = db.relationship('Challenge')
	challenge_id=db.Column(db.Integer, db.ForeignKey('challenge.id'))
	status=db.Column(db.String, index=True, default='Active begin')
	#challenger_id=db.Column(db.Integer, db.ForeignKey('challengers.id'))
	n_subtasks = db.Column(db.Integer, index=True, default=0)
	nc_subtasks = db.Column(db.Integer, index=True, default=0)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	subtasks = db.relationship('Subtask', backref='task', lazy='dynamic')
	streak = db.Column(db.Integer, default = 0)
	#challenger_row = db.relationship('challenger', backref='task', lazy='dynamic')
	#challenge = db.relationship('Challenge', secondary='challengers',
	#							backref = db.backref('task', lazy = 'dynamic'))

	def __repr__(self):
		return '<Task {}>'.format(self.name)

	def completion_percent(self):
		nc_subtasks=self.recount_nc_subtasks()
		n_subtasks=self.recount_n_subtasks()
		percent=str(int(nc_subtasks*100/n_subtasks)) \
			if self.n_subtasks>0 else '0'
		return percent

	def recount_n_subtasks(self):
		temp = Subtask.query.filter_by(task_id=self.id).count()
		self.n_subtasks=temp
		return temp

	def recount_nc_subtasks(self):
		temp = Subtask.query.filter_by(task_id=self.id,status=1).count()
		self.nc_subtasks = temp
		return temp

	def get_streak(self):
		#the task must have a challenge associated
		if self.challenge!=None:
			return self.streak
		else:
			return None

	def change_streak(self, val): #here val would be +1 or -1
		#the task must have a challenge associated
		#No checking of status done here.
		if self.challenge!=None:
			self.streak+=val
			db.session.commit()
			return True
		else:
			return False

	def set_status(self, status):
		self.status =  status
		db.session.commit()
		return True

	def reset_streak(self):# setting streak back to zero
			if self.challenge!=None:
				#challenger_row=challengers.query.filter_by(challenge_id=self.challenge.id, user_id=self.user_id).first()
				self.streak=0
				self.status = 'Active pending'
				db.session.commit()
				return True
			else: #task is a normal task and not a challenge task
				return False



class Subtask(db.Model):
	id = db.Column(db.Integer, primary_key=True)
	name = db.Column(db.String(150))
	timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	#1 is task complete, 0 is task incomplete
	status = db.Column(db.Integer, index=True, default=0)
	task_id = db.Column(db.Integer, db.ForeignKey('task.id'))

	def __repr__(self):
		return '<Subtask {} {}>'.format(self.name, self.status)

	def check(self):
		self.status=1
		db.session.commit()

	def uncheck(self):
		self.status=0
		db.session.commit()

class Post(SearchableMixin, db.Model):
	__searchable__ = ['body']
	id = db.Column(db.Integer, primary_key=True)
	body = db.Column(db.String(140))
	timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
	challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'))

	def __repr__(self): # for printing while deubgging
		return '<Post {}>'.format(self.body)

class Challenge( SearchableMixin, db.Model):
	__searchable__=['name', 'description']
	id = db.Column(db.Integer, primary_key = True)
	name = db.Column(db.String(50), unique = True)
	description = db.Column(db.String(600))
	#0: Daily, 1: Weekly, 2: Monthly
	interval = db.Column(db.Integer, index=True, default = 0)
	total_days = db.Column(db.Integer, index=True, default = 30)
	#0: Follower defined, 1: Admin defined
	type = db.Column(db.Integer, default = 0)
	difficulty = db.Column(db.Integer, default = 0)
	posts = db.relationship('Post', backref='challenge', lazy='dynamic')
	n_followers = db.Column(db.Integer, default = 0)
	creator_id = db.Column(db.Integer, default = 0)
	#follower_tasks=db.relationship('Task', backref='challenge',lazy='dynamic')

	def __repr__(self): # for printing while deubgging
		return '<Challenge {}>'.format(self.name, self.interval, self.total_days)

	def followed_by(self, user):
		return self.challengers.filter( challengers.c.user_id == user.id).count() > 0

	def follow_request(self, user):
		if not self.followed_by(user):
			#insert_query = challenger.insert().values(challenge_id = self.id, \
			#										  user_id = user.id, \
			#										  task_id = task.id)
			self.challengers.append(user)
			#db.session.execute(insert_query)
			#db.session.commit()
			self.n_followers+=1
			db.session.commit()
		#ONce followed, create a recurring task for the user.

	def unfollow_request(self, user):
		if self.followed_by(user):
			self.challengers.remove(user)
			self.n_followers-=1

challengers = db.Table('challengers',
		db.Column('challenge_id', db.Integer, db.ForeignKey('challenge.id')),
		db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
		#db.Column('task_id', db.Integer, db.ForeignKey('task.id')),
		#db.Column('streak', db.Integer, default=0)
		)
#TODO Feb 8 22:18: Need to configure a class table for challengers.
# class challengers(db.Model):
# 	challenge_id = db.Column(db.Integer, db.ForeignKey('challenge.id'))
# 	user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
# 	task_id = db.Column(db.Integer, db.ForeignKey('task.id'))
# 	streak = db.Column(db.Integer, default = 0)
# 	challenge = db.relationship('Challenge', backref = 'challenge', lazy='dynamic')
# 	user = db.relationship('User', backref = 'challenger_row', lazy='dynamic')
# 	task = db.relationship('Task', backref = 'challenger_row', lazy='dynamic')
