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


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(800))
    pub_date = db.Column(db.DateTime, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    memory_lvl_id = db.Column(db.Integer, db.ForeignKey('memory_lvl.id'))
    answered = db.Column(db.Integer)
    answered_correct = db.Column(db.Integer)
    answered_false = db.Column(db.Integer)
    
    memory_lvl = db.relationship('Memory_lvl',
                               backref=db.backref('questions', lazy='dynamic'))
    category = db.relationship('Category',
                               backref=db.backref('questions', lazy='dynamic'))

    def answered_update(self):
        self.answered = Answer.query.filter(Answer.option.question==self).count()
        return self.answered
    
    def answered_correct_update(self):
        self.answered_correct = Answer.query.join(Option).filter(Answer.option.question==self, Option.correctness==True).count()
        return self.answered_correct

    def answered_false_update(self):
        self.answered_false = Answer.query.join(Option).filter(Answer.option.question==self, Option.correctness==False).count()
        return self.answered_false

    def memorized_period(self):
        if Memory_lvl.query.filter(Memory_lvl.num==self.memory_lvl.num).first():
            return Memory_lvl.query.filter(Memory_lvl.num==self.memory_lvl.num).first().time_sec
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
        if self.memory_lvl.num > 0:
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
        self.answered = 0
        self.answered_correct = 0
        self.answered_false = 0

    def __repr__(self):
        return '<Question %r>' % self.question_text


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    option_text = db.Column(db.String(800))
    correctness = db.Column(db.Boolean)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id', ondelete="CASCADE"))
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
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'))
    memory_lvl_id = db.Column(db.Integer, db.ForeignKey('memory_lvl.id'))
    
    option = db.relationship('Option',
                             backref=db.backref('answers', lazy='dynamic'))
    memory_lvl = db.relationship('Memory_lvl',
                             backref=db.backref('answers', lazy='dynamic'))
    
    def __init__(self, option, take_datetime=None):
        self.option = option
        if take_datetime is None:
            take_datetime = datetime.utcnow()
        self.take_datetime = take_datetime
        question = option.question
        # it should be memory level of question, if it was None then give that Question Memory lvl=0
        # if there is not Memory lvl 0 create it and asign it to question
        if question.memory_lvl == None:
            if Memory_lvl.query.filter(Memory_lvl.num==0).first():
                question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==0).first()
            else:
                db.session.add(Memory_lvl(0))
                db.session.commit()
                question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==0).first()
        memory_lvl_to_update = option.question.memory_lvl
        self.memory_lvl = question.memory_lvl
        # when answer is given question has to increment its memory lvl if answer correct, or zero if false
        if option.correctness:
            # if there is no such level create it
            if Memory_lvl.query.filter(Memory_lvl.num==option.question.memory_lvl.num+1).first():
                option.question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==option.question.memory_lvl.num+1).first()
            else:
                db.session.add(Memory_lvl(option.question.memory_lvl.num+1))
                db.session.commit()
                option.question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==option.question.memory_lvl.num+1).first()
        elif not option.correctness:
            if Memory_lvl.query.filter(Memory_lvl.num==0).first():
                option.question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==0).first()
            else:
                db.session.add(Memory_lvl(0))
                db.session.commit()
                option.question.memory_lvl = Memory_lvl.query.filter(Memory_lvl.num==0).first()
        db.session.commit()
        # in the end update memory lvl time
        # memory level that question was before answering if any
        memory_lvl_to_update.update()


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
        return Answer.query.filter(Answer.memory_lvl==self).count()
    
    def questions(self):
        return Question.query.filter(Question.memorized_lvl==self.num).count()

    def answers_correct_num(self):
        return Answer.query.join(Option).filter(Option.correctness==True, Answer.memory_lvl==self).count()
    
    def answers_false_num(self):
        return Answer.query.join(Option).filter(Option.correctness==False, Answer.memory_lvl==self).count()
    
    def ratio(self):
        if not self.answers_num() == 0:
            return self.answers_correct_num() / float(self.answers_num())  
        else:
            return 0

    def update(self):
        # execute only after adding new answer, otherwise, might buuuu!!!
        # update memory level of num which it had before answering after answering NOT
        # any other, like one higher!
        print("update")
        print(self)
        if self.ratio() > 0.99:
            self.time_sec = (self.time_sec+1)*2
        elif self.ratio() < 0.95:
            self.time_sec = self.time_sec/2+1
        db.session.commit()
        print(self.time_sec)
        return None 

    def __init__(self, num):
        if num == 0:
            time_sec = 0
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


