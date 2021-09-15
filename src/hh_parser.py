from sklearn.feature_extraction.text import CountVectorizer

import pandas as pd
import requests
import json
import logging
import re

class Vacancy():
    def __init__(self, area=113):
        self.area = area

    def __get_vacancy_info(self, id_vac):
        """
        Возращает поробную информацию о вакансии

        Parameters:
        id_vac - id вакансии
        """

        try:
            req = requests.get(f'https://api.hh.ru/vacancies/{id_vac}')
            vacancy = json.loads(req.content.decode())
            req.close()
        except requests.exceptions.RequestException as e:
            logger.info(f'ERROR RequestException: {e}')
            return None
        except requests.exceptions.ConnectionError as err:
            logger.info(f'ERROR ConnectionError: {err}')
            return None
        except Exception as exc:
            logger.info(f'ERROR Exception: {exc}')
            return None

        return vacancy

    def __get_all_vacancies_info(self, vac_id):
        '''
        Возвращает подробную инфу о вакансии

        Parameters:
        vac_id - id вакансий
        '''

        vac = self.__get_vacancy_info(vac_id)
        if vac is None:
            logger.info(f'Ничего не вернулось при парсинге подробной инфы о вакансии {id}')
            return {}

        if vac.get('errors'):
            logger.info(f'ERROR при получении вакансии с {id}')
            return {}

        vac_name = str(vac.get('name', 'NaN')).replace(';', ' ')
        if vac.get('experience'):
            vac_exp = vac['experience'].get('id')
        else:
            vac_exp = ''
        vac_skills = ''
        for skill in vac.get('key_skills', []):
            vac_skills += skill['name'] + ','
        vac_skills = str(vac_skills[:-1]).replace(';', ' ')
        vac_descr = str(vac.get('description', 'NaN')).replace(';', ' ')

        vacancy = {}
        vacancy['title'] = vac_name
        vacancy['experience'] = vac_exp
        vacancy['key_skills'] = vac_skills
        vacancy['description'] = vac_descr
        #TODO добавить поля для парсинга, специализации, мб еще что-то

        return vacancy

    def __get_page(self, work_name, specialization=None, exp=None, page=0):
        ''' Возвращает страницу по заданным параметрам со всеми вакансиями

            Parameters:
            work_name - поисковой запрос
            prof - специализация
            exp - опыт работы
            page - номер страницы

        '''

        params = {
            'text': work_name,
            'area': self.area,
            'page': page,
            'per_page': 100  # default 100 (100 vacancy per each page)
        }

        if specialization:
            params['specialization'] = specialization

        if exp:
            params['experience'] = exp

        try:
            req = requests.get('https://api.hh.ru/vacancies', params)
            print(req.url)
            list_of_vacancies = req.content.decode()
            req.close()
        except requests.exceptions.RequestException as e:
            raise SystemExit(e)

        return json.loads(list_of_vacancies)

    def pars_vacansies(self, q, count=50):
        """
        Парсит вакансии по переданному поисковому запросу, парсит определенное кол-во. Парсится описание вакансии,
        название, ключевые скиллы, снипеты.

        Parameters:
        q: Поисковой запрос
        count: кол-во вакансий которое надо спарсить
        """

        experience = [{"id": "noExperience", "name": "Нет опыта"}, {"id": "between1And3", "name": "От 1 года до 3 лет"},
                      {"id": "between3And6", "name": "От 3 до 6 лет"}, {"id": "moreThan6", "name": "Более 6 лет"}]

        # получаем кол-тво вакансий
        param = self.__get_page(q)
        found = param['found']

        if count > found:
            count = found

        logger.info(f'Парсим  {count} вакансий из {found} найденных')
        pages = count // 100 + 1

        result_info = []

        if count > 2000:  # если вакансий больше 2000
            for exp in experience:  # тогда дробим вакансии по опыту работы

                for page in range(0, pages):  # перебираем страницы
                    logger.info(f'страница - {page} из {pages}, опыт - {exp}')

                    # получаем все вакансии со страницы
                    vacancies = self.__get_page(q, exp=exp['id'], page=page)
                    vacancies_info = self.__get_vacancies_info(vacancies['items'])
                    result_info += vacancies_info

        else:
            for page in range(0, pages):
                logger.info(f'страница {page+1} из {pages}')

                # получаем все вакансии со страницы
                vacancies = self.__get_page(q, page=page)
                vacancies_info = self.__get_vacancies_info(vacancies['items'])
                result_info += vacancies_info

        df = pd.DataFrame(result_info)
        ngrams = self.get_freq_ngrams(list(df.condition))

        return result_info, ngrams

    def __get_vacancies_info(self, vacancies):
        """
        Перебираем каждую вакансию и получаем подробную инфу о ней
        :param vacancies:
        :return:
        """
        vacansies_info = []
        for v in vacancies:  # перебираем каждую вакансию.
            vacancy_info = {}
            if v.get('snippet'):
                vacancy_info['requirement'] = str(v['snippet'].get('requirement', 'NaN')).replace(';', ' ')
                vacancy_info['responsibility'] = str(v['snippet'].get('responsibility', 'NaN')).replace(';', ' ')
            else:
                vacancy_info['requirement'] = None
                vacancy_info['responsibility'] = None

            vacancy_info['vacancy_id'] = v.get('id')

            all_vacancy_info = self.__get_all_vacancies_info(vacancy_info['vacancy_id'])
            vacancy_info.update(all_vacancy_info)

            vacancy_info['condition'] = self.__get_conditions(vacancy_info['description'])
            vacancy_info['description'] = self.__delete_html(vacancy_info['description'])
            vacansies_info.append(vacancy_info)

        return vacansies_info

    def __get_conditions(self, description):
        '''Достаем условия работы из описания вакансии
        :param description: текст описание вакансии
        '''
        test_re = re.search(r'(?<=условия).*?((?=\<strong\>)|$)', description.lower())
        if test_re:
            test_re = test_re.group(0)
        else:
            return ''
        test_re = self.__delete_html(test_re)
        test_re = test_re.strip(': ')
        test_re.strip()
        return test_re

    def __delete_html(self, text):
        test_re = re.sub(r'\<[^>]*\>', '', text)
        test_re.strip()
        return test_re

    def get_freq_ngrams(self, text):
        vectorizer = CountVectorizer(ngram_range=(1, 5))
        vec_text = vectorizer.fit_transform(text)
        vocab = vectorizer.vocabulary_

        count_values = vec_text.toarray().sum(axis=0)

        ngrams = []
        # output n-grams
        for ng_count, ng_text in sorted([(count_values[i], k) for k, i in vocab.items()], reverse=True):
            ngrams.append((ng_count, ng_text))

        return ngrams

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(name)s %(levelname)s:%(message)s')
    logger = logging.getLogger(__name__)

    vacancy_parcer = Vacancy()
    vacancies, ngrams = vacancy_parcer.pars_vacansies('python', 200)
    # print(vacancies)

if __name__ == 'hh_parser':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(name)s %(levelname)s:%(message)s')
    logger = logging.getLogger(__name__)

    vacancy_parcer = Vacancy()
    vacancies, ngrams = vacancy_parcer.pars_vacansies('машинное обучение', 200)
    # print(vacancies)