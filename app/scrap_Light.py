import csv
import logging
import logging.config
import matplotlib.dates
import matplotlib.pyplot as plt
import os
import os.path
import pytz
from bs4 import BeautifulSoup
from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import sys
import time
from flask_sqlalchemy import SQLAlchemy
from flask import Flask, request, session, g, redirect, url_for, \
    abort, render_template, flash
from contextlib import closing
from datetime import datetime, timedelta
import random
from app import *

app = Flask(__name__)
app.config.from_envvar('settings.cfg', silent=True)
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
db = SQLAlchemy(app)


# -*- Settings -*-

LOG_DIR = 'log/'
LOGGING = {
    'version': 1,
    #'disable_existing_loggers': True,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(name)s %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(name)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.WatchedFileHandler',
            'encoding': 'utf-8',
            'filename': os.path.join(LOG_DIR, 'app.log'),
            'formatter': 'verbose',
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.WatchedFileHandler',
            'encoding': 'utf-8',
            'filename': os.path.join(LOG_DIR, 'debug.log'),
            'formatter': 'verbose',
        },
    },

    'root': {
        'handlers': ['console', 'file', 'file_debug',],
        'level': 'DEBUG',
    },
    'loggers': {
        'selenium': {
            'handlers': ['file_debug'],
            'propagate': False,
            'level': 'DEBUG',
        },
        'easyprocess': {
            'handlers': ['file_debug'],
            'propagate': False,
            'level': 'DEBUG',
        },
    }
}

# -*- EO: Settings -*-

logging.config.dictConfig(LOGGING)
log = logging.getLogger()

