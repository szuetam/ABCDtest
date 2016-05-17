import random
from contextlib import closing
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash

app = Flask(__name__)
app.config.from_envvar('settings.cfg', silent=True)
#it is not using settings.cfg just I dont know how to replace silent=True while removing it
app.config.update(
        DATABASE = 'ppl.db',
        DEBUG = True,
        SECRET_KEY = 'development key',
        USERNAME = 'ppl',
        PASSWORD = 'ppl',
        SQLALCHEMY_TRACK_MODIFICATIONS = False,
        SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/test.db',
)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/pre-registration'
#that above I would move to config higher
db = SQLAlchemy(app)


def filter_shuffle(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except:
        return seq
app.jinja_env.filters['shuffle'] = filter_shuffle

#does it being used? rather not, if not delete
def filter_memorized(the_question):
    try:
        last_false_answer=Answer.query.join(Option).filter(Option.correctness==False, Option.question==the_question).order_by(Answer.take_datetime.desc()).first()
        result=Answer.query.filter(Answer.take_datetime > last_false_answer.take_datetime)
        return result.count()
    except:
        return "0, albo brak odpowiedzi wogole"
app.jinja_env.filters['memorized'] = filter_memorized

#not used? then delete
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    email = db.Column(db.String(120), unique=True)

    def __init__(self, username, email):
        self.username = username
        self.email = email

    def __repr__(self):
        return '<User %r>' % self.username


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(800))
    pub_date = db.Column(db.DateTime, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    category = db.relationship('Category',
                               backref=db.backref('questions', lazy='dynamic'))
    answered = db.Column(db.Integer)
    answered_correct = db.Column(db.Integer)
    answered_false = db.Column(db.Integer)
   
    def update_all(self):
        self.answered_update()
        self.answered_correct_update()
        self.answered_false_update()

    def answered_update(self):
        answered = Answer.query.filter(Answer.question==self).all()
        if answered:
            answered = len(answered)
        else:
            answered = 0
        self.answered = answered
        return answered
    
    def answered_correct_update(self):
        self.answered_correct = len(Answer.query.join(Option).filter(Answer.question==self, Option.correctness==True).all())
        return self.answered_correct

    def answered_false_update(self):
        self.answered_false = len(Answer.query.join(Option).filter(Answer.question==self, Option.correctness==False).all())
        return self.answered_false

    def memorized_lvl(self):
        if self.answered == 0:
            return 0
        elif self.answered == self.answered_correct:
            return self.answered_correct
        else:
            last_false_answer=Answer.query.join(Option).filter(Option.correctness==False, Option.question==self).order_by(Answer.take_datetime.desc()).first()
            correct_answers_since_last_false_answer=Answer.query.join(Option).filter(Option.correctness==True, Option.question==self, Answer.take_datetime > last_false_answer.take_datetime).all()
            return len(correct_answers_since_last_false_answer)
    
    def memorized_period(self):
        if Memory_lvl.query.filter(Memory_lvl.num==self.memorized_lvl()).first():
            return Memory_lvl.query.filter(Memory_lvl.num==self.memorized_lvl()).first().time_sec
        else:
            return 0

    def last_correct_answer_time(self):
        if Answer.query.join(Option).filter(Option.correctness==True, Option.question==self).first():
            return Answer.query.join(Option).filter(Option.correctness==True, Option.question==self).order_by(Answer.take_datetime.desc()).first().take_datetime
        else:
            return datetime.utcnow() - timedelta(weeks=5200) #mean did not know that for about 100years or so ;)

    def in_memory(self):
        if self.last_correct_answer_time() + timedelta(seconds=self.memorized_period()) > datetime.utcnow():
            return True
        else:
            return False
    
    def potential_in_memory(self):
        if self.memorized_lvl() > 0:
            return True
        else:
            return False
    
    def potential_in_memory_but_not_in_memory(self):
        if self.potential_in_memory() and not self.in_memory():
            return True
        else:
            return False

    def time_of_forgeting(self):
        return self.last_correct_answer_time() + timedelta(seconds=self.memorized_period())

    def time_left_in_memory(self):
        time = self.time_of_forgeting() - datetime.utcnow() 
        if time > timedelta(0):
            return time
        else:
            return 0

    def __init__(self, question_text, category, pub_date=None):
        self.question_text = question_text
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date
        self.category = category
        self.update_all()

    def __repr__(self):
        return '<Question %r>' % self.question_text


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    option_text = db.Column(db.String(800))
    correctness = db.Column(db.Boolean)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    question = db.relationship('Question',
                               backref=db.backref('options', lazy='dynamic'))

    def __init__(self, option_text, correctness, question):
        self.option_text = option_text
        self.correctness = correctness
        self.question = question
    
    def __repr__(self):
        return '<Answer %r>' % self.option_text


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    take_datetime = db.Column(db.DateTime, default=datetime.utcnow)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'))
    question = db.relationship('Question',
                               backref=db.backref('answers', lazy='dynamic'))
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'))
    option = db.relationship('Option',
                             backref=db.backref('answers', lazy='dynamic'))
    memory_lvl_id = db.Column(db.Integer, db.ForeignKey('memory_lvl.id'))
    memory_lvl = db.relationship('Memory_lvl',
                             backref=db.backref('answers', lazy='dynamic'))
    
    def __init__(self, option, question=None, memory_lvl=None, take_datetime=None):
        # For future me, not to assign memory_lvl of quesion after (this is always 0 for fals) but before
        if memory_lvl is None:
            memory_lvl = option.question.memorized_lvl()
            if not Memory_lvl.query.filter(Memory_lvl.num==option.question.memorized_lvl()).first():
                lvl = Memory_lvl(memory_lvl)
                db.session.add(lvl)
                db.session.commit()
            memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==option.question.memorized_lvl()).first()
        self.memory_lvl = memory_lvl
        self.option = option
        if take_datetime is None:
            take_datetime = datetime.utcnow()
        self.take_datetime = take_datetime
        if question is None:
            question = option.question
        self.question = question
        self.question.update_all()

    def __repr__(self):
        return '<Answer %r>' % self.question


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<Category %r>' % self.name