@app.route('/clean')
def clean():
    db.drop_all()
    db.create_all()


@app.route('/update-memory-lvls', methods=['POST'])
def update_memory_lvls():
    for lvl in Memory_lvl.query.all():
        lvl.update()
    db.session.commit()
    return redirect(url_for('show_entries'))


@app.route('/delete-memory-lvl', methods=['POST'])
def delete_memory_lvl():
    memory_lvl = Memory_lvl.query.get(request.form['memory_lvl_id'])
    db.session.delete(memory_lvl)
    db.session.commit()
    flash('Memory lvl was successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/delete-all-memory-lvls', methods=['POST'])
def delete_all_memory_lvls():
    for m in Memory_lvl.query.all():
        db.session.delete(m)
    db.session.commit()
    flash('All memory lvls ware successfully deleted')
    return redirect(url_for('show_entries'))


@app.route('/quest')
def quest():
    #for q in Question.query.all():
    #    print(q)
    #    print(q.memory_lvl)
    #
    questions_with_mem_lvl = Question.query.filter(Question.memory_lvl != None).all()
    if questions_with_mem_lvl:
        print("there are some with mem lvl")
        answeredQuestions_not_in_mem = []
        for q in questions_with_mem_lvl:
            if not q.in_memory():
                answeredQuestions_not_in_mem.append(q)
        answeredQuestions_not_in_mem.sort(key=lambda x: x.memory_lvl.num, reverse=True)
        if answeredQuestions_not_in_mem:
            print("there are some with mem lvl and not in mem")
            the_question=questions_with_mem_lvl[-1]
        else:
            print("there are some with mem lvl but all in mem")
            the_question = Question.query.filter(Question.memory_lvl == None).first()
    else:
        print("there are no q in mem lvl")
        the_question = Question.query.filter(Question.memory_lvl == None).first()
    return render_template('quest.html', 
            the_question=the_question,
            )


@app.route('/quest-check', methods=['POST'])
def quest_check():
    option = Option.query.get(request.form['option_id'])
    answer = Answer(option)
    db.session.add(answer)
    db.session.commit()
    if option.correctness is True:
        flash(u'Correct!', 'flash')
    else:
        correct_option = option.question.optins.query.filter(Option.correctness==True).first()
        flash(u'Buuuuuuuuu!!!', 'error')
        flash(u'Corect is: %s', correct_option.option_text, 'flash')
    return redirect(url_for('quest'))


@app.route('/question/<question_id>')
def show_question(question_id):
    return render_template('show_question.html', 
            Question=Question,
            Option=Option,
            Answer=Answer,
            Memory_lvl=Memory_lvl,
            Category=Category,
            memory_lvls=Memory_lvl.query.all(),
            the_question=Question.query.filter(Question.id==question_id).first(),
            )


@app.route('/')
def show_entries():
    memory_lvls=Memory_lvl.query.all()
    memory_lvls.sort(key=lambda x: x.num, reverse=True)
    return render_template('show_entries.html', 
            categories_count=Category.query.count(),
            questions_count=Question.query.count(),
            answers_count=Answer.query.count(),
            Question_ob=Question,
            Option_ob=Option,
            Answer_ob=Answer,
            Memory_lvl_ob=Memory_lvl,
            answers_true_count=Answer.query.join(Option).filter(Option.correctness==True).count(),
            answers_false_count=Answer.query.join(Option).filter(Option.correctness==False).count(),
            memory_lvls=memory_lvls,
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
    flash('Question was successfully deleted with its options')
    return redirect(url_for('show_entries'))


@app.route('/del-all-questions', methods=['POST'])
def del_all_questions():
    for q in Question.query.all():
        db.session.delete(q)
    db.session.commit()
    flash('All questions ware successfully deleted')
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


if __name__ == '__main__':
    app.run()


# TODO
# fix memory levels
# ETA 2h
#
# some stats
# % of learned material (how many qestions are in staging KISS
# ETA 3h