class Site(object):
    TIME_ZONE = pytz.timezone('Europe/Warsaw')

    def __init__(self, driver):
        self.driver = driver
        self.login()
        self.go_to_datatab()

    def login(self):
        file = open('logandpass.txt')
        login =file.readline().rstrip('\n')
        log.info('login login is %s', login)
        password =file.readline().rstrip('\n')
        log.info('login password is %s', password)
        driver = self.driver
        log.info('login Fetching main page')
        driver.get("http://platform.ventumair.eu/")
        #Log in
        driver.find_element_by_id("login_username").send_keys(login)
        log.info('login Login typed')
        driver.find_element_by_id("login_password").send_keys(password)
        log.info('login Pass typed')
        driver.find_element_by_xpath('//*[@id="login"]/div[4]/input').click()
        time.sleep(3)
        log.info('login Login sent')

    def go_to_datatab(self):
        driver = self.driver
        link_text = "CXXIII Edycja kursu PPL (A) 7 Marca 2016"
        log.info('go_to_datatab %s', link_text)
        driver.find_element_by_link_text(link_text).click()
        time.sleep(3)
        log.info('go_to_datatab On datatab')

        
    def page_grab(self, page_text):
        driver = self.driver
        log.info('page_grab enter questions')
        log.info('page_grab Grab page: %s', page_text)
        driver.find_element_by_link_text(page_text).click()
        time.sleep(3)
        source = driver.page_source
        log.info('page_grab back to datatab')
        self.go_to_datatab()
        log.info('page_grab Grabbed page: %s', page_text)
        return source


    def page_grab_since(self):
        link_texts = ["Prawo lotnicze oraz procedury kontroli ruchu lotniczego - baza pytań kursu PPL (A)", 
                "Procedury operacyjne - baza pytań kursu PPL (A)",
                "Ogólna wiedza o statku powietrznym - baza pytań kursu PPL (A)",
                "Zasady lotu: samolot - baza pytań kursu PPL (A)",
                "Łączność - baza pytań kursu PPL (A)",
                "Meteorologia - baza pytań kursu PPL (A)",
                "Człowiek - możliwości i ograniczenia - baza pytań kursu PPL (A)",
                "Nawigacja - baza pytań kursu PPL (A)",
                "Wykonanie i planowanie lotu - baza pytań kursu PPL (A)",
                ]
        for page_link_text in link_texts:
            source = self.page_grab(page_link_text)
            log.info("page_grab_since Grabed page %s", page_link_text)
            self.page_parse(source)
            log.info("page_grab_since Grabed and Parsed page %s", page_link_text)
        return None


    def add_question(self, category, the_question, answer_A, answer_B, answer_C, answer_D):
        quest = Question(question_text=the_question,
                         category=category)
        db.session.add(quest)
        db.session.commit()
        log.info('New question was successfully added %s', the_question)

        db.session.add(Option(option_text=answer_A, correctness=True, question=quest))
        db.session.add(Option(option_text=answer_B, correctness=False, question=quest))
        db.session.add(Option(option_text=answer_C, correctness=False, question=quest))
        db.session.add(Option(option_text=answer_D, correctness=False, question=quest))
        db.session.commit()
        log.info('Option A %s', answer_A)
        log.info('Option B %s', answer_B)
        log.info('Option C %s', answer_C)
        log.info('Option D %s', answer_D)
        log.info('New question was successfully added with options')


    def page_parse_row(self, category_and_questions):
        
        category_raw = category_and_questions[0]
        caq = category_and_questions[0].split('</p>')
        the_category = caq[0].replace('<div class="no-overflow"><p>', "")
        the_category = Category(the_category)
        db.session.add(the_category)
        db.session.commit()
        log.info('New category was successfully added')
        
        the_question = caq[2].replace("\n<p>Q: ", "")
        answer_A = caq[4].replace("\n<p>A) ", "")
        answer_B = caq[5].replace('\n<p>B) ', "")
        answer_C = caq[6].replace("\n<p>C) ", "")
        answer_D = caq[7].replace("\n<p>D) ", "")
        
        self.add_question(the_category, the_question, answer_A, answer_B, answer_C, answer_D)

        del category_and_questions[0]

        # pytania
        for question_raw in category_and_questions:
            q_split = str(question_raw).split('</p>')
            the_question = q_split[0].replace("<p>Q: ", "")
            answer_A = q_split[2].replace("\n<p>A) ", "")
            answer_B = q_split[3].replace('\n<p>B) ', "")
            answer_C = q_split[4].replace("\n<p>C) ", "")
            answer_D = q_split[5].replace("\n<p>D) ", "")
            self.add_question(the_category, the_question, answer_A, answer_B, answer_C, answer_D)

        return None

    def page_parse(self, source):
        bs2 = BeautifulSoup(source)
        bs = bs2.find('div', class_="no-overflow")
        category_and_questions = []
        for row in str(bs).split('\n<p> </p>\n<p> </p>\n'):
            #print("------------row")
            category_and_questions.append(row)
            #print(row)
            #print("------------row")
        self.page_parse_row(category_and_questions)
        return category_and_questions

    def results(self):
        if not hasattr(self, '_results'):
            base_path = os.path.dirname(__file__)
            data_path = os.path.join(base_path, 'data')
            tmp_path = os.path.join(base_path, 'tmp')
            output_path = os.path.join(base_path, 'output')
            results_path = os.path.join(data_path, 'results.csv')
            results = {}
            self.page_grab_since()
            self._results = results
        return self._results


def initialize_virtual_display():
    log.info('Initializing display')
    display = Display(visible=0, size=(800, 600))
    display.start()
    return display

def initialize_driver():
    log.info('Starting browser driver')
    chrome_options = webdriver.ChromeOptions()
    prefs = {"profile.managed_default_content_settings.images":1}
    chrome_options.add_experimental_option("prefs",prefs)
    driver = webdriver.Chrome(
        chrome_options=chrome_options,
        service_args=["--verbose", "--log-path=%s" % (os.path.join(LOG_DIR, 'driver.log'),)],
    )

    driver.set_window_size(1400,1000)
    driver.implicitly_wait(10)
    return driver

sys.setrecursionlimit(100000)

def main():
    start_time = datetime.now()
    display = initialize_virtual_display()
    try:
        driver = initialize_driver()
        try:
            site = Site(driver)
            site.results()
        finally:
            log.info('Quitting driver...')
            driver.quit()
    finally:
        log.info('Stopping display...')
        display.stop()

    delta = datetime.now() - start_time
    log.info('It took only %s, bye!', delta)

if __name__ == '__main__':
    main()