class Memory_lvl(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    num = db.Column(db.Integer, unique=True)
    time_sec = db.Column(db.Integer)
    
    def answers_num(self):
        return len(Answer.query.filter(Answer.memory_lvl==self).all())
    
    def questions(self):
        return len(Question.query.filter(Question.memorized_lvl==self.num).all())

    def answers_correct_num(self):
        return len(Answer.query.join(Option).filter(Option.correctness==True, Answer.memory_lvl==self).all())
    
    def answers_false_num(self):
        return len(Answer.query.join(Option).filter(Option.correctness==False, Answer.memory_lvl==self).all())
    
    def ratio(self):
        if not self.answers_num() == 0:
            return self.answers_correct_num() / float(self.answers_num())  
        else:
            print ("error, there should be one answer when updating")
            return 0

    def update(self):
        # execute only after adding new answer, otherwise, buuuu!!!
        if self.ratio() > 0.99:
            self.time_sec = self.time_sec*2
        elif self.ratio() < 0.95:
            self.time_sec = self.time_sec/2
        db.session.commit()
        return None 

    def __init__(self, num):
        if num == 0:
            time_sec = 0
        elif num == 1:
            time_sec = 1
        else:
            time_sec = Memory_lvl.query.filter(Memory_lvl.num==(num-1)).first().time_sec
        self.num = num
        self.time_sec = time_sec

    def __repr__(self):
        return '<Memory_lvl %r>' % self.num


def Memory_lvl_init():
    if not Memory_lvl.query.filter(Memory_lvl.num==0).first():
        #tworzymy go
        lvl = Memory_lvl(0)
        db.session.add(lvl)
        db.session.commit()


@app.route('/update-memory-lvl', methods=['POST'])
def update_memory_lvl():
    memory_lvl   =   Memory_lvl.query.get(request.form['memory_lvl_id'])
    memory_lvl.update()
    return redirect(url_for('show_entries'))


@app.route('/update-memory-lvls', methods=['POST'])
def update_memory_lvls():
    for lvl in Memory_lvl.query.all():
        lvl.update()
    db.session.commit()
    return redirect(url_for('show_entries'))


@app.route('/quest')
def quest():
    answeredQuestions_pre=Question.query.filter(Question.answered > 0).all()
    answeredQuestions_not_in_mem = []
    for q in answeredQuestions_pre:
        if not q.in_memory():
            answeredQuestions_not_in_mem.append(q)
    answeredQuestions_not_in_mem.sort(key=lambda x: x.memorized_lvl(), reverse=True)
    if answeredQuestions_not_in_mem:
        the_question=answeredQuestions_not_in_mem[-1]
    else:
        the_question = Question.query.filter(Question.answered == 0).first()
    return render_template('quest.html', 
            the_question=the_question,
            )


@app.route('/quest-check', methods=['POST'])
def quest_check():
    if not session.get('logged_in'):
        abort(401)
    option   =   Option.query.get(request.form['option_id'])
    answer = Answer(option)
    db.session.add(answer)
    mem_lvl = answer.question.memorized_lvl()
    if not Memory_lvl.query.filter(Memory_lvl.num==mem_lvl).first():
        db.session.add(Memory_lvl(mem_lvl))
    Memory_lvl.query.filter(Memory_lvl.num==mem_lvl).first().update()
    db.session.commit()
    if option.correctness is True:
        flash(u'Correct!', 'flash')
    else:
        flash(u'Buuuuuuuuu!!!', 'error')
    return redirect(url_for('quest'))

    
@app.route('/')
def show_entries():
    return render_template('show_entries.html', 
            categories_count=Category.query.count(),
            questions_count=Question.query.count(),
            answers_count=Answer.query.count(),
            Question_ob=Question,
            Option_ob=Option,
            Answer_ob=Answer,
            Memory_lvl_ob=Memory_lvl,
            memory_lvls=Memory_lvl.query.all(),
            answers_true_count=Answer.query.join(Option).filter(Option.correctness==True).count(),
            answers_false_count=Answer.query.join(Option).filter(Option.correctness==False).count(),
            questions=Question.query.all(),
            categories=Category.query.all(),
            answers=Answer.query.all(),
            options=Option.query.all(),
            )


@app.route('/add-question', methods=['POST'])
def add_entry():
    if not session.get('logged_in'):
        abort(401)
    # TODO: get_or_404
    category = Category.query.get(request.form['category_id'])
    quest = Question(question_text=request.form['question'],
                     category=category)
    db.session.add(quest)
    db.session.add(Option(option_text=request.form['answer_A'], correctness=True, question=quest))
    db.session.add(Option(option_text=request.form['answer_B'], correctness=False, question=quest))
    db.session.add(Option(option_text=request.form['answer_C'], correctness=False, question=quest))
    db.session.add(Option(option_text=request.form['answer_D'], correctness=False, question=quest))
    db.session.commit()
    flash('New question was successfully added')
    return redirect(url_for('show_entries'))


@app.route('/del-question', methods=['POST'])
def del_entry():
    question = Question.query.get(request.form['question_id'])
    db.session.delete(question)
    db.session.commit()
    flash('Question was successfully deleted but not its options')
    return redirect(url_for('show_entries'))
##### add and its options!!


@app.route('/del-all-questions', methods=['POST'])
def del_all_questions():
    Question.query.delete()
    db.session.commit()
    flash('All questions ware successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/del-all-options', methods=['POST'])
def del_all_options():
    Option.query.delete()
    db.session.commit()
    flash('All options ware successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/add-category', methods=['POST'])
def add_category():
    if not session.get('logged_in'):
        abort(401)
    db.session.add(Category(request.form['category']))
    db.session.commit()
    flash('New category was successfully added')
    return redirect(url_for('show_entries'))


@app.route('/del-category', methods=['POST'])
def del_category():
    category = Category.query.get(request.form['category_id'])
    db.session.delete(category)
    db.session.commit()
    flash('Category was successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/del-all-categoriess', methods=['POST'])
def del_all_categories():
    Category.query.delete()
    db.session.commit()
    flash('All categories ware successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/check', methods=['POST'])
def check():
    if not session.get('logged_in'):
        abort(401)
    option   =   Option.query.get(request.form['option_id'])
    db.session.add(Answer(option))
    db.session.commit()
    if option.correctness is True:
        flash('Correct!')
    else:
        flash('Buuuuuu!')

    return redirect(url_for('show_entries'))


@app.route('/del-answer', methods=['POST'])
def del_answer():
    answer = Answer.query.get(request.form['answer_id'])
    db.session.delete(answer)
    db.session.commit()
    flash('Answer was successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/del-all-answers', methods=['POST'])
def del_all_answers():
    Answer.query.delete()
    db.session.commit()
    flash('All answers ware successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != 'ppl':
            error = 'Invalid username'
        elif request.form['password'] != 'ppl':
            error = 'Invalid password'
        else:
            session['logged_in'] = True
            flash('You were logged in')
            return redirect(url_for('show_entries'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('show_entries'))


if __name__ == '__main__':
    app.run()


# TODO
#
# proper deleting with childs, and not deleting childs without parents when needed
# ETA 3h - need to learn that
#
# move to more variables and only updating functions
# ETA - 3h 
#
# some stats
# % of learned material (how many qestions are in staging KISS
# ETA 3h
