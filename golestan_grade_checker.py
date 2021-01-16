#!/usr/bin/python3

import os
import jdatetime
import subprocess as s
from time import sleep
from kavenegar import *
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from config import GolestanGradeCheckerConfig


class GolestanGradeChecker:
    def __init__(self):
        self.config = GolestanGradeCheckerConfig()
        if self.config.tg_notif:
            from telegram.ext import Updater
            self.updater = Updater(self.config.tg_token)
        else:
            self.updater = None
        self.driver = self._setup_driver()

    def _setup_driver(self):
        # setup Firefox profile (you can use other browsers, but I prefer Firefox)
        options = Options()
        options.add_argument('-headless')  # run in headless mode (without gui)
        fp = webdriver.FirefoxProfile()
        fp.set_preference("browser.tabs.remote.autostart", False)
        fp.set_preference("browser.tabs.remote.autostart.1", False)
        fp.set_preference("browser.tabs.remote.autostart.2", False)
        driver = webdriver.Firefox(fp, options=options)
        return driver

    def run(self):
        """
        Logins to Golestan, goes to desired semester page and loops over it to get new grades
        :return:
        """
        self._login_to_golestan()
        sleep(10)
        self._go_to_etelaate_jame_daneshjoo_page()
        sleep(7)
        self._go_to_semester()
        sleep(7)

        self.driver.switch_to.default_content()
        self._switch_to_grades_frame(3)
        sleep(0.5)
        self.loop()

    def loop(self):
        """
        An infinite loop which keeps refreshing golestan grades page in given semester
        :return: None
        """
        previous_grades = None
        while True:
            given_grades = self._find_given_grades()
            self._print_grades(given_grades)
            if previous_grades is not None and previous_grades != given_grades:
                diff = dict(set(given_grades.items()) - set(previous_grades.items()))
                new_grades_message = self._create_grades_notif_message(diff)

                self._send_sms(new_grades_message)

            previous_grades = given_grades

            # give professors some time to insert our grades -_-
            sleep(self.config.refresh_rate * 60)

            self._refresh_grades_page()

    def _switch_to_grades_frame(self, faci_id):
        """
        Golestan uses frames. To access main body of page, we need to switch between its frames
        This function switches driver to main frame of grades in Etelaate Jame-e Daneshjoo.
        :param faci_id: Golestan frames has a Faci_id which is the id of that frame.
                According to our usage, we need to navigate to different Faci_ids.
        """
        self._switch_to_main_frame(faci_id)
        frame = self.driver.find_element_by_xpath('/html/body')
        frame = frame.find_element_by_xpath(""".//iframe[@id="FrameNewForm"]""")
        self.driver.switch_to.frame(frame)

    def _switch_to_main_frame(self, faci_id):
        """
        Golestan uses frames. To access main body of page, we need to switch between its frames
        This function switches driver to main frame of page (the contents)
        :param faci_id: Golestan frames has a Faci_id which is the id of that frame.
                According to our usage, we need to navigate to different Faci_ids.
        """
        WebDriverWait(self.driver, 50) \
            .until(ec.frame_to_be_available_and_switch_to_it((By.XPATH, f"""//*[@id="Faci{faci_id}"]""")))
        frame = self.driver.find_element_by_xpath('/html/frameset/frameset/frame[2]')
        self.driver.switch_to.frame(frame)
        frame = self.driver.find_element_by_xpath('/html/frameset/frame[3]')
        self.driver.switch_to.frame(frame)

    def _login_to_golestan(self):
        """
        Logs into Golestan system.
        You may need to change xpath of username and password fields if according to your university login web page.
        """
        self.driver.get(self.config.login_url)
        username_field = self.driver.find_element_by_xpath("""//input[@name="uid"]""")
        password_field = self.driver.find_element_by_xpath("""//input[@name="pass"]""")
        username_field.send_keys(self.config.username)
        password_field.send_keys(self.config.password)
        password_field.send_keys(Keys.ENTER)
        sleep(3)
        self.driver.find_element_by_link_text("""سامانه گلستان""").click()

    def _go_to_etelaate_jame_daneshjoo_page(self):
        """
        From golestan main page, it navigates to Etelaate Jame-e Daneshjoo page
        """
        self._switch_to_main_frame(2)
        sleep(5)
        etelaate_jame_daneshjoo_button = self.driver.find_element_by_xpath("""//*[text()='اطلاعات جامع دانشجو']""")
        etelaate_jame_daneshjoo_button.click()
        sleep(1)
        etelaate_jame_daneshjoo_button.click()

    def _go_to_semester(self):
        """
        From Etelaate Jame-e Daneshjoo, it navigates to your dedicated term page
        """
        self.driver.switch_to.default_content()
        self._switch_to_main_frame(3)

        terms_status_table = self.driver.find_element_by_xpath("""//table[@id="T01"]""")
        term_field = terms_status_table.find_element_by_xpath(
            f"""//tr[@class="TableDataRow"][{self.config.term}]/td[1]""")
        term_field.click()

    def _add_time_prefix(self, string):
        now = jdatetime.datetime.now()
        return f"[{now.month}/{now.day} {now.hour}:{now.minute}:{now.second}] {string}"

    def _print_grades(self, given_grades):
        if not given_grades:
            print(self._add_time_prefix("There is no grade given!"))
            return
        print(self._add_time_prefix("Currently given Grades are:"))
        for course_name, course_grade in given_grades.items():
            print(course_name, course_grade)

    def _find_given_grades(self):
        """
        When driver is in the page of a semester, this function finds courses with grades given
        :return: courses with given grades
        """
        result = {}
        grades_table = self.driver.find_element_by_xpath(""".//table[@id="T02"]""")
        grades_table = grades_table.find_element_by_xpath(""".//tbody""")
        grades_rows = grades_table.find_elements_by_xpath(""".//tr[@class="TableDataRow"]""")
        for row in grades_rows:
            course_name = row.find_element_by_xpath(""".//td[6]""").get_attribute("title")
            grade_element = row.find_element_by_xpath(""".//td[9]""")
            course_grade = grade_element.find_element_by_xpath(""".//nobr[1]""").text
            if course_grade:
                result[course_name] = course_grade
        return result

    def _refresh_grades_page(self):
        """
        This is dummy!
        Preventing Golestan to log us out because of inactivity, by clicking on previous term and next term.
        NOTE: This doesn't work when you're a freshman (When you don'y have any previous term)
            (Subject to change if another solution is found)
        """
        previous_term = self.driver.find_element_by_xpath(""".//img[@title="ترم قبلي"]""")
        previous_term.click()
        sleep(5)
        self.driver.switch_to.default_content()
        self._switch_to_grades_frame(3)
        next_term = self.driver.find_element_by_xpath(""".//img[@title="ترم بعدي"]""")
        next_term.click()
        sleep(5)

    def _create_grades_notif_message(self, grades):
        """
        Takes a list of tuples of grades in format (NAME, GRADE) and returns a beautified string
        :param grades: a list of tuples of grades
        :return: beautified string of grades with names and marks
        """
        return ", ".join([f"{name}: {mark}" for (name, mark) in grades])

    def _send_notification(self, new_grades_message):

        print('You have new grades!')
        print(new_grades_message)
        print('---------')
        if self.config.tg_notif:
            self.updater.bot.send_message(chat_id=self.config.tg_chat_id,
                                          text=f"You have new grades in golestan!\nGiven Grades are"
                                          f" {new_grades_message}")

    def _send_sms(self, new_grades_message):
        if self.config.sms_notif:
            api = KavenegarAPI(self.config.sms_api_key)
            params = {'sender': '1000596446', 'receptor': self.config.phone_number, 'message': new_grades_message}
            api.sms_send(params)
